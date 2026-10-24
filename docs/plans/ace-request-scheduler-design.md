# Request scheduler design (Gate 3)

**Status: implemented** in `request_scheduler.py` (3a polling admission, 3b event-driven admission). Written 2026-10-24. Context:
[`ace-correctness-and-congestion-program.md`](ace-correctness-and-congestion-program.md) and the
[audit](../reports/ace-correctness-audit.md).

## What is replaced, and what is not

`ParallelLayerRequestManager` (`parallel_core.py`) submits a layer's requests together, waits for
all of them, then starts the next. With a compiler controller it first splits each layer into
batches holding at most one request per core. It stays as the **legacy** manager, untouched, so the
recorded baseline keeps meaning something.

The replacement is a second class, `QubitOrderedRequestManager`, in a new module
`request_scheduler.py`. It subclasses the legacy manager and reuses its request accounting
(`_submit_request`, approval and rejection callbacks, `get_statistics`), and overrides only *when a
request is released* and *what happens when it times out*. After construction the run uses just
`start`, `get_statistics()` and `request_end_times`, plus the controller calls
`on_original_layer` and `mark_request_start`, so the swap is a one-line choice in
`run_parallel_experiment` (`scheduler="legacy" | "per-qubit"`, default legacy).

The reservation protocol is **not** changed here beyond Gate 2. Admission stays what it is: a
request is admitted when both endpoints can book a memory, atomically, with rollback on rejection.

## Release rules

Inputs per request, from the trace: id, layer, qubit, position within the layer. The tuple format
ACE's applications take is unchanged; the qubit travels in a side table.

* **Dependencies.** The hops of one qubit within one layer form a chain in trace order. A hop is
  *eligible* when the previous hop of its chain has completed. Hops of different qubits are
  independent and are released together. (D1: just-in-time use. Generation of a later hop's pair may
  begin earlier only through compiler preparation, which already works that way.)
* **Layer barrier (D2).** Layer L+1 becomes active when every request of layer L has completed.
  Kept because the trace carries no gate-level dependencies.
* **Layer activation** calls `on_original_layer(L)` once, as the legacy manager does at the first
  batch of a layer. `mark_request_start` is called at each request's first submission, so compiler
  readiness keeps its definition: the pair existed strictly before the application asked for it.
* **Empty layers** keep the legacy 5 ms gap, and each submission keeps the 5.3 ms reservation
  lead. Both are harness constants that dominate makespan (83-96% on the audited traces). They are
  preserved so the two managers are comparable, and made explicit and configurable in Gate 5.
* **Order.** Ready requests are released in trace order at a given instant, so runs are
  deterministic.

## Rejection and timeout

* **3a, polling (first).** A rejected request retries after 1 ms, exactly as in the legacy manager.
  A request still pending at the end of its reservation window is timed out and resubmitted
  *on its own*, one picosecond after the window ends. The legacy manager instead inserts one
  sequential retry layer per pending request, which blocks every other request behind it.

**Event order within one instant is not defined.** SeQUeNCe's event list is a `heapq` ordered by
(time, priority) alone, default priority `inf`, so events at the same time with the same priority
compare equal and `heapq` does not keep insertion order among equal keys (read in
`kernel/event.py` and `kernel/eventlist.py`). The run is still deterministic, since the same
operations always give the same order, but nothing in the scheduler may rely on one same-instant
event running before another. Two consequences:

* The expiry of an abandoned booking and the request's timeout fall at the same instant by
  construction, so the resubmission is scheduled strictly later (one picosecond, the unit of
  simulation time) and the old booking is certainly gone.
* A hop's completion is seen at the initiator before the responder has released its end in the
  same instant. A chain successor that starts at the relay core can therefore find the memory still
  booked and be rejected once. It retries, so this costs time and never correctness; with event-driven
  admission (3b) the responder's release wakes it. Whether it happens at one memory per core is
  measured in Gate 4, not assumed.
* **3b, event-driven (the default).** A released request waits in a line ordered by the time it
  became eligible, then by trace position. It is handed to the reservation protocol only when both
  of its cores have a memory free for its whole window. "Free" is read from each core's reservation
  table (the same overlap test the protocol applies) less the requests already admitted whose
  responder booking has not arrived yet. A release at any core (a booking removed, or a lease
  released) wakes the line one picosecond later, so every release of that instant has happened.
  Waiting counts in the request's latency (its clock starts when it became eligible).
  Reasoning, in place of the classical-literature claims I could not read first-hand:
  * *No hold-and-wait.* A request is admitted only if both endpoints are free, so no admitted request
    ever waits on another; a circular wait cannot form among application requests.
  * *Why not just poll.* Measured (`test_compiler_scheduler_admission.py`): two requests that swap two
    cores holding one memory each reject each other on the same 1 ms period for ever (about 2,500
    submissions each in 3 s). Found by the randomized traces (seed 0, one memory: 8 of 34 requests done in
    30 s; two requests submitted 25,000 times each).
  * *Starvation.* With `starvation_guard` (default on) an older request that cannot start yet keeps
    the free memory it would need, so younger requests cannot take it for ever. Without it a younger
    request goes ahead (tested both ways).
  * *Assumption, stated.* The scheduler is a central controller that reads every core's reservation
    table with no delay. Not measured, not free: a distributed scheduler would see stale tables.
  * *Fallback.* If requests wait and nothing is in flight, a booking that blocks them can only end
    with time, which reports no event; the line is then re-examined every millisecond.
  * *Physical rejections* still happen when something else takes a memory in between (a pre-generated
    pair); such a request rejoins the line and is re-examined after a millisecond or at the next release.
  * *Impossible requests* (more memories than a core has) raise `TraceError` when the manager is built.

Doing 3a and 3b as separate steps means any difference in results can be attributed to one change.

## Statistics

The keys the runner reads keep their names. `total_layers` is the number of trace layers;
`retry_layers` is 0 because there are no retry layers; `total_layers_with_retries` equals
`total_layers`; layer latencies are per trace layer. New per-request clocks are added as columns, so
`check` still treats them as informational: when it became eligible, when it was first submitted,
admitted, and delivered.

## Properties to be checked (Gate 4)

* Equivalence where it should hold: on a trace whose layers contain one chain each (GHZ), the new
  manager must reproduce the legacy manager's per-request latencies and makespan exactly. This is a
  prediction, tested, not assumed. Where layers hold independent qubits the results differ by design.
* Every invariant of `invariants.py` on real traces, with `submission_after_predecessor=True`:
  precedence, layer barrier, no stale or phantom booking, exactly-once release and completion.
* Forced timeouts (a short reservation window) exercise resubmission under both managers.
* Memory never over-subscribed, and a request that can never be admitted fails loudly instead of
  retrying forever (audit F7).
* The legacy baseline still reproduces 164 of 164 rows with the default scheduler.

## Not in this gate

Early generation of an *application* hop before its predecessor completes (pipelined on-demand),
which needs the escape-reserve rule R2. Whether on-demand is defined as just-in-time or pipelined is
still a decision for you and your guide; this gate implements just-in-time.
