# Handoff: ACE correctness, QFT-96 study, and repository cleanup

**Date:** 26 October 2026  
**Repository:** `sanjeevkrishnaa/Compiler-Driven-ACE`  
**Only active branch:** `codex/ace-scheduler-correctness`  
**Commit at handoff creation:** `0565775ef7a5f7ebc3b207cbfe0393b1287a2cdf`  
**Local checkout:** `/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE-correctness`  
**SeQUeNCe checkout used by the ACE virtual environment:** `/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/SeQUeNCe`

This document is the self-contained continuation context for a new session. It
separates facts already verified from running work and open research questions.

## 1. Non-negotiable user requirements

1. Work only on `codex/ace-scheduler-correctness` until the user explicitly
   requests a merge.
2. Make descriptive commits and push them; do not leave important work only in
   a local checkout.
3. Do not invent parameters, silently hard-code assumptions, reuse stale
   results, or claim conclusions from incomplete data.
4. Every result must be traceable to a manifest, source/config/trace hashes,
   simulator parameters, physics seeds, raw outputs, and validation status.
5. For every graph in the report, include the corresponding table and a link
   to the committed CSV that generated it.
6. The long-term benchmark study covers T-HQA placement, explicit routing,
   mesh and torus, ODG/CGP/ACGP/Dynamic, memory allocation, congestion,
   readiness, waste, fidelity, latency, and makespan.
7. Current execution focus is QFT-96 only. Other benchmarks, including MQT QPE,
   should be expanded only after the QFT-96 pipeline is validated end to end.

## 2. Correct conceptual model established in discussion

### 2.1 Hop-by-hop movement

Rajeswari confirmed that the intended model is hop-by-hop teleportation, as
described in the ISVLSI 2025 work. A routed migration is converted into
adjacent-core requests. ACE is therefore not being used here as one end-to-end
swapping reservation over a complete multihop path.

The unresolved physical question of data-qubit occupancy at relay cores was
explicitly deferred by the user. Do not silently add relay computation-slot
blocking to the present study. Keep the limitation documented.

### 2.2 Communication-memory model

The current study uses one shared pool of communication memories per core.
For the historically important four-memory case, at most three memories are
available to compiler-driven pre-generation and one remains for on-demand
service. The current sweep generalizes total memories and compiler allocations
through explicit manifest fields.

### 2.3 Latency definition

The corrected primary metric is request arrival/eligibility to completion. It
includes RSVP/control delay, admission waiting for communication memory,
generation, retries, and delivery. It does not count time before a request is
eligible, and it does not count how long an EPR pair sat cached before the
request arrived as request service latency.

Parallelism does not require a new latency definition. Report both:

- per-request latency distributions (mean, median, p95/p99 where available),
- workload makespan/throughput for system-level parallel performance.

### 2.4 The historical 5.3-ms quantity

The old pipeline used a 5.3-ms pre-generation lead/buffer and subtracted it in
the local latency accounting. That produced a service-local number rather than
fair arrival-to-completion latency. The corrected QFT-96 study sets
`pregeneration_buffer_ms = 0.0` and does not use the subtraction.

The earlier comparison established four logically distinct combinations:
legacy versus per-qubit scheduling, crossed with historical versus corrected
physical timing. Do not mix those metrics in one headline comparison.

### 2.5 Historical timing checkpoint

The 30-seed QFT-96 comparison previously produced the following reference
values. These are historical/reproduction checkpoints, not the final current
QFT-96 matrix:

| Model | Latency interpretation | ODG | Dynamic | Makespan comparison |
|---|---|---:|---:|---|
| Historical legacy with 5.3-ms lead | old local/service metric | `1.110 +/- 0.011 ms` | `0.691 +/- 0.008 ms` | `30.932 vs 32.900 s` (`-5.98%`) |
| Legacy with corrected physical timing | local metric was about `0.917 ms` for Dynamic; fair metric was separately studied | use committed reproduction artifacts | use committed reproduction artifacts | `7.106 vs 8.950 s` (`-20.60%`) in the fair comparison |
| Correct per-qubit, corrected timing | fair arrival-to-completion | `1.526 +/- 0.016 ms` | `2.570 +/- 0.096 ms` | `4.694 vs 4.337 s` (`+8.22%`) |

The research motivation is to reduce corrected Dynamic latency below corrected
ODG without falsifying assumptions or hiding queueing.

## 3. Mapping and routing contract

### 3.1 Placement

Use T-HQA for further main experiments. HQA/T-HQA places logical qubits onto
cores; routing is a separate post-placement decision. The mapper/export
boundary should expose logical migration endpoints `(qubit, source core,
destination core)` before converting them into adjacent physical hops.

### 3.2 QFT-96 mapper evidence

For archived 48-qubit workloads, `mapping.npz` contains the original mapper
`Partition`. For QFT-96, the original NPZ was not archived, but replaying the
complete historical adjacent-hop trace reconstructs each layer's placement and
logical migration endpoints exactly.

This reconstruction does not recover the mapper's original random link-
reliability map. Consequently:

- XY and YX are valid deterministic alternatives.
- The supplied historical route is a valid control when used.
- Shortest-reliable and maximum-reliability are controlled alternatives under
  a documented reconstructed reliability map, not byte-for-byte reproduction
  of the mapper's original reliability-aware decision.

### 3.3 Routes in the current QFT-96 matrix

- Mesh: XY, YX, shortest-reliable, maximum-reliability.
- Torus: Dijkstra only.
- Mapping seeds: 42, 43, 44.

There are 15 conceptual mapping/routing cells but 11 byte-distinct trace
inputs. Exact duplicate traces are executed once and retain aliases for all 15
conceptual cells. This is deduplication, not missing experimental coverage.

## 4. Current official QFT-96 study

### 4.1 Authoritative root

`results/qft96_2seed_2026-10-26/`

Read these first:

- `results/qft96_2seed_2026-10-26/README.md`
- `docs/research/qft96-experimental-design.md`
- `docs/project-structure.md`
- `results/qft96_2seed_2026-10-26/execution_spec.json`
- `results/qft96_2seed_2026-10-26/execution_scope.json`

### 4.2 Frozen official scope

- Workload: QFT-96.
- Placement: T-HQA.
- Mapping seeds: 42, 43, 44.
- Physics seeds: 0 and 1.
- Total memories/core: 2, 3, 4, 6, 8, 16, 32.
- Compiler allocations: every `C = 0, ..., M-1`.
- Base policies: ODG, CGP, ACGP, Dynamic full-chain, Dynamic first-hop.
- Mesh routes: XY, YX, shortest-reliable, maximum-reliability.
- Torus route: Dijkstra.

Official base manifest:

`manifests/base-evaluation_jobs_max-m32.jsonl.gz`

It contains 1,639 jobs and 6,402 policy-seed evaluations. An exact-subset audit
proved it is byte-for-byte the ordered subset of the original manifest where
`M <= 32`. No other dimension was removed.

### 4.3 M64 scope revision

The original manifest had 3,058 jobs and included M64. The user explicitly
approved dropping M64 from the official complete sweep. At enforcement time,
425 of 1,419 M64 jobs had completed. Those raw outputs remain archived for
provenance but must not enter official summaries, plots, tables, or claims.

The machine-readable record is `execution_scope.json`, including both manifest
hashes. Never use the original manifest for official progress reporting.

### 4.4 Dynamic variants

The 13 auxiliary Dynamic preparation variants are a separate fixed-point
study at `M=4`, `C=3`, over all 11 byte-distinct traces and both physics seeds.
All 143 variant jobs completed.

Variants include baseline layer-start, first-hop-only, predecessor-start,
two-hop predecessor-start, and delay sensitivity variants. They are not crossed
with every M/C allocation. The full memory matrix includes Dynamic full-chain
and Dynamic first-hop; a full Cartesian expansion of all 13 variants would be
new work and must not be implied by current results.

## 5. Live execution state at handoff creation

Snapshot only; recalculate before reporting:

- Official base jobs complete: 1,046 / 1,639.
- Pending: 593.
- Mesh: 998 / 1,192 complete.
- Torus: 48 / 447 complete.
- Dynamic-variant jobs: 143 / 143 complete.
- Launcher PID at snapshot: 84364.
- Base runner PID at snapshot: 84377.
- Six `run_trace_comparison.py` children were active.
- Active phase: mesh.

The single combined launcher command is:

```bash
cd "/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE-correctness"

bash tools/golden_study/run_qft96_all.sh \
  results/qft96_2seed_2026-10-26 \
  "/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE/.venv/bin/python" \
  6
```

Do not run that command while PID 84364 or another matching launcher is alive.
The launcher lock is
`results/qft96_2seed_2026-10-26/.qft96-pipeline.lock`.

## 6. How to inspect progress safely

Always read the scoped manifest from `execution_scope.json`; do not hard-code
the original 3,058-job manifest.

```bash
cd "/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE-correctness"

python3 - <<'PY'
import gzip, json
from pathlib import Path

root = Path("results/qft96_2seed_2026-10-26")
scope = json.loads((root / "execution_scope.json").read_text())
with gzip.open(root / scope["base_manifest"], "rt") as stream:
    jobs = [json.loads(line) for line in stream]
done = sum((root / job["output_path"] / "summary.csv").is_file()
           for job in jobs)
print(f"Official: {done}/{len(jobs)} complete; {len(jobs)-done} pending; "
      f"{100*done/len(jobs):.2f}%")
PY

ps -axo pid,ppid,etime,%cpu,%mem,command | \
  grep -E 'run_qft96_all|tools.golden_study.run_execution|run_trace_comparison|run_qft96_dynamic_variants' | \
  grep -v grep
```

Healthy process structure during a base phase:

```text
one run_qft96_all.sh
  -> one tools.golden_study.run_execution
       -> at most six run_trace_comparison.py children
```

Do not count `.partial` directories as completed jobs. A finalized job has been
atomically promoted to `raw/<phase>/<job-id>/` after validation.

## 7. What the launcher does after simulations complete

The launcher runs sequential phases:

1. mesh base jobs,
2. torus base jobs,
3. Dynamic variants (already complete and will validate/reuse),
4. base summarization,
5. congestion analysis,
6. base metric plots,
7. Dynamic-variant summary/plots,
8. LaTeX report compilation.

The M<=32 scope is passed both to base execution and congestion capacities.
Any M64 raw directories remain archival only.

## 8. Required validation after completion

Before claiming final QFT-96 results:

1. Confirm official status is 1,639/1,639 with zero failed/missing jobs.
2. Recompute and verify manifest SHA-256 values against `execution_scope.json`.
3. Confirm every finalized job has the expected strategies, both physics seeds,
   completion status, config hash, and trace hash.
4. Confirm no M64 row appears in official summary CSVs or figures.
5. Confirm all M/C/policy/route/topology cells expected by the manifest appear
   in aggregation.
6. Inspect failure logs and `.partial/`; do not silently discard failures.
7. Generate latency, p95 latency, admission wait, makespan, readiness, EPR hit
   rate, EPR waste/expiry, memory occupancy where recorded, and fidelity plots.
8. Generate congestion heatmaps for total, source/destination, and relay demand
   for all official routes/topologies/capacities.
9. Put the complete table directly after every figure in the report and link
   the exact committed CSV.
10. Compile the PDF and visually inspect every new/changed page twice.
11. Run targeted tests plus `git diff --check`.
12. Make a descriptive commit and push.

Do not claim that Dynamic is generally better unless the completed corrected
matrix supports that statement. Report negative results honestly.

## 9. Metrics and interpretation required in the final analysis

At minimum analyze:

- mean, median, standard deviation, and p95 request latency,
- admission/memory wait separately from service/generation time,
- makespan and throughput,
- readiness/hit rate,
- EPR generation count, consumption, expiry, and waste percentage,
- achieved fidelity and failure/retry behaviour,
- compiler-memory occupancy/utilization if emitted,
- congestion total and split into relay versus source/destination contribution,
- sensitivity to M, C/M ratio, route, topology, mapping seed, and policy.

Compare paired physics seeds where appropriate. Two seeds are a pipeline and
trend study, not strong final statistical evidence. The report must say this.

## 10. Congestion definition

Congestion is a trace-level demand property, not measured latency. The current
analysis supports:

- hop counting: an internal relay contributes arrival and departure incident
  demand,
- route counting: a routed qubit contributes one demand at every visited core.

Heatmaps have total, source/destination, and relay-only panels. Percentages are
over communication-active layers, not all idle layers padded with zeros.

## 11. Repository cleanup completed

The obsolete root entry points `main.py`, `main2.py`, `main3.py`, `main4.py`,
`main5.py`, `main_dynamic.py`, `main_parallel.py`, `main_test.py`, and
`hello.py` were removed in commit `5d62f6e`. No current pipeline/test imported
them; Git retains recoverable history.

`docs/project-structure.md` now contains:

- the complete QFT-96 artifact tree,
- a table of important source paths and roles,
- the mapper-to-report execution flow,
- the boundary between removed and retained historical files.

Do not remove `parallel_*.py`, PIR runners, traffic/config generators, or root
simulator modules without a separate dependency and provenance audit.

## 12. Important commits from the final session segment

- `8c84716` - added the resumable end-to-end QFT-96 launcher.
- `f357952` - excluded M64 from the official sweep with a hashed scoped
  manifest and updated report/design documentation.
- `5d62f6e` - removed obsolete root `main*.py`/`hello.py` entry points and
  introduced the structure guide.
- `0565775` - expanded the project-structure guide with the QFT artifact tree
  and important-file table.

Use `git log --oneline --decorate` for the complete earlier history. Do not
rewrite already-pushed history while experiments are active.

## 13. Report locations

- Main report PDF: `docs/latex/ace_report/main.pdf`
- Main report sources: `docs/latex/ace_report/`
- QFT-focused chapter: `docs/latex/ace_report/chapters/16_qft96_focus.tex`
- Correctness audit: `docs/research/ace-correctness-audit-2026-10-25.md`
- QFT design: `docs/research/qft96-experimental-design.md`
- Project map: `docs/project-structure.md`

The QFT chapter intentionally separates running/partial data from completed
checkpoints. Update its ledger after final validation; do not turn partial
progress into a final result.

## 14. Immediate next actions for the next session

1. Check the live process tree and scoped completion count.
2. If the existing launcher is healthy, do not start another one.
3. If it stopped, inspect the relevant log and `.partial` outputs before
   resuming the same command; the runner is designed to validate and reuse
   completed outputs.
4. When 1,639/1,639 completes, inspect launcher post-processing rather than
   launching separate competing aggregation commands.
5. Validate all final CSV coverage and metrics.
6. Update the QFT research README and report chapter with completed figures,
   directly followed by tables and repository CSV links.
7. Visually inspect the compiled PDF twice, run checks, commit descriptively,
   and push.
8. Only after the QFT-96 pipeline is trustworthy, replicate the same frozen
   workflow workload by workload, including MQT QPE.

## 15. Known limitations and open research work

- Relay data-qubit/computation-slot occupancy is deferred and not modelled as
  a new blocking constraint in this study.
- The reconstructed QFT reliability map does not reproduce the mapper's
  original random reliability map byte-for-byte.
- Two physics seeds provide limited uncertainty estimation.
- The 13 Dynamic variants are fixed at M4/C3 rather than fully crossed with the
  memory sweep.
- M64 is intentionally incomplete and excluded.
- Dynamic currently loses to ODG in the corrected four-memory checkpoint;
  improving it is the main research challenge, not a result to assume away.
- Future research should use routing, congestion-aware preparation/admission,
  lookahead, chain-depth control, memory allocation, and topology jointly,
  then validate improvements on the full benchmark set.

## 16. Safety rules for continuation

- Never delete raw completed outputs simply because they are excluded; retain
  provenance and exclude through machine-readable scope.
- Never run two launchers against the same study root.
- Never summarize the original manifest when the scoped manifest is official.
- Never interpret a `.partial` output as a result.
- Never change simulator timing, coherence, fidelity, memory, routing, or
  scheduler assumptions without updating the specification and producing a
  new manifest/result identity.
- Never describe reconstructed reliability-aware routes as exact historical
  mapper reproduction.
- Never merge branches, delete worktrees, or clean broad directories without
  resolving exact targets and preserving recoverable history.
