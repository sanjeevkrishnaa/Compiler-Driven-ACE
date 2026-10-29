# Compiler study tools

Run these commands from the repository root with the pinned SeQUeNCe 0.8.1
dependency on `PYTHONPATH`.

| Tool | Purpose |
| --- | --- |
| `run_full_chain_latency.py` | Explicit full-chain Dynamic/ODG comparison with four physical memories, configurable compiler allocation, ready-first admission and physical audits. |
| `study_full_chain_latency.py` | Controlled policy/allocation experiments, exact command capture and per-run evidence. |
| `summarize_full_chain_latency.py` | Aggregate completed, physically audited runs into seed tables and summaries. |

The comparison preset defaults to C=2 and a two-layer minimum lead. Select C=4
with `--compiler-memories 4`. The researched EPR-delivery default is `handoff`,
which passes the existing physical pair to the terminal consumer in place.
Explicit `--compiler-pair-consumption swap` reproduces a model requiring a separate
application communication memory. Neither mode simulates data-qubit teleportation.
The research sweep retains historical FIFO/swap defaults for its old variants;
the explicitly named `handoff-c*-l2` variants select corrected consumption.

```text
python -m tools.compiler_study.run_full_chain_latency --compiler-memories 4 --compiler-pair-consumption handoff --seeds 6,7,8,9 --trace results/qft96_2seed_2026-10-26/traces/placements/mesh/T-HQA/qft96/seed_42/routes/xy/requests.txt --config config/final_config/grid_4x4_ace_3.json --output output/handoff_reproduction
```

Use `--dry-run` to inspect the complete simulator command without running it.
The simulator entry point remains `run_trace_comparison.py` at the root; it forwards to `ace/cli/run_trace_comparison.py`. See the [package source map](../../ace/README.md).

See the [study index](../../docs/research/compiler-pregeneration/README.md) and
[committed evidence](../../results/compiler_memory_handoff_2026-10-28/README.md).
