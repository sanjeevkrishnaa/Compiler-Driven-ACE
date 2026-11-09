# QAOA borrowing: exact L-3 versus exact L-2

Same source implementation on `codex/l2-borrow-refill` at 0fb30bc. Both runs use trace-order preparation, same-edge borrowing and immediate replenishment, eight communication memories with compiler quota six, generation capacity eight, a 50 ms reservation, frozen QAOA-224 mapping seed 42, and physics seed 60. Only the initial preparation lead/window and output directory differ.

| Routing | Lead | Mean latency (ms) | Completion (s) | Delivered fidelity | Prepared-pair fidelity at use | Waste |
|---|---|---:|---:|---:|---:|---:|
| xy | L2 | 1.067584 | 4.438001 | 0.943975 | 0.940999 | 4.462% |
| xy | L3 | 0.996829 | 4.115398 | 0.943798 | 0.941097 | 2.893% |
| history | L2 | 1.060163 | 4.282488 | 0.944536 | 0.941893 | 5.194% |
| history | L3 | 0.966871 | 3.973091 | 0.944201 | 0.941827 | 3.227% |

Delivered fidelity covers every delivered EPR pair, including on-demand fallback; prepared-pair fidelity covers only consumed compiler pairs. The raw-state creation fidelity is unchanged; storage and the mix of prepared/on-demand pairs affect fidelity at delivery.

| Routing | Lead | Ready-before-demand coverage | Average prepared-pair storage (ms) | Expiry | Borrowed pairs | Immediate replenishment requests |
|---|---|---:|---:|---:|---:|---:|
| xy | L2 | 55.369% | 4.775692 | 4.422% | 7089 | 7088 |
| xy | L3 | 57.365% | 4.728719 | 2.868% | 10961 | 10960 |
| history | L2 | 54.693% | 4.287951 | 5.169% | 7523 | 7516 |
| history | L3 | 58.004% | 4.328879 | 3.193% | 11373 | 11371 |

## Previously measured autonomous baselines

| Strategy | XY delivered fidelity | History delivered fidelity |
|---|---:|---:|
| ODG | 0.949813 | 0.949813 |
| CGP | 0.944951 | 0.945417 |
| ACGP | 0.945010 | 0.945452 |

Autonomous baseline figures are reused from the earlier matched QAOA seed-60, eight-memory study; they were not rerun.

All 29,605 requests completed on both routes with zero physical/ordering audit violations. Source fingerprints and parameters were checked against the previous L-2 borrowing run. The offline planner was independently checked to schedule every admitted initial preparation at exactly the third preceding communication-active layer. Replenishment remains an immediate exception to the initial lead, constrained by resources and current-demand priority. Targets already in service are not prepared redundantly.

The global default remains L-2. L-3 was selected using explicit matching minimum-lead and maximum-lookback CLI overrides. This is a one-seed comparison of EPR delivery, not a multi-seed statistical claim or a model of local data-qubit teleportation gates.
