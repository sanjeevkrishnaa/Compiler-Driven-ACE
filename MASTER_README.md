# Week 4 — Physical Validation and Audited Comparison

> **Week 4 source of truth.** Weeks 1–3 established the research idea, QFT
> trace and initial compiler work. This document records only Week 4: physical
> scheduler correction, realistic memory semantics, audited 30-seed results,
> and the valid ACE/native comparison.

## 1. Week 4 deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| ACE lifecycle repair | Complete | [scheduler](compiler_scheduler.py), [commit `8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940) |
| Corrected ACE static matrix | Complete, audited | [report](results/CORRECTED_STATIC_ACE_30SEED.md), [commit `0c70b95`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/0c70b95) |
| Strict 4+0 coverage test | Complete | [report](COMPILER_DRIVEN_ACE_4X4_REPORT.md), [commit `8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940) |
| ACE shared-pool compiler study | Complete, audited | [report](results/SHARED_POOL_COMPILER_30SEED.md), [commit `2659387`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/2659387) |
| ACE ODG/CGP/ACGP baseline | Complete, audited | [runner](run_trace_adaptive_baseline.py), [audit](audit_adaptive_baseline_results.py), [commits `e173c25`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/e173c25), [`f654fef`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/f654fef) |
| Native shared-pool compiler study | Complete, audited | [runner](../SeQUeNCe/example/multicore_entanglement/run_native_compiler_trace.py), [commit `0aad0d9f`](https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/0aad0d9f) |
| Final result aggregation | Complete | [report](results/SHARED_POOL_FINAL_COMPARISON_30SEED.md), [aggregator](summarize_shared_pool_study.py), [commit `eb9fed2`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/eb9fed2) |

## 2. Locked workload and interpretation boundary

| Property | Value |
|---|---:|
| Topology | 4×4 mesh, 16 cores |
| Logical qubits | 96 |
| Trace layers / transfers | 766 / 4,954 |
| Serialized sublayers | 2,831 |
| Replications | 30 paired seeds, 0–29 |
| Trace SHA-256 | `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1` |
| Serialization SHA-256 | `6b9520823830c50caaefb57baa737c2a8af834ef9474fe628df35def103a235d` |

The workload is frozen by [the static contract](experiments/qft_4x4_comparison_v1.json)
and [the final shared-pool contract](experiments/qft_4x4_shared_pool_v1.json).
Requests sharing a core are serialized; the next sublayer releases only after
the current one terminates.

ACE and native SeQUeNCe use different physical models and latency boundaries.
Therefore their raw milliseconds are **not** a speed comparison. The valid
comparison is the policy trade-off within each backend.

## 3. Policies and memory semantics

| Policy | Meaning |
|---|---|
| ODG | Generate after a request arrives. |
| CGP / ACGP | Speculative neighbour generation; ACGP adapts probabilities from traffic. |
| Fixed compiler | Prepare the exact requested pair two sublayers before use. |
| Dynamic compiler | Choose the latest feasible preparation in an eight-sublayer window with at least one-sublayer lead. |

Static allocations are per core:

```text
3+1  [ compiler ][ compiler ][ compiler ][ demand ]
2+2  [ compiler ][ compiler ][ demand ][ demand ]
1+1  [ compiler ][ demand ]
4+0  [ compiler ][ compiler ][ compiler ][ compiler ]  strict coverage only
```

The realistic Week 4 design is a [shared four-memory pool](SHARED_POOL_4X4_DESIGN.md):
compiler/speculative occupancy is capped at three; demand can use any free
slot. On a miss, demand atomically acquires every endpoint slot or waits with
no partial lock. Pending demand has priority over new speculative work.

## 4. Code changes and commits

| Area | Code | Week 4 contribution |
|---|---|---|
| ACE compiler path | [trace/planner](compiler_trace.py), [scheduler](compiler_scheduler.py), [runner](run_compiler_pregeneration.py) | Request-specific preparation, fixed/dynamic scheduling, shared pool and fallback. [Commits `bab1a14`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/bab1a14), [`8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940). |
| ACE lifecycle repair | [scheduler](compiler_scheduler.py), [test](test/test_compiler_one_shot.py) | Release compiler reservation/timecard/quota when its pair is consumed. |
| ACE adaptive path | [runner](run_trace_adaptive_baseline.py), [layer replay](parallel_core.py), [protocol](adaptive_continuous.py) | Hash-locked physical ODG/CGP/ACGP replay using the same shared pool. |
| ACE adaptive audit | [observer](adaptive_baseline_metrics.py), [auditor](audit_adaptive_baseline_results.py) | Pair conservation, unique use, timestamp and fidelity validation. |
| Native physical path | [compiler simulation](../SeQUeNCe/sequence/entanglement_management/generation/compiler_sequence.py), [model](../SeQUeNCe/sequence/entanglement_management/generation/sequence_model.py), [runner](../SeQUeNCe/example/multicore_entanglement/run_native_compiler_trace.py) | Barrett–Kok generation, noise, teleportation, shared fallback and traces. |
| Native audit | [auditor](../SeQUeNCe/example/multicore_entanglement/audit_sequence_study.py) | Pair accounting, no double use, capacity, timing and fidelity invariants. |
| Final aggregation | [script](summarize_shared_pool_study.py) | Generates the final table and seed-paired 95% intervals only within one backend. |

## 5. Critical ACE issue corrected

An application could consume a compiler pair while ACE still retained its
compiler reservation/timecard/quota until nominal 1,000 ms expiry:

```text
Before: generated → reserved → consumed → stale bookkeeping until expiry
After:  generated → reserved → consumed → bookkeeping released immediately
```

The defect caused artificial congestion and could lower readiness or inflate
retries. The repair is documented in [COMPILER_PREGENERATION.md](COMPILER_PREGENERATION.md).
Only the corrected ACE static matrix below is valid final evidence; it
supersedes prior ACE static values.

## 6. Result A — corrected static 3+1 / 2+2 / 1+1 comparison

### 6.1 ACE corrected 30-seed matrix

Sources: [corrected report](results/CORRECTED_STATIC_ACE_30SEED.md), local
[3+1 CSV](output/qft_static_corrected_30seed/static-3plus1/summary.csv),
[2+2 CSV](output/qft_static_corrected_30seed/static-2plus2/summary.csv),
[1+1 CSV](output/qft_static_corrected_30seed/static-1plus1/summary.csv),
and [audit JSON](output/qft_static_corrected_30seed/audit.json).

| Profile | Fixed: latency / ready / fidelity@use | Dynamic: latency / ready / fidelity@use | Dynamic vs fixed |
|---|---|---|---|
| 3+1 | 0.658419 ms / 51.87% / 0.7682 | 0.575869 ms / 61.59% / 0.8039 | **12.52% faster**, CI [11.80, 13.24] |
| 2+2 | 0.821357 ms / 32.97% / 0.8496 | 0.741142 ms / 42.13% / 0.8738 | **9.75% faster**, CI [9.11, 10.40] |
| 1+1 | 0.908687 ms / 22.85% / 0.8267 | 0.910578 ms / 22.57% / 0.7861 | 0.21% slower, CI [-0.49, 0.07] |

Dynamic wins at ACE 3+1 and 2+2. At 1+1 its confidence interval includes
zero; this does not establish a fixed/dynamic winner.

### 6.2 Native SeQUeNCe static 30-seed matrix

Sources: [aggregate report](results/shared_contract_30seed/RESULTS.md),
[aggregate CSV](results/shared_contract_30seed/aggregates.csv), and
[paired-effects CSV](results/shared_contract_30seed/paired_effects.csv).
The native rows remain valid. The ACE rows in that older aggregate predate the
Week 4 lifecycle correction and must not be used.

| Profile | Fixed: latency / ready / fidelity@use | Dynamic: latency / ready / fidelity@use | Dynamic vs fixed |
|---|---|---|---|
| 3+1 | 0.005028 ms / 92.29% / 0.7393 | 0.018990 ms / 69.66% / 0.8660 | 279.64% slower |
| 2+2 | 0.005028 ms / 92.29% / 0.7393 | 0.018990 ms / 69.66% / 0.8660 | 279.64% slower |
| 1+1 | 0.037042 ms / 51.46% / 0.6671 | 0.018990 ms / 69.66% / 0.8660 | **48.75% faster** |

The static study shows that memory allocation changes readiness, retry
opportunity, latency and fidelity. Different ACE/native policy orderings are
valid backend-specific outcomes, not a contradiction.

## 7. Result B — strict compiler-only 4+0 coverage

Source: [technical report](COMPILER_DRIVEN_ACE_4X4_REPORT.md).

| ACE policy, seed 0 | Completed / 4,954 | Strict misses | Coverage |
|---|---:|---:|---:|
| Fixed | 2,793 | 2,161 | 56.38% |
| Dynamic | 3,602 | 1,352 | 72.71% |

Compiler knowledge cannot eliminate finite capacity, physical failure or missed
deadlines. A complete system needs demand fallback.

## 8. Result C — final shared-pool compiler comparison

### ACE shared pool

Sources: [compiler report](results/SHARED_POOL_COMPILER_30SEED.md), local
[summary CSV](output/qft_shared_pool_compiler_30seed_v2/shared-pool-4-cap3/summary.csv),
and [audit JSON](output/qft_shared_pool_compiler_30seed_v2/audit.json).

| Policy | Latency | Ready | Fidelity@use | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|
| Matched ODG | 1.104216 ms | 0.00% | — | 0.00% | 100.00% |
| Fixed | 0.658471 ms | 51.92% | 0.7871 | 18.66% | 48.06% |
| Dynamic | 0.615906 ms | 56.83% | 0.8575 | 14.32% | 43.14% |

Dynamic is 6.45% faster than fixed (95% CI [5.79, 7.10]) and also has higher
readiness/fidelity and lower expiry.

### Native SeQUeNCe shared pool

Sources: local [summary CSV](../SeQUeNCe/output/qft_shared_pool_native_30seed/shared-pool-4-cap3/summary.csv),
[study JSON](../SeQUeNCe/output/qft_shared_pool_native_30seed/shared-pool-4-cap3/study.json),
and [audit JSON](../SeQUeNCe/output/qft_shared_pool_native_30seed/audit.json).

| Policy | Latency | Ready | Fidelity@use | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|
| Matched ODG | 0.076451 ms | 0.00% | — | 0.00% | 100.00% |
| Fixed | 0.005092 ms | 92.23% | 0.7486 | 0.00% | 4.26% |
| Dynamic | 0.019885 ms | 68.95% | 0.8838 | 0.00% | 17.44% |

The ACE/native comparison matches trace, serialization, seeds, memory count,
cap-three rule and demand-first atomic fallback. ACE dynamic wins over fixed;
native fixed wins latency/readiness while dynamic uses higher-fidelity prepared
pairs. Raw cross-backend latency comparison remains invalid.

## 9. Result D — normal ACE adaptive generation versus compiler scheduling

This is the completed comparison of ACE ODG, CGP, ACGP, fixed compiler and
dynamic compiler under one final shared-pool physical model.

Sources: [final generated report](results/SHARED_POOL_FINAL_COMPARISON_30SEED.md),
local [adaptive CSV](output/qft_shared_pool_adaptive_30seed/summary.csv),
[adaptive audit](output/qft_shared_pool_adaptive_30seed/audit.json), and
[aggregation script](summarize_shared_pool_study.py).

| ACE policy | Latency | Delivered fidelity | Prepared fidelity@use | Expiry |
|---|---:|---:|---:|---:|
| ODG | 1.104216 ms | 0.9498 | — | 0.00% |
| CGP | 0.547729 ms | 0.8623 | 0.8375 | 74.27% |
| ACGP | 0.476298 ms | 0.8507 | 0.8360 | 74.01% |
| Fixed compiler | 0.658471 ms | 0.8653 | 0.7871 | 18.66% |
| Dynamic compiler | 0.615906 ms | 0.8972 | 0.8575 | 14.32% |

| Seed-paired effect | Mean latency reduction | 95% CI |
|---|---:|---:|
| CGP vs ODG | 50.40% | [50.07, 50.72] |
| ACGP vs ODG | 56.86% | [56.57, 57.15] |
| Fixed compiler vs ODG | 40.37% | [40.01, 40.72] |
| Dynamic compiler vs ODG | 44.22% | [43.94, 44.50] |
| Dynamic compiler vs fixed compiler | 6.45% | [5.79, 7.10] |

ACGP has the lowest ACE latency in this matrix, but around 74% speculative
expiry. Dynamic compiler scheduling has much lower expiry (14.32%),
request-specific preparation and higher delivered fidelity than CGP/ACGP. This
is a measured latency–waste–fidelity trade-off, not a universal ranking.

## 10. Audit, conclusion and remaining work

| Verification | Outcome |
|---|---|
| ACE corrected static audit | 300 cells; 1,486,200 requests; passed |
| ACE shared compiler audit | 90 cells; 445,860 requests; 193,741 compiler-pair records; passed |
| ACE adaptive audit | 90 cells; 445,860 requests; 21,226 adaptive-pair records; passed |
| Native shared compiler audit | 90 cells; 445,860 successful requests; zero failures; passed |
| Focused ACE tests | 13 passed, 1 skipped |

Week 4 establishes physical compiler-driven preparation with realistic fallback.
It shows that memory allocation and preparation lead determine the
latency/readiness/fidelity/expiry trade-off. It does not establish that either
repository is globally faster.

| Remaining research | Reason |
|---|---|
| Native physical CGP/ACGP shared-pool matrix | Completes the symmetric adaptive-versus-compiler comparison in native SeQUeNCe. |
| Static-bank CGP/ACGP | Tests adaptive generation with permanent demand reservations. |
| Reservation-aware dynamic scheduling | React to physical admission/failure, not offline layer feasibility only. |
| Sensitivity and extra workloads | Vary cap/lead/lookahead/coherence/generation, then test another trace/topology. |

## 11. Repository links

- [Compiler-Driven ACE](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE), branch [`codex/strict-compiler-4plus0`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0).
- [Native SeQUeNCe](https://github.com/sanjeevkrishnaa/SeQUeNCe), branch [`codex/native-compiler-4x4-physical`](https://github.com/sanjeevkrishnaa/SeQUeNCe/tree/codex/native-compiler-4x4-physical).
