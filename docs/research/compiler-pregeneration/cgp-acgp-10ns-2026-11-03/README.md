| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) |
| --- | ---: | ---: | ---: |
| ODG | 1.3732 | 94.981 | 5.3050 |
| CGP | 1.1070 | 94.322 | 3.3903 |
| ACGP | 1.0920 | 94.332 | 3.3873 |
| Compiler quota6 + demand guard | 1.0011 | 94.071 | 4.3447 |

208-qubit QAOA, same History route and seed42 T-HQA mapping, 4x4 mesh,
14 data slots/core, eight physical communication memories/core, physics seed60,
10ns empty-layer gaps and the same per-qubit event scheduler. CGP and ACGP have
an explicitly configured six-slot autonomous cache cap, matching compiler quota6.
They retain native background-generation behavior and the200ms protocol period
from ace/topology/node.py. Their reservations use the native period rounding;
the compiler's50ms reservation parameter does not apply to them. Compiler active
lookback, generation launch budget, demand guard and directed handoff are compiler
controls, not autonomous-policy overrides. No autonomous timing tuning was done.

Latency is eligibility-to-EPR-delivery per hop and includes admission wait;
makespan is end_to_end_latency_ms /1000. Fidelity is delivered EPR fidelity.
All30232 hop requests completed with clean audits, and engine-facing source
fingerprints match across the four trials. This is a single-seed comparison of
the current implementations. Autonomous hop readiness is not reported: compiler
hit counters are not a valid measurement of generic CGP/ACGP cache readiness.
