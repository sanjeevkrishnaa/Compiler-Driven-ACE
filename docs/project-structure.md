# Compiler-Driven ACE project structure

This guide is the short map of the repository. The current QFT-96 study is
driven by the `tools/golden_study/` pipeline; the root-level historical
runners are not part of that pipeline.

## Start here

1. `README.md` - repository entry point and high-level status.
2. `docs/research/qft96-experimental-design.md` - QFT-96 factors, metrics,
   routing, memory scope, and reproducibility rules.
3. `results/qft96_2seed_2026-10-26/README.md` - the dated experiment ledger,
   manifests, logs, raw outputs, summaries, figures, and report links.
4. `docs/latex/ace_report/` - the compiled research report and its chapter
   sources.

## Current simulation path

```text
mapper/                         T-HQA placement and route/export validation
traces/                         versioned request traces and placement data
config/final_config/             mesh and torus ACE simulator configurations
run_trace_comparison.py          one trace, policy, allocation, and seed cell
tools/golden_study/              planning, execution, validation, summaries,
                                 congestion analysis, plots, and tests
results/qft96_2seed_2026-10-26/  immutable manifests plus dated run artifacts
docs/latex/ace_report/            report source and compiled PDF
```

The official QFT-96 runner is:

```text
tools/golden_study/run_qft96_all.sh
```

It reads `execution_scope.json`, so the official current sweep uses total
memories `2, 3, 4, 6, 8, 16, 32`. The original M64 manifest and raw outputs
remain archived for provenance but are excluded from official aggregation.

## Root files that were deliberately retained

The root simulator modules (`node.py`, `resource_manager.py`,
`reservation.py`, `request_scheduler.py`, `compiler_trace.py`, and related
modules) are implementation dependencies and require a separate dependency
audit before removal. `parallel_*.py`, PIR runners, and old traffic/config
tools are historical experiment entry points; they are documented candidates,
not silently deleted files.

## Removed historical entry points

The unused root `main.py`, `main2.py`, `main3.py`, `main4.py`, `main5.py`,
`main_dynamic.py`, `main_parallel.py`, `main_test.py`, and `hello.py` files
were deleted after checking that current tools and tests do not import them.
Their history remains recoverable through Git.

## How to study a result

For any result, start with its manifest, then inspect the job's `execution.json`,
`summary.csv`, and `stdout/stderr` log under the corresponding `raw/` folder.
Do not treat a directory as reportable unless its execution record, hashes,
both physics-seed rows, and completion validation are present.
