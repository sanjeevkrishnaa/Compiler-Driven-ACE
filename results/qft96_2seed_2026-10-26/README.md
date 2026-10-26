# QFT-96 study output layout

This directory is the authoritative, self-contained output root for the
26-October QFT-96 study. A later benchmark receives the same layout under its
own dated study root; it never writes into another workload's directory.

```text
qft96_2seed_2026-10-26/
├── execution_spec.json          # frozen factors and simulator parameters
├── mapping_contract.json        # mapper/export contract
├── manifests/                   # immutable job plans and source lock
├── traces/                      # placement, migrations, and ACE request traces
├── validation/                  # hashes, route replay, mapping audit
├── raw/
│   ├── base-evaluation/<job-id>/
│   └── dynamic-variants/<job-id>/
├── summaries/                   # validated progress and aggregate tables
├── congestion/                  # trace-level CSVs and heatmaps
└── figures/                     # checkpoint and incremental metric figures
```

## Per-job evidence

Every completed job directory is content-addressed by its job ID and contains:

- `summary.csv`: one row per policy and physics seed;
- `metadata.json`: simulator parameters and trace/config identity;
- `execution.json`: command, source commit, interpreter, SeQUeNCe identity,
  timestamps, and stdout/stderr hashes;
- `stdout.log` and `stderr.log`: the complete child-process logs.

Jobs are written to `raw/.partial/<temporary-id>` first. The directory is
atomically renamed to `raw/<phase>/<job-id>` only after hashes, expected seed
rows, completion rate, and metadata validate. A partial directory is therefore
an active or failed job, never a reportable result.

## How to find results quickly

- Start with `summaries/base-evaluation-progress.csv` and its status JSON.
- Use `manifests/` to resolve a job ID to topology, route, memory allocation,
  policy, trace hash, and seed list.
- Open the corresponding `raw/<phase>/<job-id>/summary.csv` for raw rows.
- Use `raw/<phase>/<job-id>/execution.json` to reproduce the exact command.
- Use `congestion/trace_congestion_summary.csv` and
  `congestion/per_core_congestion.csv` for route demand and heatmaps.

The metric plotting outputs are under `figures/metrics/` and
`figures/dynamic-variants/`. They include latency, p95, makespan, admission
wait, fidelity, protocol/compiler waste, hit/fallback rates, compiler-not-ready
requests, and retries. They are explicitly incremental while the runners are
active; after completion, rerun the plotting commands to produce the final
figures from the complete validated summaries.

The parent launcher currently prints progress to its terminal; the durable
per-job logs above are the authoritative logs. When this study is distributed
across machines, each worker must write only its assigned job IDs into this
same schema. Aggregation then copies validated rows into `summaries/`; it does
not merge arbitrary terminal text or unverified CSVs.

