# Same-edge borrowing with immediate replenishment

This branch starts at main `3c16c897f8da7b2c1f445940f70d099b580b8ef6`.
It does not import the unfinished completion-cleanup changes from
`history-algo-update`.

The CLI defaults to exact L-2 on the communication-active-layer axis, trace-order
preparation, eight communication memories per core with a six-memory compiler
quota, and borrowing enabled. `--no-borrow-compiler-pairs` provides the matched
control. Alternative preparation priorities remain available for experiments.

An earlier request may use a later, unstarted target's ready pair only on the
same undirected physical edge. Exact-target pairs take precedence. Readiness
checks require matching metadata and the physical pair at both endpoints, with
fidelity at least the request threshold. Checks do not consume the pair.

In-place RSVP handoff transfers the selected pair's existing memory leases to
the borrowing application. Generation is bound to that claimed pair, so it
cannot consume a different pair after reserving a particular physical memory.
The existing handoff checks continue to enforce physical ownership and expiry.

On consumption, the compiler clears the displaced target's accepted marker and
immediately calls its preparation launch path at the same simulation timestamp.
The replacement is an explicit replenishment exception to the original L-2
launch schedule. It still respects memory quota, generation capacity and demand
priority. If blocked, it remains queued for normal resource-release/retry events;
it is not promised instantaneous successful physical generation.

Duplicate endpoint notifications do not trigger duplicate replenishments. An
already-started target cannot be borrowed from or replenished by this path.
An earlier request on the reversed edge is eligible because an EPR pair is
bidirectional.

If a target starts its own demand during the borrower's RSVP flight, its existing
demand is allowed to finish; a redundant replacement is not submitted. The
experiment records these exceptions through the difference between borrowed-pair
and replacement-request counts.

The [QAOA comparison](qaoa-borrow-refill-2026-11-10.md) shows lower mean latency
and completion time but materially higher expiry/waste. Borrowing does not retain
the extremely low waste of request-bound L-2 preparation. Compact audited evidence
is under `results/compiler_borrow_refill_2026-11-10/`; full raw traces remain in
`output/qaoa-borrow-refill-2026-11-10/`.

New summary counters:

- `borrowed_compiler_pairs`: consumed pairs whose actual request differs from target.
- `replacement_preparations_requested`: displaced-target launch calls.
- `replacement_attempts_immediate`: launch calls at the consumption timestamp.

The QAOA experiment uses the frozen 224-qubit, mapping-seed-42 XY and cumulative
History traces from the previous study, physics seed 60 and identical physical
parameters in both arms. Only borrowing is switched off/on. Audit every transfer,
report average request latency and workload completion time separately, and keep
expiry/waste alongside coverage and fidelity. These single-seed results are a
screening comparison, not a statistical claim.

Run the physical regressions with the pinned SeQUeNCe 0.8.1 checkout on PYTHONPATH:

```
python -B -m unittest test.test_compiler_borrow_refill -v
python -B -m unittest discover -s test -p "test_compiler*.py"
```
