| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Chain readiness: full / partial / zero (%) | Hop readiness (%) | Admission wait (ms/hop) |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| ODG | 1.3732 | 94.981 | 5.3050 | 0.00 / 0.00 / 100.00 | 0.00 | 0.0040 |
| Compiler quota 8 | 1.4285 | 93.403 | 6.4421 | 50.50 / 17.97 / 31.53 | 58.78 | 0.5731 |
| Compiler quota 6 | 1.0833 | 94.001 | 4.5781 | 40.82 / 19.63 / 39.55 | 49.77 | 0.1534 |

Same 208-qubit QAOA History trace, T-HQA/OEE mapping seed42, 4x4 mesh,
14 data slots/core, eight physical communication memories/core, physics seed60.
10ns empty gaps, active-layer lookback2-16, planner age cutoff17, generation
capacity8, execution-first ready-first admission, all-chain preparation, native
handoff and 50ms compiler reservation lifetime. Physical coherence is unchanged.

The quota-six candidate changes only --compiler-memories from8 to6 relative to
the completed quota-eight trial (apart from output path). The existing setting
limits offline compiler occupancy and runtime adaptive reservations at both
endpoints. ODG retains access to all eight physical memories. This is a fixed
compiler cap, not a demand-adaptive borrowing policy. Runtime booking diagnostics
verify at most six live compiler bookings/core. All trials completed30232 hops
with clean audits. Engine-facing source hashes match across all three trials.

Latency includes admission wait from hop eligibility to EPR delivery. Makespan
is the same end_to_end_latency_ms metric across trials. Chain readiness is sampled
at layer opening; hop readiness is sampled at individual hop eligibility. Fidelity
is delivered EPR fidelity, not circuit output fidelity. Single physics seed.
