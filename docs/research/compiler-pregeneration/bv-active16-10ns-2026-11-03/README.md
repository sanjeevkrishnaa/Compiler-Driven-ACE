| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (ms) | Chain readiness: full / partial / zero (%) | Hop readiness (%) |
| --- | ---: | ---: | ---: | --- | ---: |
| on-demand | 1.4231 | 94.981 | 37.0080 | 0.00 / 0.00 / 100.00 | 0.00 |
| dynamic | 0.9346 | 94.677 | 24.3074 | 62.50 / 18.75 / 18.75 | 80.77 |

208-qubit MQT BV; 4x4 mesh, 14 data slots/core, 8 communication memories/core, compiler quota8 and generation capacity8. T-HQA mapping seed42; History routing capacity threshold8; physics seed60. Active lookback2-16, planner age cutoff17, empty gaps10ns, reservation lifetime50ms. Execution-first, ready-first, all-chain preparation and native handoff; physical coherence unchanged. Same trace for both strategies. 26 hop requests across16 communication-active layers (722 logical layers), all completed with clean audits. Latency is eligibility-to-EPR-delivery per hop. Fidelity is delivered EPR fidelity, not circuit fidelity. Makespan includes empty gaps. Chain readiness is sampled at layer opening; hop readiness at individual hop eligibility. Single seed and a small communication sample.
