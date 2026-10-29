# Golden-study control plane

This directory contains the project-owned control plane for the fresh ACE study.
It does not launch simulations by itself. Its first responsibility is preventing an
unregistered trace, seed, or configuration from becoming a reported result.

```bash
python tools/golden_study/studyctl.py init \
  --root results/golden_study_2026-10-25
python tools/golden_study/studyctl.py validate \
  --root results/golden_study_2026-10-25
python tools/golden_study/studyctl.py render-latex \
  --root results/golden_study_2026-10-25 \
  --latex-output docs/latex/ace_report/generated/golden_study_contract.tex
```

`validate --run-ready` is deliberately stricter. It refuses execution until the
contract names non-overlapping training and evaluation physics seeds, mapper seeds,
a preregistered adaptive-policy threshold, and ten workload traces with hashes.

No runner has implicit workloads, seed ranges, memory capacities, or routing choices.
Those values belong in the study contract and inventory, not in Python constants.

## Frozen base execution

`plan_execution.py` expands `execution_spec.json` into a compressed, immutable job
manifest. `run_execution.py` requires the interpreter and worker count explicitly,
uses atomic partial outputs, and validates every existing result before resume.

```bash
python -m tools.golden_study.plan_execution \
  --root results/golden_study_2026-10-25 \
  --latex-output docs/latex/ace_report/generated/golden_execution_plan.tex

python -m tools.golden_study.run_execution \
  --root results/golden_study_2026-10-25 \
  --manifest results/golden_study_2026-10-25/manifests/base-evaluation_jobs.jsonl.gz \
  --python /absolute/path/to/the/declared/python \
  --workers 4
```

Use `--limit N` for a bounded first batch. A result is reusable only when its full
job/input hashes, expected rows, metadata, completion rates, ACE source lock, and
SeQUeNCe Git revision validate. Filters such as `--workload ghz --topology mesh
--route-policy xy` select a scientifically named resumable batch.

Each completed job is stored as `raw/<phase>/<job-id>/` under the study root.
That directory contains the raw summary and metadata, the exact command and
source/interpreter identity in `execution.json`, and durable `stdout.log` and
`stderr.log` files. Jobs are first written under `raw/.partial/` and atomically
renamed only after validation. The study-root README documents the complete
layout and the lookup path from an aggregate CSV row back to its raw evidence.

After any batch, rebuild the incremental source table and LaTeX progress table:

```bash
python -m tools.golden_study.summarize_execution \
  --root results/golden_study_2026-10-25 \
  --manifest results/golden_study_2026-10-25/manifests/base-evaluation_jobs.jsonl.gz \
  --output results/golden_study_2026-10-25/summaries/base-evaluation-progress.csv \
  --status results/golden_study_2026-10-25/validation/base-evaluation-progress.json \
  --latex-output docs/latex/ace_report/generated/golden_execution_progress.tex
```

A completed memory-sweep slice is accepted for plotting only after
`analyze_memory_sweep.py` proves that ODG and every integer compiler allocation
`C=0,...,M-1` are present with the declared seed count and 100% completion. The
analysis writes both figures as PNG/PDF, plus the exact observed-minimum CSV and a
LaTeX table. All selector values and output paths are explicit command arguments.

## Fresh mapper inputs and trace generation

`prepare_inputs.py` copies only the QASM members explicitly named in
`mapping_inputs.json` from a declared archive. It records both source-member and
extracted-file SHA-256 digests. `map_inputs.py` then generates fresh mapper
`Partition` contracts and route-derived ACE traces from `mapping_jobs.json`.

```bash
PYTHONPATH=mapper:. python -m tools.golden_study.prepare_inputs \
  --root results/golden_study_2026-10-25
PYTHONPATH=mapper:. python -m tools.golden_study.map_inputs \
  --root results/golden_study_2026-10-25 --plan
```

Use `--execute` only after installing the mapper's declared QASM parser
dependency. It does not substitute a parser or silently choose a different
mapping/route. Torus jobs are accepted only with the contract's `dijkstra` policy.
