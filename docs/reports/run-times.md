# Run times of every experiment

Wall-clock seconds on the development Mac (8 CPUs, Python 3.13). Recorded by the drivers (`timings.csv`, `run_parameters.json`) except where stated.
An *invocation* is one process that runs one workload at one budget and policy for three physics seeds; a run is one physics seed (one third of an invocation).
Times from parallel runs include contention from the other jobs, so their sum exceeds the wall clock; the serial pass has no such inflation.

## Totals

| Experiment | Parallel jobs | Wall clock | Sum of invocation times |
|---|---:|---:|---:|
| Experiment 1, mesh (456 invocations, 1,368 runs) | 4 | 24.5 min | 95.3 min |
| Experiment 1, torus (456 invocations, 1,368 runs) | 4 | 25.2 min | 97.9 min |
| Sensitivity arm, ACGP Table I parameters (40 invocations, 120 runs) | 4 | 105.0 s | 6.3 min |
| Serial timing pass (90 invocations, 270 runs, mapping seed 42) | 1 | 8.6 min | 8.6 min |

Smaller pieces, timed separately: the heatmap regeneration 2.7 s; the endpoint-versus-relay split (Experiment 2, both counting variants) 4.3 s; mapping all 30 torus trials (ten workloads, three seeds) finished within 30 s of the launch; the offline re-routing study 190 s (mesh) and 475 s (torus) with 3 jobs; the simulation of re-routed mesh traces 1,200 s with 3 jobs while other jobs were running; the legacy baseline check about 15 min (not instrumented, so approximate).

## Per benchmark: sum of invocation seconds (parallel runs, contended)

| Benchmark | Mesh | Torus |
|---|---:|---:|
| GHZ | 64.1 s | 87.3 s |
| Bernstein-Vazirani | 65.3 s | 89.4 s |
| BMW/QUARK cardinality | 2.7 min | 2.7 min |
| VQE real amplitudes | 84.8 s | 117.0 s |
| CDKM ripple-carry adder | 3.2 min | 3.4 min |
| Graph state | 72.6 s | 101.7 s |
| Draper QFT adder | 5.7 min | 7.4 min |
| QAOA | 12.0 min | 10.6 min |
| QFT | 11.4 min | 11.8 min |
| Random circuit | 55.6 min | 55.4 min |

## Per benchmark, one run at a time: seconds per run (serial pass, mapping seed 42)

Each cell is the mean over the invocation's three physics seeds (invocation time divided by three).

| Benchmark | on-demand 1 | 2 | 4 | 8 | 32 | dynamic 2 | 4 | 8 | 32 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GHZ | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 |
| Bernstein-Vazirani | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 |
| BMW/QUARK cardinality | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 |
| VQE real amplitudes | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.5 | 0.5 | 0.5 |
| CDKM ripple-carry adder | 0.6 | 0.6 | 0.6 | 0.6 | 0.6 | 0.7 | 0.7 | 0.7 | 0.8 |
| Graph state | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 |
| Draper QFT adder | 1.1 | 1.1 | 1.1 | 1.1 | 1.2 | 1.2 | 1.4 | 1.4 | 1.6 |
| QAOA | 2.1 | 2.1 | 2.1 | 2.2 | 2.4 | 2.4 | 2.8 | 3.1 | 3.5 |
| QFT | 1.8 | 1.8 | 1.7 | 1.8 | 2.0 | 1.9 | 2.2 | 2.5 | 2.9 |
| Random circuit | 7.8 | 7.9 | 8.0 | 8.0 | 8.8 | 10.6 | 14.1 | 14.9 | 15.3 |

## Bare simulation at 4 memories, legacy against per-qubit scheduler (one seed, no event recorder, one at a time)

| Benchmark | on-demand legacy | on-demand per-qubit | dynamic legacy | dynamic per-qubit |
|---|---:|---:|---:|---:|
| GHZ | 0.1 s | 0.0 s | 0.0 s | 0.0 s |
| Bernstein-Vazirani | 0.0 s | 0.0 s | 0.0 s | 0.0 s |
| BMW/QUARK cardinality | 0.1 s | 0.1 s | 0.1 s | 0.1 s |
| VQE real amplitudes | 0.1 s | 0.1 s | 0.1 s | 0.2 s |
| CDKM ripple-carry adder | 0.2 s | 0.2 s | 0.3 s | 0.3 s |
| Graph state | 0.0 s | 0.0 s | 0.1 s | 0.1 s |
| Draper QFT adder | 0.6 s | 0.7 s | 0.9 s | 1.0 s |
| QAOA | 2.0 s | 2.1 s | 2.0 s | 2.1 s |
| QFT | 1.3 s | 1.4 s | 1.6 s | 1.6 s |
| Random circuit | 5.9 s | 6.2 s | 11.6 s | 11.5 s |

The new scheduler costs a few percent more real time on the larger traces, because it reads the reservation tables at admission. Real time has no relation to the simulated latency the experiments report.
