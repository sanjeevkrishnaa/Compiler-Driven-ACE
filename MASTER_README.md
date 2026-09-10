# Week 4 — Engineering Update: Physical Validation and Audited Comparison

## TL;DR

Week 4 converted the compiler-driven pre-generation work into a controlled,
audited physical-simulation study. It corrected the ACE reservation lifecycle,
re-ran the static 3+1, 2+2, and 1+1 matrix, tested strict compiler-only 4+0
coverage, implemented and audited a safe shared-memory pool, and completed the
within-backend ACE comparison with ODG, CGP, and ACGP. The report also records
the matched native SeQUeNCe shared-pool comparison. All final result tables are
supported by 30 paired seeds, raw provenance, CSV summaries, and audits.

> 📌 **Project:** Compiler-Driven ACE and native SeQUeNCe<br>
> **Reporting period:** September 5–9, 2026<br>
> **Primary implementation commits:** [`8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940), [`bab1a14`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/bab1a14), and [`94f3b49`](https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/94f3b49)<br>
> **Primary documentation commits:** [`102635a`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/102635a) and [`ae1d7f0`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/ae1d7f0)<br>
> **Status:** Implemented, audited, and documented; the controlled native CGP/ACGP comparison remains pending.

## Scope of this Week 4 report

Weeks 1–3 established the research idea, QFT trace, and initial compiler work.
This document is the Week 4 source of truth: it records only the physical
scheduler correction, realistic memory semantics, audited 30-seed results, and
the valid ACE/native comparison. Earlier reports remain the detailed records of
their respective implementation periods.

## 1. Week 4 deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| ACE lifecycle repair | Complete | [scheduler on GitHub](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/compiler_scheduler.py), [commit `8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940) |
| Corrected ACE static matrix | Complete, audited | [report on GitHub](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/CORRECTED_STATIC_ACE_30SEED.md), [commit `0c70b95`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/0c70b95) |
| Strict 4+0 coverage test | Complete | [report on GitHub](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/COMPILER_DRIVEN_ACE_4X4_REPORT.md), [commit `8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940) |
| ACE shared-pool compiler study | Complete, audited | [report on GitHub](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_COMPILER_30SEED.md), [commit `2659387`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/2659387) |
| ACE ODG/CGP/ACGP baseline | Complete, audited | [runner](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/run_trace_adaptive_baseline.py), [audit](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/audit_adaptive_baseline_results.py), [commits `e173c25`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/e173c25), [`f654fef`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/f654fef) |
| Native shared-pool compiler study | Complete, audited | [runner](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/run_native_compiler_trace.py), [commit `0aad0d9f`](https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/0aad0d9f) |
| Final result aggregation | Complete | [report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_FINAL_COMPARISON_30SEED.md), [tracked aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_aggregates.csv), [aggregator](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/summarize_shared_pool_study.py), [commit `eb9fed2`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/eb9fed2) |

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

The workload is frozen by [the static contract](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/experiments/qft_4x4_comparison_v1.json)
and [the final shared-pool contract](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/experiments/qft_4x4_shared_pool_v1.json).
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

The realistic Week 4 design is a [shared four-memory pool](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/SHARED_POOL_4X4_DESIGN.md):
compiler/speculative occupancy is capped at three; demand can use any free
slot. On a miss, demand atomically acquires every endpoint slot or waits with
no partial lock. Pending demand has priority over new speculative work.

## 4. Code changes and commits

| Area | Code | Week 4 contribution |
|---|---|---|
| ACE compiler path | [trace/planner](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/compiler_trace.py), [scheduler](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/compiler_scheduler.py), [runner](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/run_compiler_pregeneration.py) | Request-specific preparation, fixed/dynamic scheduling, shared pool and fallback. [Commits `bab1a14`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/bab1a14), [`8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940). |
| ACE lifecycle repair | [scheduler](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/compiler_scheduler.py), [test](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/test/test_compiler_one_shot.py) | Release compiler reservation/timecard/quota when its pair is consumed. |
| ACE adaptive path | [runner](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/run_trace_adaptive_baseline.py), [layer replay](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/parallel_core.py), [protocol](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/adaptive_continuous.py) | Hash-locked physical ODG/CGP/ACGP replay using the same shared pool. |
| ACE adaptive audit | [observer](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/adaptive_baseline_metrics.py), [auditor](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/audit_adaptive_baseline_results.py) | Pair conservation, unique use, timestamp and fidelity validation. |
| Native physical path | [compiler simulation](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/sequence/entanglement_management/generation/compiler_sequence.py), [model](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/sequence/entanglement_management/generation/sequence_model.py), [runner](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/run_native_compiler_trace.py) | Barrett–Kok generation, noise, teleportation, shared fallback and traces. |
| Native audit | [auditor](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/audit_sequence_study.py) | Pair accounting, no double use, capacity, timing and fidelity invariants. |
| Final aggregation | [script](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/summarize_shared_pool_study.py) | Generates the final table and seed-paired 95% intervals only within one backend. |

## 5. Critical ACE issue corrected

An application could consume a compiler pair while ACE still retained its
compiler reservation/timecard/quota until nominal 1,000 ms expiry:

```text
Before: generated → reserved → consumed → stale bookkeeping until expiry
After:  generated → reserved → consumed → bookkeeping released immediately
```

The defect caused artificial congestion and could lower readiness or inflate
retries. The repair is documented in [the compiler-pre-generation guide](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/COMPILER_PREGENERATION.md).
Only the corrected ACE static matrix below is valid final evidence; it
supersedes prior ACE static values.

## 6. How to read the result tables

| Term | Exact meaning in this document |
|---|---|
| Mean request latency | Average simulated service time from request release to completed communication. It is comparable only between policies in the same backend. |
| Ready / pre-ready | Fraction of transfers served by the intended prepared pair at release, without waiting for fresh demand generation. |
| Delivered fidelity | Fidelity of the EPR resource actually used by every completed transfer, including prepared and fallback pairs. |
| Prepared fidelity@use | Fidelity of only the pre-generated/compiler or background pairs when they are consumed. A higher value normally means the pair spent less time decohering in memory. |
| Expiry | Percentage of successfully prepared pairs that reached their lifetime limit before being consumed. It measures speculative waste, not request failure. |
| Fallback | Fraction of compiler requests that did not have their exact pair ready and therefore entered demand generation. A fallback can wait/retry and still complete successfully. |
| 95% CI | Two-sided Student-t confidence interval over 30 seed-paired effects. If a fixed-vs-dynamic interval includes zero, the experiment does not establish a reliable winner. |

Every reported 30-seed policy row contains 148,620 request instances
(4,954 requests × 30 seeds). Percentages and fidelity values describe different
questions and must not be combined into one informal “performance” score.

## 7. Result A — corrected static 3+1 / 2+2 / 1+1 comparison

### 7.1 ACE corrected 30-seed matrix

**Question.** How does a permanent compiler/demand memory split change the
fixed-versus-dynamic result?

GitHub evidence: [corrected report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/CORRECTED_STATIC_ACE_30SEED.md)
and [tracked corrected aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_corrected_ace_static.csv).

| Profile | Fixed: latency / ready / fidelity@use | Dynamic: latency / ready / fidelity@use | Dynamic vs fixed |
|---|---|---|---|
| 3+1 | 0.658419 ms / 51.87% / 0.7682 | 0.575869 ms / 61.59% / 0.8039 | **12.52% faster**, CI [11.80, 13.24] |
| 2+2 | 0.821357 ms / 32.97% / 0.8496 | 0.741142 ms / 42.13% / 0.8738 | **9.75% faster**, CI [9.11, 10.40] |
| 1+1 | 0.908687 ms / 22.85% / 0.8267 | 0.910578 ms / 22.57% / 0.7861 | 0.21% slower, CI [-0.49, 0.07] |

**Observations.** Moving from 3+1 to 2+2 reduces compiler capacity and lowers
readiness for both policies; moving to 1+1 reduces the total physical memory
count as well. Dynamic remains both faster and higher-fidelity at 3+1 and 2+2.
At 1+1 its readiness is slightly lower than fixed and its fidelity advantage
reverses.

**Why.** With enough compiler capacity, dynamic can place preparations closer
to use while avoiding planner-visible conflicts, improving freshness and
readiness. Under 1+1, one compiler slot and one demand slot leave too little
freedom: physical failures and demand contention dominate the offline timing
choice.

**Conclusion.** Dynamic is the supported ACE winner at 3+1 and 2+2. At 1+1
the [-0.49, 0.07]% interval includes zero, so the result does not establish a
latency winner.

### 7.2 Native SeQUeNCe static 30-seed matrix

GitHub evidence: [aggregate report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/shared_contract_30seed/RESULTS.md),
[aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/shared_contract_30seed/aggregates.csv), and
[paired-effects CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/shared_contract_30seed/paired_effects.csv).
The native rows remain valid. The ACE rows in that older aggregate predate the
Week 4 lifecycle correction and must not be used.

| Profile | Fixed: latency / ready / fidelity@use | Dynamic: latency / ready / fidelity@use | Dynamic vs fixed |
|---|---|---|---|
| 3+1 | 0.005028 ms / 92.29% / 0.7393 | 0.018990 ms / 69.66% / 0.8660 | 279.64% slower |
| 2+2 | 0.005028 ms / 92.29% / 0.7393 | 0.018990 ms / 69.66% / 0.8660 | 279.64% slower |
| 1+1 | 0.037042 ms / 51.46% / 0.6671 | 0.018990 ms / 69.66% / 0.8660 | **48.75% faster** |

**Observations.** Native fixed is much more ready at 3+1/2+2, but its used
pairs have lower fidelity. Dynamic wins at 1+1 and retains the same 69.66%
readiness shown at the larger partitions. Identical native 3+1 and 2+2 values
mean the additional fixed compiler slot was not the limiting resource for this
serialized workload—not that the profiles are universally equivalent.

**Why.** Fixed launches earlier, giving failed native physical generation
attempts more time to retry before release. The resulting pairs wait longer
and decohere more. Dynamic launches later and produces fresher pairs, but with
less retry time. Under 1+1, the fixed schedule's rigid contention outweighs its
retry advantage.

**Conclusion.** Memory allocation changes latency, readiness and fidelity
together. ACE and native can legitimately prefer different policies because
their physical-generation and scheduling lifecycles differ.

## 8. Result B — strict compiler-only 4+0 coverage

**Question.** If all four memories are assigned to compiler preparation and
on-demand generation is disabled, can compiler knowledge serve every request?

GitHub evidence: [technical report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/COMPILER_DRIVEN_ACE_4X4_REPORT.md)
and [implementation commit `8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940).

| ACE policy, seed 0 | Completed / 4,954 | Strict misses | Coverage |
|---|---:|---:|---:|
| Fixed | 2,793 | 2,161 | 56.38% |
| Dynamic | 3,602 | 1,352 | 72.71% |

**Observation.** Dynamic covers 809 more requests than fixed, but still misses
1,352 of 4,954 transfers. These are terminal misses because the experiment
forbids fallback.

**Conclusion and limitation.** Compiler knowledge cannot eliminate finite
capacity, physical failure or missed deadlines; a complete system needs demand
fallback. This is a full-trace **seed-0 diagnostic**, not a 30-seed latency
comparison, so it supports the fallback requirement but not a population-level
fixed/dynamic performance claim.

## 9. Result C — final shared-pool compiler comparison

### ACE shared pool

**Question.** Does sharing all four memories with a compiler-occupancy cap
retain fallback safety while improving compiler preparation?

GitHub evidence: [compiler report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_COMPILER_30SEED.md),
[tracked aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_aggregates.csv), and
[paired-effect CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_paired_effects.csv).

| Policy | Latency | Ready | Fidelity@use | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|
| Matched ODG | 1.104216 ms | 0.00% | — | 0.00% | 100.00% |
| Fixed | 0.658471 ms | 51.92% | 0.7871 | 18.66% | 48.06% |
| Dynamic | 0.615906 ms | 56.83% | 0.8575 | 14.32% | 43.14% |

**Observation.** Both compiler policies complete all requests and reduce
latency versus matched ODG. Dynamic is 6.45% faster than fixed (95% CI
[5.79, 7.10]), improves readiness by 4.91 percentage points, increases
prepared fidelity from 0.7871 to 0.8575, and lowers expiry by 4.34 points.
The 43.14% dynamic fallback rate is not a failure rate: those requests enter
demand generation and still complete.

**Conclusion.** Dynamic is the clear compiler-policy winner inside the ACE
shared-pool experiment. The pool prevents a compiler preparation from
permanently monopolising the only recovery path, but fallback remains essential.

### Native SeQUeNCe shared pool

GitHub evidence: [tracked aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_aggregates.csv),
[paired-effect CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_paired_effects.csv),
[native runner](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/run_native_compiler_trace.py), and
[native auditor](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/audit_sequence_study.py).

| Policy | Latency | Ready | Fidelity@use | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|
| Matched ODG | 0.076451 ms | 0.00% | — | 0.00% | 100.00% |
| Fixed | 0.005092 ms | 92.23% | 0.7486 | 0.00% | 4.26% |
| Dynamic | 0.019885 ms | 68.95% | 0.8838 | 0.00% | 17.44% |

**Observation.** Fixed supplies 92.23% of requests from prepared pairs and has
only 4.26% demand fallback, while dynamic supplies 68.95% and falls back for
17.44%. Dynamic's used pairs are substantially fresher: fidelity 0.8838 versus
0.7486. Both have zero measured expiry in this native contract.

**Why.** Native fixed starts earlier and has more time to recover from failed
Barrett–Kok attempts. Dynamic launches closer to use, preserving fidelity but
reducing retry opportunity. This is the same retry-time-versus-freshness
mechanism visible in the native static study.

### ACE versus native: valid conclusion

The comparison matches trace, serialization, seeds, memory count, cap-three
rule and demand-first atomic fallback. ACE dynamic wins over fixed; native
fixed wins latency/readiness while dynamic wins prepared-pair fidelity. This
shows that the scheduling decision interacts with backend physics. It does not
show that either simulator or architecture is globally faster.

## 10. Result D — normal ACE adaptive generation versus compiler scheduling

This is the completed comparison of ACE ODG, CGP, ACGP, fixed compiler and
dynamic compiler under one final shared-pool physical model.

**Question.** Under the same ACE shared pool, how does exact compiler
foreknowledge compare with normal traffic-oblivious CGP and history-adaptive
ACGP?

GitHub evidence: [final generated report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_FINAL_COMPARISON_30SEED.md),
[aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_aggregates.csv),
[paired-effect CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_paired_effects.csv),
[aggregation code](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/summarize_shared_pool_study.py), and
[adaptive audit code](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/audit_adaptive_baseline_results.py).

| ACE policy | Latency | Delivered fidelity | Prepared fidelity@use | Expiry |
|---|---:|---:|---:|---:|
| ODG | 1.104216 ms | 0.9498 | — | 0.00% |
| CGP | 0.547729 ms | 0.8623 | 0.8375 | 74.27% |
| ACGP | 0.476298 ms | 0.8507 | 0.8360 | 74.01% |
| Fixed compiler | 0.658471 ms | 0.8653 | 0.7871 | 18.66% |
| Dynamic compiler | 0.615906 ms | 0.8972 | 0.8575 | 14.32% |

`Ready` is intentionally not placed in this adaptive-comparison table for
CGP/ACGP. Compiler readiness asks whether a particular request's intended pair
was prepared. CGP/ACGP do not target request IDs, so presenting the same label
would imply a false one-to-one meaning. Their actual used-pair fidelity,
generated/used/expired lifecycle and request latency are audited instead.

| Seed-paired effect | Mean latency reduction | 95% CI |
|---|---:|---:|
| CGP vs ODG | 50.40% | [50.07, 50.72] |
| ACGP vs ODG | 56.86% | [56.57, 57.15] |
| Fixed compiler vs ODG | 40.37% | [40.01, 40.72] |
| Dynamic compiler vs ODG | 44.22% | [43.94, 44.50] |
| Dynamic compiler vs fixed compiler | 6.45% | [5.79, 7.10] |

**Observations.** ACGP has the lowest ACE service latency, followed by CGP,
dynamic compiler, fixed compiler and ODG. The compiler result is different on
waste and quality: dynamic expiry is 14.32%, compared with approximately 74%
for CGP/ACGP, and its delivered fidelity is 0.8972 rather than 0.8623/0.8507.
Dynamic also beats fixed compiler by a statistically supported 6.45%.

**Why.** CGP/ACGP continuously populate memories without needing an exact
future request match, so a coincidentally useful pair can make admission fast.
That aggressiveness also produces many pairs that are never used before
expiry. Compiler scheduling targets known requests and therefore avoids much
of that waste, but finite capacity and physical-generation deadlines prevent
every planned pair from being ready.

**Conclusion.** ACGP is the latency winner for this ACE contract; dynamic is
the compiler-policy winner and offers a much stronger waste/fidelity balance.
The study therefore reveals a multi-objective trade-off rather than one
universally best policy. A thesis claim must state which objective—latency,
fidelity, memory efficiency or predictability—is being optimised.

## 11. Audit evidence

| Verification | Outcome |
|---|---|
| ACE corrected static audit | 300 cells; 1,486,200 requests; passed |
| ACE shared compiler audit | 90 cells; 445,860 requests; 193,741 compiler-pair records; passed |
| ACE adaptive audit | 90 cells; 445,860 requests; 21,226 adaptive-pair records; passed |
| Native shared compiler audit | 90 cells; 445,860 successful requests; zero failures; passed |
| Focused ACE tests | 13 passed, 1 skipped |

GitHub evidence: [tracked audit summary CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_audit_summary.csv),
[ACE adaptive auditor](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/audit_adaptive_baseline_results.py), and
[native auditor](https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/audit_sequence_study.py).

Passing an audit means all expected policy/seed cells are present, every
request is accounted for, pair creation equals terminal pair outcomes, no pair
is consumed twice, memory occupancy stays within its configured bound, event
times are ordered, and fidelities remain in [0,1]. An audit does not prove that
the physical parameter assumptions match future hardware; it proves that the
reported experiment obeys its declared simulator contract.

## 12. Week 4 conclusions

1. Compiler-directed physical pre-generation works, but strict 4+0 proves it
   cannot replace demand fallback.
2. Memory layout is part of the algorithm: it changes preparation capacity,
   demand recovery, retry time, freshness and expiry together.
3. Dynamic is the supported ACE compiler winner in static 3+1/2+2 and in the
   final shared pool; ACE 1+1 establishes no reliable fixed/dynamic winner.
4. Native fixed wins shared-pool latency/readiness because it gains retry time;
   native dynamic trades latency for substantially higher pair fidelity.
5. ACE ACGP minimises latency in the adaptive comparison but expires roughly
   three quarters of generated speculative pairs. Dynamic compiler scheduling
   uses future knowledge to obtain a lower-waste, higher-delivered-fidelity
   operating point.
6. These claims apply to this 4×4 QFT trace and declared physical parameters.
   They are not a general hardware result or a raw ACE/native speed ranking.

## 13. Remaining work after Week 4

| Remaining research | Reason |
|---|---|
| Native physical CGP/ACGP shared-pool matrix | Completes the symmetric adaptive-versus-compiler comparison in native SeQUeNCe. |
| Static-bank CGP/ACGP | Tests adaptive generation with permanent demand reservations. |
| Reservation-aware dynamic scheduling | React to physical admission/failure, not offline layer feasibility only. |
| Sensitivity and extra workloads | Vary cap/lead/lookahead/coherence/generation, then test another trace/topology. |

## 14. Repository and evidence index

- [Compiler-Driven ACE](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE), branch [`codex/strict-compiler-4plus0`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0).
- [Native SeQUeNCe](https://github.com/sanjeevkrishnaa/SeQUeNCe), branch [`codex/native-compiler-4x4-physical`](https://github.com/sanjeevkrishnaa/SeQUeNCe/tree/codex/native-compiler-4x4-physical).
- [Corrected ACE static report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/CORRECTED_STATIC_ACE_30SEED.md) and [CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_corrected_ace_static.csv).
- [Final shared-pool report](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_FINAL_COMPARISON_30SEED.md), [aggregate CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_aggregates.csv), and [paired-effect CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_shared_pool_paired_effects.csv).
- [Audit summary CSV](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/week4_audit_summary.csv).
