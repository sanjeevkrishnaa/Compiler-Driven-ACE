# Compiler-Driven ACE project structure

This is the source and study map for the repository. Current compiler work is
organized under `tools/compiler_study/` and
`docs/research/compiler-pregeneration/`. The dated QFT-96 campaign below remains
the frozen historical input/evidence tree, not the current handoff implementation.

## Current compiler entry points

| Location | Purpose |
| --- | --- |
| `run_trace_comparison.py` | Simulator-facing entry point; module locations remain unchanged. |
| [tools/compiler_study/](../tools/compiler_study/README.md) | Full-chain comparison, controlled sweeps and audited aggregation. |
| [Compiler research index](research/compiler-pregeneration/README.md) | Current handoff correction and chronological historical studies. |
| `docs/research/compiler-pregeneration/data/` | Derived seed rows, aggregate metrics and audit outcomes. |
| [Handoff evidence](../results/compiler_memory_handoff_2026-10-28/README.md) | Committed raw-record archive, original commands and source snapshots. |
| [examples/](../examples/README.md) | Small request-format samples. |
| [test/](../test/README.md) | Active tests and existing fixture paths. |

## QFT-96 study artifact tree

```text
qft96_2seed_2026-10-26/
├── README.md                         # inspect, resume, and validate this study
├── execution_spec.json               # frozen experimental factors and physical parameters
├── execution_scope.json              # official M<=32 scope and archived M64 exclusion
├── mapping_contract.json             # placement/migration/route-trace input contract
├── manifests/
│   ├── base-evaluation_jobs_max-m32.jsonl.gz  # official immutable base-job manifest
│   ├── base-evaluation_jobs.jsonl.gz          # original manifest, including archived M64 jobs
│   ├── base-evaluation_plan.json              # human-readable planning metadata
│   ├── base-evaluation_source-lock.json       # hashes of source inputs used by the run
│   └── dynamic-variants_jobs.json             # 13 Dynamic-policy variant jobs
├── traces/
│   └── placements/                   # T-HQA placements, migrations, and routed ACE hop traces
├── validation/
│   ├── mapping_audit.csv             # route/migration validation evidence
│   └── mapping_record.json           # audited mapper/export metadata
├── raw/
│   ├── .partial/                     # active or interrupted jobs; never report these
│   ├── base-evaluation/<job-id>/     # validated base cell: metadata, logs, seed CSVs, summary
│   └── dynamic-variants/<job-id>/    # validated Dynamic-policy variant cell
├── summaries/
│   ├── base-evaluation-progress.csv  # live completion ledger
│   ├── base-evaluation-status.json   # machine-readable live status
│   ├── qft96_m4_checkpoint.csv       # matched M=4, C=3 policy checkpoint
│   └── qft96_m4_seed_rows.csv        # checkpoint seed-level measurements
├── congestion/
│   ├── per_core_congestion.csv       # layer/core demand measurements
│   ├── trace_congestion_summary.csv  # trace-level congestion aggregation
│   ├── heatmaps/                     # total, source/destination, and relay heatmaps
│   └── manifest.json                 # congestion-analysis provenance
├── figures/
│   ├── metrics/                      # base ACE metric plots, generated after completion
│   ├── dynamic-variants/             # Dynamic-policy plots and tables
│   └── qft96_*.{png,pdf}             # checkpoint and route-structure figures
└── logs/
    ├── combined-launcher.log         # end-to-end launcher log
    ├── base-mesh.log                 # mesh execution phase log
    └── base-torus.log                # torus phase log, created after mesh finishes
```

`raw/base-evaluation/<job-id>/` is trustworthy only after its hash, metadata,
expected two physics-seed rows, and completion have been validated. An item in
`raw/.partial/` is still executing or interrupted and must not appear in a
table or graph.

## Important source files

| Path | What it does | When to read it |
|---|---|---|
| `README.md` | Repository entry point and project-level usage notes. | First. |
| `docs/research/qft96-experimental-design.md` | Formal QFT-96 matrix, timing metric, routes, congestion definition, and scope decision. | Before interpreting results. |
| `results/qft96_2seed_2026-10-26/README.md` | Reproducibility guide for the dated study root. | Before running or resuming QFT-96. |
| `tools/golden_study/run_qft96_all.sh` | Resumable QFT-96 launcher: mesh, torus, variants, summaries, figures, report. | When running the experiment. |
| `tools/golden_study/plan_execution.py` | Builds immutable job manifests from the experiment specification. | To understand scheduled combinations. |
| `tools/golden_study/run_execution.py` | Validates, launches, resumes, and atomically promotes base jobs. | To understand job safety/resume behavior. |
| `tools/golden_study/summarize_execution.py` | Converts validated raw base jobs into policy-level result rows. | Before trusting aggregate CSVs. |
| `tools/golden_study/run_qft96_dynamic_variants.py` | Runs the 13 additional Dynamic preparation policies at fixed `M=4, C=3`. | For Dynamic-policy experiments. |
| `tools/golden_study/summarize_qft96_variants.py` | Produces Dynamic-variant tables and figures. | After variant runs. |
| `tools/golden_study/analyze_qft96_congestion.py` | Measures per-layer/per-core route demand and emits relay/source-destination heatmaps. | For congestion analysis. |
| `tools/golden_study/plot_qft96_metrics.py` | Plots latency, readiness, waste, fidelity, and related base metrics. | For final QFT figures. |
| `run_trace_comparison.py` | Simulator-facing runner for one trace, policy/allocation, and seed cell. | Core experiment execution path. |
| `compiler_scheduler.py` | Compiler-driven EPR scheduling, preparation triggers, lookahead, and allocation logic. | Main Dynamic algorithm study. |
| `compiler_trace.py` | Parses compiler migration/hop traces and exposes layer/request structure. | To understand scheduler input. |
| `request_scheduler.py` | Per-qubit eligibility, ordering, and admission timing. | To understand corrected latency. |
| `resource_manager.py` | Memory/resource admission and reservation management. | To study queueing and contention. |
| `reservation.py` | Reservation lifecycle and resource accounting. | To study allocation correctness. |
| `node.py` | Quantum-network node/core construction and attached managers. | To understand simulator core objects. |
| `generation.py` | EPR-generation behaviour and physical-generation events. | To study EPR time/fidelity parameters. |
| `traffic.py` | Legacy traffic-generation/helper logic. | Historical context; not the trace-driven QFT path. |
| `mapper/` | External/dependent mapper code, including HQA/T-HQA placement workflow. | Before changing placement. |
| `tools/mapper_ace/export.py` | Converts mapper placement/migrations into ACE trace contracts and routing alternatives. | To change routing or trace export. |
| `mapper/verification/verify_mapper.py` | Validates mapper output and placement/routing invariants. | Before accepting mapper data. |
| `config/final_config/` | Mesh and torus physical simulator configurations. | Before changing assumptions. |
| `data/tracegen/` and dated `results/*/traces/` | Versioned reusable and campaign-specific compiler traces. | When selecting a workload. |
| `docs/latex/ace_report/` | LaTeX sources, generated tables/figures, and compiled research PDF. | When writing the report. |

## Current execution flow

```text
T-HQA placement
  -> tools/mapper_ace/export.py
  -> placement/migrations/routed adjacent-hop trace
  -> run_trace_comparison.py
  -> compiler_scheduler.py + ACE resource/scheduler modules
  -> raw/<phase>/<job-id>/ validated result
  -> summarize/plot/congestion tools
  -> CSV tables + figures + LaTeX report
```

## Removed versus retained historical root files

The October 28 directory cleanup groups the compiler CLI tools under
`tools/compiler_study/` and their reports/data under
`docs/research/compiler-pregeneration/`. Root simulator modules are unchanged.
The former `sample.json` is retained at `examples/requests/sample.json`, and
`dummy.txt` is retained as `docs/reference/historical-experiment-notes.txt`.
Unreferenced console dumps (`dummy`, `filter.txt`, `temp.txt`, `tt.txt`), the
empty `test_event_driven.py`, and the one-off `temp.py`/`my_circuit.jpg` drawing
were removed after reference checks. Their old contents remain in Git history.
Versioned result logs, mapper sources, historical study inputs, and request
fixture paths remain intact. The verified handoff evidence is committed under
`results/compiler_memory_handoff_2026-10-28/`.

The unused root `main*.py` runners and `hello.py` were removed in commit
`5d62f6e` after confirming that current tools and tests do not import them.
Their Git history remains recoverable. `parallel_*.py`, PIR runners, legacy
traffic/configuration helpers, and root simulator modules remain until a
separate dependency audit classifies them; they were not removed by this
cleanup.
