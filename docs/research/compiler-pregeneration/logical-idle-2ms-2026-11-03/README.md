# Logical-layer pregeneration: 2 ms versus 5 ms idle gaps

2026-11-03. Matched complete QAOA96 trace, History routing, T-HQA/OEE mapping
seed 42 and physics seed 60, four physical communication memories/core and
compiler quota four, generation capacity four. Both use original logical-layer
lookback 2-8, planner age limit ten, ready-first event admission, all-chain
preparation, handoff and 50 ms reservations. All four trials completed 7913
requests and passed audits. The 5 ms rows reuse the matched old-policy rerun;
2 ms rows are fresh. The explicit gap overrides the scheduler's default.

| Strategy | Idle gap (ms) | Hop latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) | Admission wait (ms/hop) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| on-demand | 5 | 1.3732 | 4.0941 | 94.981 | 0.00 | 0.0358 |
| dynamic | 5 | 1.0044 | 3.7064 | 93.777 | 65.41 | 0.2102 |
| on-demand | 2 | 1.3738 | 2.9053 | 94.981 | 0.00 | 0.0355 |
| dynamic | 2 | 1.0546 | 2.5447 | 94.338 | 63.68 | 0.2438 |

Makespan includes empty-layer gaps, so removing explicit idle time can shorten
makespan even if mean hop-service latency worsens. This is not a full local-gate
execution or teleportation model. Readiness counts consumed pairs generated
before first application submission, not necessarily before eligibility.
Fidelity is delivered EPR fidelity, not circuit output fidelity. One seed does
not establish robustness to physics or mapping variation. Earlier four-seed
means should not be mixed with this single-seed comparison.
