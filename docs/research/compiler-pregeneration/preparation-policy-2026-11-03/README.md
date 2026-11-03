| Configuration | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Hop readiness (%) | Admission wait (ms/hop) |
| --- | ---: | ---: | ---: | ---: | ---: |
| ODG | 1.3732 | 94.981 | 5.3050 | 0.00 | 0.0040 |
| Quota 4 | 1.1277 | 94.284 | 4.6706 | 34.31 | 0.0626 |
| Quota 5 | 1.0935 | 94.156 | 4.5023 | 42.34 | 0.0986 |
| Quota 6 | 1.0833 | 94.001 | 4.5781 | 49.77 | 0.1534 |
| Quota 7 | 1.1459 | 93.755 | 5.0570 | 56.70 | 0.2806 |
| Quota 6 + demand guard | 1.0011 | 94.071 | 4.3447 | 49.81 | 0.0955 |
| Quota 6 + guard + release/dependency priority | 1.0100 | 94.026 | 4.3684 | 49.84 | 0.1068 |
| Quota 6 + guard + release/dependency + runtime planner | 1.0442 | 94.447 | 4.0069 | 42.53 | 0.0903 |

208-qubit QAOA, same frozen History route and mapping seed42, 4x4 mesh,
14 data slots/core, eight physical communication memories/core, physics seed60.
All trials use10ns empty gaps, active lookback2-16, planner age cutoff17, generation
budget8, 50ms compiler reservation lifetime, execution-first ready-first admission,
all-chain preparation and native handoff. Physical coherence unchanged. Hop
readiness is ready-pair hits at individual hop eligibility; chain readiness is
deliberately omitted. Latency includes admission wait. Fidelity is delivered EPR
fidelity, not circuit output fidelity. Makespan is end_to_end_latency_ms /1000.

Quota-only trials use the original offline planner. Demand guard is an existing
optional control that blocks preparation sharing endpoints with waiting demand
and checks promised application slots. Release mode reuses existing memory-release
notifications, now coalesces bursts into one wake after application admission,
and ranks preparation by target layer and outstanding predecessor starts. This
is a dependency proxy, not a calibrated physical-time prediction. The1ms retry
remains a fallback for missed/non-memory wakeups; resource releases accelerate it.
Runtime planning supplies launch candidates without offline storage reservations;
the runtime enforces storage quota and a per-core eight-launch budget per active
layer. Failed locally booked handshakes count toward this launch budget. A1ms
retry or active-layer transition can revisit deferred candidates. All hops remain
eligible; no first-hop-only policy or pair borrowing is enabled.

The benchmark re-runs ODG and quota6 with the new source to expose regressions.
All eight trials must complete30232 requests, pass audits, share source hashes,
and respect compiler booking limits. This is one workload and physics seed, not
an across-workload guarantee. Defaults remain unchanged: new priority is opt-in.
Exact commands, raw pair/timing/admission records and metadata are retained.
