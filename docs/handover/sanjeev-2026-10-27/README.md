# ACE handover — 27 October 2026

This bundle is the compact handover record for the ACE work completed from 24
to 27 October 2026.  It is intentionally evidence-first: the three reports,
their numerical data, and the fixed Git revision are more authoritative than a
verbal summary.

## Exact baseline

| Item | Value |
| --- | --- |
| Repository | `sanjeevkrishnaa/Compiler-Driven-ACE` |
| Working branch | `codex/ace-scheduler-correctness` |
| Handover revision | `6247e48a1a4bfe83814dd5f3d1669e46aa421dd4` |
| SeQUeNCe revision used in final QFT-96 report | `cf5283cdfd6692a82a090d15fb09fbc01bd322fc` |
| Final QFT-96 campaign | 1,639 base jobs + 143 Dynamic-policy jobs; 6,688 policy/seed observations |
| Official physics seeds | 0 and 1 |

Clone/check out that exact branch and revision before changing or rerunning
anything.  All three reports below are versioned in the repository and are
also copied into this zip for offline reading.

```sh
git clone https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE.git
cd Compiler-Driven-ACE
git checkout codex/ace-scheduler-correctness
git checkout 6247e48a1a4bfe83814dd5f3d1669e46aa421dd4
```

## Read these reports in this order

| Order | Report | What it establishes | Interpretation status |
| ---: | --- | --- | --- |
| 1 | `01_ace_correctness_report.pdf` | Full correctness audit, historical timing analysis, mapping/routing context, and ACE model limitations. | Background and audit record; do not mix its historical timing values with final metrics. |
| 2 | `02_oct25_pre_golden_dynamic_routing.pdf` | Retrospective of the 25 October routing and Dynamic pre-generation/allocation experiments. | Historical controlled study; clearly separated from the final campaign. |
| 3 | `03_qft96_final_results.pdf` | Completed QFT-96 matrix: mesh and torus, memory allocations, policies, routes, 13 Dynamic launch variants, verified congestion atlas, figures, tables, and CSV provenance. | Current authoritative QFT-96 result. |

The 25 October reports remain valuable because they explain how the timing and
Dynamic-policy questions were found.  The third report is the one to cite for
the final QFT-96 values.

## Final model decisions

1. **Movement model:** ACE receives adjacent-hop requests and models
   hop-by-hop teleportation.  It is not modelling one end-to-end EPR-swapping
   reservation for a multihop migration.
2. **Latency:** for a completed request, latency is `completion - eligibility`.
   It includes control/RSVP delay, shared communication-memory admission
   waiting, retries, EPR generation and delivery.  It excludes cache residence
   before the request becomes eligible.  Mean/median/p95/max request latency
   and workload makespan are separate metrics.
3. **Historical 5.3 ms:** this was an old pre-generation lead and a
   service-local subtraction, not a physical constant.  It is retained only
   for reproducing historical results.  The corrected final study uses no
   arbitrary 5.3-ms lead.
4. **Memory:** each core uses a shared communication-memory pool.  For total
   memory budget `M`, Dynamic compiler allocation `C` is explicitly swept for
   every legal `0 <= C < M`; no hidden fixed allocation is used.
5. **Mapping and routing:** T-HQA placement is held fixed for the QFT-96
   campaign.  Routing follows it: mesh uses XY, YX, shortest-reliable and
   maximum-reliability; torus uses Dijkstra.  QFT-96 placement endpoints were
   reconstructed by replaying the historical complete hop trace, because the
   original QFT-96 mapper NPZ was not archived.

## Final QFT-96 experiment scope

| Dimension | Values |
| --- | --- |
| Workload | QFT-96 |
| Topologies | 4x4 mesh; 4x4 torus |
| Routes | Mesh: XY, YX, shortest-reliable, maximum-reliability. Torus: Dijkstra. |
| Total communication memories/core | 2, 3, 4, 6, 8, 16, 32 |
| Main policies | ODG, CGP, ACGP, Dynamic full-chain, Dynamic first-hop |
| Auxiliary Dynamic variants | 13 launch-policy variants at `M=4, C=3` |
| Measurements | latency distribution, admission wait, makespan, throughput, readiness/hit/fallback, waste/expiry/storage, retries, completion, fidelity, and congestion |
| Congestion evidence | All 210 heatmaps, independently recomputed and verified |

Important scope boundaries:

- The final campaign uses one workload and two physics seeds.  It is strong
  reproducible evidence for QFT-96, but not proof of universal policy
  superiority across workloads or hardware parameter sets.
- The 64-memory endpoint was explicitly excluded from the official campaign.
  Do not blend partial `M=64` outputs into the official summaries.
- Maximum-reliability is a controlled reconstructed-reliability alternative;
  it is not a byte-for-byte recovery of the mapper's unarchived original random
  reliability map.
- Relay data-qubit computation-slot occupancy is an acknowledged simulator
  limitation, not silently modelled.

## Most useful repository entry points

| Purpose | Path |
| --- | --- |
| Correctness audit | `docs/research/ace-correctness-audit-2026-10-25.md` |
| Project file map | `docs/project-structure.md` |
| QFT-96 frozen design | `docs/research/qft96-experimental-design.md` |
| QFT-96 run handoff | `docs/plans/handoff-qft96-study-2026-10-26.md` |
| Official final result root | `results/qft96_2seed_2026-10-26/` |
| Final result report source/data | `docs/latex/qft96_final/` |
| October-25 report source/data | `docs/latex/oct25_pre_golden/` |
| Final report builder and independent validator | `tools/golden_study/build_qft96_final_report.py` |
| Historical report builder | `tools/build_oct25_report.py` |
| End-to-end QFT launcher | `tools/golden_study/run_qft96_all.sh` |

## Reproduction and audit commands

The final report builder audits results; it does **not** launch simulations:

```sh
python -m tools.golden_study.build_qft96_final_report --verify-only
cd docs/latex/qft96_final && tectonic main.tex
```

For the 25 October historical report:

```sh
python tools/build_oct25_report.py
cd docs/latex/oct25_pre_golden && tectonic main.tex
```

The exact launch configuration and source/config/trace fingerprints are in:

- `results/qft96_2seed_2026-10-26/execution_spec.json`
- `results/qft96_2seed_2026-10-26/execution_scope.json`
- `docs/latex/qft96_final/data/job_provenance.csv`
- `docs/latex/qft96_final/data/validation.json`

## Contents of this zip

```text
README.md                                      this handover
reports/01_ace_correctness_report.pdf          report 1
reports/02_oct25_pre_golden_dynamic_routing.pdf report 2
reports/03_qft96_final_results.pdf             report 3
context/                                       audit, design, timing matrix, project map,
                                               result README and prior QFT handoff
evidence/                                      validation, source ledger, provenance and metric CSVs
tools/                                         two report builders and QFT launcher
```

The zip intentionally does not duplicate thousands of raw per-job simulator
directories.  The committed final report includes complete derived per-seed
and aggregate/provenance CSVs needed to audit every included figure.  Raw
outputs remain in the original local result trees and should be archived
separately only if Sanjeev specifically needs to rerun individual jobs.

## Recommended next work

1. Read reports 1–3 and use report 3's final matched-budget tables to choose a
   clearly stated QFT-96 baseline.
2. Improve Dynamic without changing the metric contract: validate candidate
   admission/preparation policies against latency, makespan, fidelity,
   completion, waste and congestion together.
3. Only after freezing a QFT-96 improvement, replicate the same frozen
   pipeline on the other workloads (including QPE), retaining manifests and
   report/data links exactly as done here.
4. Treat topology-specific placement, relay data-qubit occupancy and
   reliability-map provenance as explicit future modelling studies rather than
   assumptions hidden in a new result.
