# Active-layer preparation with 0.5 ms empty gaps

Same QAOA96 History trace, seed 60, M=4/C=4, active lookback 2-8, generation
capacity 4, 50 ms reservation cap, ready-first admission and handoff. Only the
empty-layer gap changed to 0.5 ms, explicitly in both strategy commands.
Both trials completed 7913 requests and passed runtime audits.

| Strategy | Hop latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) | Admission wait (ms/hop) |
| --- | ---: | ---: | ---: | ---: | ---: |
| on-demand | 1.3731 | 2.3132 | 94.981 | 0.00 | 0.0352 |
| dynamic | 2.6404 | 3.6470 | 93.574 | 40.55 | 1.6135 |

These are single-seed EPR-delivery results, not full data-teleportation or local-gate simulation. The gap remains a timing assumption.
