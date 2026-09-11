# Compiler-Driven Quantum Communication BTP — Complete Handoff

**Updated:** 11 September 2026
**Evidence status:** ACE fixed-lead results are final and audited. Native fixed-lead and cap-four studies are not final until their full 30-seed audits pass.

## Purpose and evidence boundary

This BTP tests whether compiler knowledge of a future inter-core communication trace can reduce service latency by pre-generating the exact EPR pair for the exact future request. It advances from topology-correct communication and analytical policies to physical ACE and native SeQUeNCe execution.

Never compare raw ACE and native SeQUeNCe milliseconds. They use different latency endpoints and physical/control paths. Compare policies only within the same backend and resource profile.

Every final number requires an immutable JSON contract, trace and serialization hash, paired seeds 0--29, raw-output hash, source/environment provenance, request completion, pair conservation, and request/pair identity audit. Seed zero is a smoke test only.

## Canonical repositories and published branches

Work only in these Sem 7/BTP repositories, not the Documents/ChatGPT mirror.

| Repository | Local path | Published branch |
|---|---|---|
| ACE | /Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE | https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0 |
| Native SeQUeNCe | /Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/SeQUeNCe | https://github.com/sanjeevkrishnaa/SeQUeNCe/tree/codex/native-compiler-4x4-physical |

- ACE is clean and pushed through https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/f163e16.
- Native source work is pushed through https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/7b8cb2eb.
- Native raw output directories remain local/untracked until complete audit, provenance, and tracked summaries are available.

## Locked workload and terminology

| Property | Value |
|---|---|
| Trace SHA-256 | 61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1 |
| Topology | 4x4 mesh, 16 cores, 24 neighbour links |
| Logical qubits | 96 |
| Source layers | 766 |
| Transfers | 4,954 |
| Serialized conflict-free sublayers | 2,831 |
| Replications | paired seeds 0--29 |
| Fixed-lead sweep | Delta = 1, 2, 3, 4, 5, 6 |

Transfers sharing a core are serialized; later sublayers wait for current sublayer completion.

- ODG/matched ODG: EPR generation begins after demand arrives; matched uses the comparison memory profile.
- Fixed compiler: request-specific preparation launches Delta sublayers before use.
- Dynamic compiler: trace-aware later feasible request-specific preparation.
- CGP/ACGP: traffic-oblivious speculative baselines; their pairs lack compiler request identity.
- Pre-ready: the request's exact pair exists before demand generation/release.
- Fallback: no exact ready pair exists, so demand generation is used.
- Expiry/waste: compiler pair expires or remains unused by completion.

Shared-pool demand first consumes an exact ready pair. Otherwise it atomically reserves a free slot at both endpoints or waits. It never holds a partial endpoint allocation.

## Completed implementation work

### Topology-correct classical communication

Sparse mesh-aligned classical links, hop-by-hop forwarding, XY routing, timing, and concurrent multi-hop support replaced an all-to-all control assumption.

- Implementation: https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/2cd7dd6b
- Native update: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/docs/native-compiler-4x4-update.md

### Compiler and native physical execution

The parser validates topology and placement, creates fixed/dynamic schedules, then native SeQUeNCe executes Barrett--Kok generation, failures/retries, decoherence, teleportation, swapping, correction, exact-pair consumption, and demand fallback.

- Native integration: https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/94f3b49a
- Compiler design: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/docs/compiler-driven-pregeneration.md
- Contract specification: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/docs/shared-qft-experiment-contract.md

### ACE lifecycle and pair-identity repair

Reusable ACE memory-slot names could cause stale compiler provenance. The correction closes stale records on slot reuse, uses the controller target map at both endpoints, and releases compiler bookkeeping correctly at use.

- Critical repair: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/53b5429
- ACE audit tool: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/audit_compiler_results.py
- ACE compiler method: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/COMPILER_PREGENERATION.md

Do not combine pre-correction ACE values with corrected final evidence.

### Fixed-lead and cap-four design

Every fixed-policy result requires the Delta 1--6 sweep; a fixed Delta-2 row is historical context only.

- Scope: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/FIXED_LEAD_STUDY_SCOPE.md
- ACE contracts: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0/experiments
- Native contracts: https://github.com/sanjeevkrishnaa/SeQUeNCe/tree/codex/native-compiler-4x4-physical/example/multicore_entanglement/contracts/fixed_lead
- Contract generator: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/generate_fixed_lead_contracts.py
- Matrix runner: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/run_contract_matrix.py

Cap four is separate from strict compiler-only 4+0: four shared slots/core, compiler cap four, no protected demand slot, and atomic wait-on-demand fallback. A matched atomic cap-three control must exist before making a capacity claim.

- Cap-four specification: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/docs/cap-four-wait-on-demand.md
- Native validation: https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/ab001392
- Native contract milestone: https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/7b8cb2eb

## Audited final ACE evidence

### ACE shared pool, legacy cap-three admission

Four physical slots/core; compiler cap three; demand fallback; six leads; 30 paired seeds each; locked trace; raw provenance; identity audit.

| Delta | Latency ms | Pre-ready | Fidelity at use | Expiry | Fallback |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.598283 | 59.17% | 0.8584 | 55.32% | 40.80% |
| 2 | 0.635186 | 54.72% | 0.7856 | 57.18% | 45.26% |
| 3 | 0.726038 | 44.15% | 0.7732 | 58.68% | 55.82% |
| 4 | 0.746164 | 41.91% | 0.7344 | 59.64% | 58.09% |
| 5 | 0.784498 | 37.25% | 0.7035 | 61.44% | 62.75% |
| 6 | 0.818597 | 33.56% | 0.6530 | 62.66% | 66.44% |

Within this legacy cap-three path, shorter lead improves all reported measures. It does not show universal Delta-1 optimality or isolate cap-three/cap-four capacity effects.

- Report: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/ace_fixed_lead_sensitivity_30seed_v1/report.md
- Summary CSV: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/ace_fixed_lead_sensitivity_30seed_v1/summary.csv
- Provenance/raw hashes: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/ace_fixed_lead_sensitivity_30seed_v1/provenance.json
- Result commit: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/d891a47

### ACE static 3+1, 2+2, and 1+1

All 18 profile/lead cells passed audit with 30 seeds and 148,620 request instances each: 2,675,160 request instances total.

| Profile | Best observed Delta | Latency ms | Pre-ready | Fidelity | Fallback |
|---|---:|---:|---:|---:|---:|
| 3+1 | 1 | 0.553104 | 64.38% | 0.8037 | 35.60% |
| 2+2 | 1 | 0.720845 | 44.61% | 0.8741 | 55.37% |
| 1+1 | 2 | 0.908687 | 22.85% | 0.8267 | 77.12% |

Use the full six-lead artifacts, not a single Delta-2 conclusion.

- Aggregate audit: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/ace_static_fixed_lead_sensitivity_30seed_v1/audit.json
- 3+1 report/CSV/provenance: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0/results/ace_static_fixed_lead_sensitivity_30seed_v1/3plus1
- 2+2 report/CSV/provenance: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0/results/ace_static_fixed_lead_sensitivity_30seed_v1/2plus2
- 1+1 report/CSV/provenance: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0/results/ace_static_fixed_lead_sensitivity_30seed_v1/1plus1
- Result commit: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/689692a

## Historical controls: valid context, not fixed-lead selection

These are validated historical 30-seed comparisons, but their fixed rows use Delta 2 and do not supersede the six-lead matrices.

| ACE shared-pool policy | Latency ms | Ready | Delivered fidelity | Expiry |
|---|---:|---:|---:|---:|
| Matched ODG | 1.104216 | 0.00% | 0.9498 | 0.00% |
| Fixed historical Delta 2 | 0.658471 | 51.92% | 0.8653 | 18.66% |
| Dynamic | 0.615906 | 56.83% | 0.8972 | 14.32% |

| ACE adaptive policy | Latency ms | Delivered fidelity | Expiry |
|---|---:|---:|---:|
| ODG | 1.104216 | 0.9498 | 0.00% |
| CGP | 0.547729 | 0.8623 | 74.27% |
| ACGP | 0.476298 | 0.8507 | 74.01% |
| Fixed historical Delta 2 | 0.658471 | 0.8653 | 18.66% |
| Dynamic | 0.615906 | 0.8972 | 14.32% |

ACGP has the lowest historical ACE latency. Dynamic has lower expiry and higher delivered fidelity. Do not start ACGP-improvement work until fixed-lead and cap-four controls finish.

| Native shared-pool policy | Latency ms | Ready | Delivered fidelity | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|
| Matched ODG | 0.076451 | 0.00% | 0.9498 | 0.00% | 100.00% |
| Fixed historical Delta 2 | 0.005092 | 92.23% | 0.7486 | 0.00% | 4.26% |
| Dynamic | 0.019885 | 68.95% | 0.8838 | 0.00% | 17.44% |

- Corrected ACE static history: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/CORRECTED_STATIC_ACE_30SEED.md
- ACE shared compiler history: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_COMPILER_30SEED.md
- ACE final shared comparison: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/SHARED_POOL_FINAL_COMPARISON_30SEED.md
- ACE/native study note: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/results/ACE_VS_NATIVE_SEQUENCE.md

## Report, slides, and Week 4 narrative

The technical report contains the research narrative, literature study, engineering contributions, evidence boundaries, tables, graphs, provenance links, capacity plan, and routing roadmap.

- LaTeX report: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/BTP_REPORT_SOURCE.tex
- Report visual history: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commits/codex/strict-compiler-4plus0/BTP_REPORT_SOURCE.tex
- IIT Guwahati/MARS cover: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/bd69e24

The research-paper section covers Kolar et al. (ACGP), Zhan et al. (native ACGP in SeQUeNCe), Chen et al. (AEPA), Suance et al. (multi-core policies), and the SeQUeNCe simulator paper. It records adopted methodology and limits rather than claiming another paper's numbers as project results.

Preferred professor presentation: visual-first editable 23-slide deck with speaker notes.

- Complete deck: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/presentations/BTP_Professor_Complete_10_Sep_2026.pptx
- Deck source: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/presentations/build_complete_professor_deck.mjs
- Earlier visual deck: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/presentations/BTP_Compiler_Driven_ACE_Visual_September_2026.pptx
- Deck commit: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/095d7df

Week 4 narrative:

- README: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/codex/strict-compiler-4plus0/MASTER_README.md
- Audited Week 4 update: https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/867dea6

## Required next sequence

1. Finish native fixed-lead matrices for static 3+1, 2+2, 1+1, and shared cap three at every Delta 1--6.
2. Run matched atomic cap-three and cap-four wait-on-demand controls in ACE and native.
3. Add only audited contract-bound tables, raw hashes, provenance, CSVs, and charts to the report, README, and presentation.
4. Then pursue physical-aware fixed/dynamic tuning.
5. Only after the controls, study fair ACGP comparison improvement.
6. Routing work requires a separately hash-locked workload with alternate paths; compare XY, offline compiler-selected routing, and adaptive compiler-driven routing under identical seeds and audits.

Native tools:

- Auditor: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/audit_sequence_study.py
- Trace runner: https://github.com/sanjeevkrishnaa/SeQUeNCe/blob/codex/native-compiler-4x4-physical/example/multicore_entanglement/run_native_compiler_trace.py

Routing studies must report path length, core/link peak occupancy, queue delay, attempts, swaps, readiness, fallback, expiry, delivered fidelity, and latency.

## New-session instruction

Read SESSION_CONTEXT_HANDOFF_11th_Sept_2026.md completely before acting. Work only in the canonical Sem 7/BTP ACE and SeQUeNCe repositories. Treat ACE shared/static Delta 1--6 as audited final evidence and historical fixed Delta-2 rows as snapshots only. Finish native fixed-lead matrices and the matched atomic cap-three/cap-four wait-on-demand control. Do not start ACGP-improvement work. Every final numerical result needs an immutable contract, 30 paired seeds, trace hash, raw provenance, and request/pair identity audit. Preserve incomplete raw output locally until its audit is complete. Commit small meaningful changes and push only confirmed canonical branches.
