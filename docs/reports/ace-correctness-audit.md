# ACE correctness audit (Gate 1)

Written 2026-10-24 on branch `codex/ace-scheduler-correctness`, ACE commit `14cfdd2` plus the
event hooks of this gate. Plan: [`docs/plans/ace-correctness-and-congestion-program.md`](../plans/ace-correctness-and-congestion-program.md).

Every finding says what the evidence is: **source** (code read), **measured** (run on the real
simulator with the invariant monitor attached), or **both**. Where something is an inference, it
is labelled as one.

## Findings

| # | Question | Answer | Evidence |
| --- | --- | --- | --- |
| F1 | Does ACE let two requests share a core at once? | No. `serialize_core_conflicts` splits every layer into batches with at most one request per core, and it is applied whenever a compiler controller is attached. Peak demand per core falls from 24 to 1 on QFT. | source `parallel_core.py:24`, `:74-78`; measured |
| F2 | Can two requests be mistaken for one? | **Yes.** SeQUeNCe's `Reservation.__eq__` and `__hash__` compare initiator, responder, start, end, size and fidelity, not the request identity. ACE application reservations are plain `Reservation` objects. | source, below |
| F3 | Does a rejection partway along a path release the earlier bookings? | Yes, exactly once, on every node it travelled back through. | source `reservation.py` `pop`; measured, below |
| F4 | Does the physics layer limit a link to one pair at a time? | **No.** | source and measured, below |
| F5 | Can a compiler preparation leave phantom occupancy? | Not in the 24 legacy runs audited: every booking was released and no memory was held at the end. | measured, below |
| F6 | Is a trace layer a real barrier? | It is a conservative one; keeping it is safe. | source of the mapper, below |
| F7 | How does ACE handle a request that can never be admitted? | It retries forever. | measured, below |
| F8 | Is waiting for memory measured faithfully? | No: admission is polled every 1 ms plus a 0.2 ms round trip. | measured, below |

### F2. Reservation equality, and why the serialization hid it

The channels through which equality matters:

| Where | What it does with equality |
| --- | --- |
| stock `MemoryTimeCard.remove` | releases the first stored reservation that compares **equal**, which need not be the one passed in; used by REJECT handling |
| `reservation.py` `create_rules_request`, `create_rules_adaptive` | pick a request's memories with `reservation in card.reservations` |
| `reservation.py` protocol selection | `protocol.rule.get_reservation() == reservation` |
| `resource_manager.py` `expire_rules_by_reservation` fallback | `rule.reservation == reservation` |
| `request_app_parallel.py` | `entanglement_timestamps`, `entanglement_fidelities`, `latency` are dicts keyed by reservation |

Paths that use object identity (`is`) and are therefore safe: `_load_owned_rules`,
`release_reservation`, and the application's `schedule_reservation`.

Measured on one link, four requests, 32 memories per core, no serialization:

| | Identical reservation keys | Keys made distinct |
| --- | --- | --- |
| completed | 4 / 4 | 4 / 4 |
| retries | 3 | **0** |
| latencies (ms) | 1.2, 55.7, 62.2, 67.9 | 2.4, 0.4, 1.6, 1.2 |
| monitor | `ORPHAN_PAIR` x2 at 7.700 ms | no violations |

The only difference between the two columns is a fidelity target that differs by at most 3e-6.
The monitor shows the second pair arriving in memory 0 of both routers after the first request
had released it, so nobody was holding it. That is what the code reading predicts:
`create_rules_request` builds each request's memory list from every card that holds an
*equal* reservation. That the rules of the second request pointed at the first request's memory is
an inference from the code and from this trace, not something the log shows directly.

**Does it occur in legacy runs?** An equality audit wrapped the timecards and counted, on each
router, distinct reservation objects that compare equal and are booked at the same time. Random-16,
all five strategies including CGP and ACGP, three physics seeds each, serialization on: **none**.
The detector was validated first: on the known aliasing case it finds 12 incidents, and none when
the fidelity targets are made distinct. Not covered: CGP and ACGP on the MQT traces, which cost
minutes per run. So changing equality for application reservations cannot alter the legacy
numbers audited here, and the autonomous protocols' existing contract can stay as it is.

Because the legacy serialization never lets two requests with the same endpoints coexist, it
**masks** this defect in every legacy run; none of the 24 audits below triggers it. This is also a
plausible reason behind the comment in `parallel_core.py` that "a core cannot serve two
reservations at once". The measurements show that a core can: four different links through core 9
completed with no retry at 4 memories.

### F3. Rollback of a rejected reservation

Source: on REJECT, each node runs `card.remove(msg.reservation)` on all its timecards and passes
the message back toward the initiator. Measured with two single links into core 10 and one memory
per core: the second request booked its initiator's memory at 0.0 ms, was rejected at the
responder at 0.2 ms, its booking was released once (`Unbooked ... removed`) before it was
resubmitted, and it completed after the first request. Monitor: no violations. Release is
by `==`, which is safe here only because F2 does not apply.

### F4. No exclusive link

Source: `QuantumChannel.schedule_transmit` gives every photon its own time bin at the channel
frequency, and the base `BSM.get` groups photons by arrival time and keeps one per origin per
group. Nothing limits a link to one pair at a time. This agrees with the SeQUeNCe-based paper
(arXiv 2504.14040) and disagrees with the *assumption* of one teleportation per link in arXiv
2607.00469.

Measured, k simultaneous requests on one link (5 -> 9), distinct reservations, 32 memories, 5 seeds:

| k | completed | retries | mean latency (ms) | slowest (ms) | monitor |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 / 1 | 0 | 1.04 | 1.04 | clean |
| 2 | 2 / 2 | 0 | 0.96 | 1.28 | clean |
| 4 | 4 / 4 | 0 | 1.16 | 2.00 | clean |
| 8 | 8 / 8 | 0 | 1.58 | 4.00 | clean |
| 16 | 16 / 16 | 0 | 1.67 | 4.08 | clean |

If a link were exclusive the slowest request would scale with k (16 times at k = 16). It grows to
about 4 times and flattens, which is what the maximum of k independent random generation times
does. I did not fit a distribution.

### F5. No phantom occupancy in the legacy runs

Compiler traces under the legacy scheduler, mapping seed 42, physics seed 0:

| Workload | Memories | Strategy | App bookings | Compiler bookings | Released as | Live at end | Pairs delivered = credited + consumed |
| --- | ---: | --- | ---: | ---: | --- | ---: | --- |
| ghz | 4 | fixed | 48 | 61 | completed 48, consumed 46, removed 15 | 0 | 94 = 48 + 46 |
| ghz | 4 | dynamic | 48 | 48 | completed 48, consumed 48 | 0 | 96 = 48 + 48 |
| graphstate | 4 | fixed | 152 | 68 | completed 152, consumed 68 | 0 | 220 = 152 + 68 |
| graphstate | 4 | dynamic | 152 | 140 | completed 152, consumed 106, removed 34 | 0 | 258 = 152 + 106 |
| qft | 4 | fixed | 5020 | 1488 | completed 5020, consumed 1488 | 0 | 6508 = 5020 + 1488 |
| qft | 4 | dynamic | 5020 | 3010 | completed 5020, consumed 2674, removed 336 | 0 | 7694 = 5020 + 2674 |
| qft | 2 | fixed | 5020 | 524 | completed 5020, consumed 524 | 0 | 5544 = 5020 + 524 |
| qft | 2 | dynamic | 5020 | 1170 | completed 5020, consumed 1054, removed 116 | 0 | 6074 = 5020 + 1054 |

In all eight runs every booking was released exactly once, and every delivered pair was either
credited to a request or consumed by one. "Removed" is a booking rolled back after a rejection.
These runs end with no unused pair, so they do not exercise expiry; that needs the new scheduler's
tests.

The monitor found **no violation in any of 24 legacy audits**: Random-16 (62 requests), GHZ (24),
graph state (76), Draper (1,310), QFT (2,510) and QAOA (3,068), under on-demand, fixed and dynamic,
at 4 memories and, for QFT and QAOA, also 2. Completion was 100%, and per-qubit hop order and layer
barriers held. CGP and ACGP were not audited.

### F6. Trace layers

Source of the mapper (`mapper/qmap`): `slice_circuit` places each gate in the earliest layer after
the last layer its qubits used, an ASAP schedule of the circuit's dependency graph. HQA then maps
slice by slice, so the placement after a layer is a function of the placement before it. The
trace contains no gate-level dependencies. A layer boundary therefore stands in for them.
Probably it also stands in for the data-slot capacity the placement assumed; that is an inference
from how the mapper works, not something I verified. Dropping the barrier would need the
dependencies reconstructed from the circuit and the mapping. The barrier is kept.

### F7. A request that can never be admitted

Found by a mistaken microcase of my own: a hop between cores 8 and 10, which are not neighbours.
ACE routes it through core 9, which then needs two memories, and with one memory per core it
can never be admitted. It was retried every millisecond for the whole 60 s, about 300,000 events,
and never failed. Real traces contain only single links, so this cannot arise from a trace, but a
scheduler should refuse or fail such a request loudly. The test harness now refuses non-adjacent
hops.

### F8. Polling

In the responder-conflict case core 10's memory was free at 6.5 ms and the waiting request was
admitted at 7.2 ms, because retries run every 1 ms plus a 0.2 ms round trip. The cost is bounded by
the retry period for each wait, and it is added to every request's latency. Gate 3 replaces it with
admission triggered by the release.

## The hooks change nothing

The event hooks (a `recorder` that defaults to `None`, every emission guarded) were added to
`reservation.py`, `request_app_parallel.py`, `node.py` and `parallel_core.py`. With the hooks in
their final form, the full legacy baseline was rerun in fresh processes under
`PYTHONHASHSEED=31337` with `--strict`: **164 of 164 rows identical**, nothing skipped.

## What the audit does not cover

* One mapping seed (42) and one physics seed (0) for the 24 legacy audits.
* CGP and ACGP.
* Expiry of unused pairs, and starvation under load; both belong to Gate 4.
* Why the classical delay is 100 microseconds per message plus 20 per hop
  (`router_net_topo_adaptive.py:105-115`); that is Gate 5.

## Reproducing

```bash
python -B -m unittest discover -s test -p 'test_compiler*.py'        # includes the microcases
python tools/ace_correctness/audit_trace.py --trace <requests.txt> --strategy dynamic
```
