# Verification of the per-qubit scheduler with event-driven admission (Gate 4)

Code at the commit that adds this file. ACE-internal numbers only; none are comparable with the native
SeQUeNCe backend. Data: `results/ace_scheduler_verification_2026-10-24/matrix_event_admission.csv`.

| Check | Result |
|---|---|
| Full matrix: 10 MQT workloads x on-demand/fixed/dynamic x 2 and 4 memories per core x physics seeds 0, 1 (120 cells), invariant monitor attached | 120 of 120 complete every request, 0 invariant violations |
| Rejections | on-demand: 0 in all 40 cells. With pre-generation (fixed, dynamic): 330 over 80 cells, at most 7 for any one request |
| Longest wait for admission | 14 ms (on-demand, 4 memories) to 78 ms (fixed, 2 memories) |
| GHZ against the legacy manager | event logs identical (on-demand, dynamic); fixed identical apart from reservation labels |
| Random small traces, 1/2/4 memories | all complete, no violation, never more bookings than memories; 16 memories: no contention |
| Python hash seeds 1 and 2, QFT dynamic, 2 memories | identical makespan (7134.42 ms), events and retries |
| Legacy baseline | 164 of 164 rows reproduced with the new code |
| Starvation guard, QFT on-demand, 2 memories | guard on 5571.8 ms, off 5416.6 ms: the guard costs 2.9% makespan here, in exchange for no starvation |

Reading the rejections: with pre-generation a pair can take a memory between the scheduler's check and the
reservation message arriving; the request rejoins the line. Whether every one of them is that case was not
traced individually, except that all 848 rejections of the earlier polling run on QFT (4 memories) coincided
with a core whose memories were all held by other requests.

Not covered: CGP and ACGP through the per-qubit scheduler (they need the request plan plumbed through the
runner), several mapping seeds, and expiry of unused pre-generated pairs under load.

## Wall-clock cost of the simulation (bare run, one at a time, no recorder)

Seconds of real time on the development Mac, 4 memories per core, physics seed 0, 4x4 mesh. Data:
`wall_time_legacy.csv`, `wall_time_per_qubit.csv`. These are timings of one run each on one machine, not a benchmark
of the machine: expect a few percent of noise. All 40 runs completed every request.

| Benchmark | Requests | On-demand legacy | On-demand per-qubit | Dynamic legacy | Dynamic per-qubit |
|---|---:|---:|---:|---:|---:|
| ghz | 24 | 0.1 | 0.0 | 0.0 | 0.0 |
| bv | 25 | 0.0 | 0.0 | 0.0 | 0.0 |
| graphstate | 76 | 0.0 | 0.0 | 0.1 | 0.1 |
| vqe_real_amp | 104 | 0.1 | 0.1 | 0.1 | 0.2 |
| bmw_quark_cardinality | 144 | 0.1 | 0.1 | 0.1 | 0.1 |
| cdkm_ripple_carry_adder | 456 | 0.2 | 0.2 | 0.3 | 0.3 |
| draper_qft_adder | 1,310 | 0.6 | 0.7 | 0.9 | 1.0 |
| qft | 2,510 | 1.3 | 1.4 | 1.6 | 1.6 |
| qaoa | 3,068 | 2.0 | 2.1 | 2.0 | 2.1 |
| randomcircuit | 11,688 | 5.9 | 6.2 | 11.6 | 11.5 |

The new scheduler costs about 5% more real time on the larger traces (it reads reservation tables at admission)
and the simulations are short either way. Real time is unrelated to the simulated makespan, which is what the
experiments report.
