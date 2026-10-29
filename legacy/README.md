# Legacy experiment runners

These scripts preserve older experiment setups. They are not the entry points
used for current compiler or routing results. Their code and timing settings are
retained unchanged, including fixed buffers and machine-specific input paths.
Do not use their output as evidence for the current zero-extra-buffer preset.

| Historical script | Purpose |
| --- | --- |
| [runners/parallel_real.py](runners/parallel_real.py) | Old benchmark runner with a hard-coded traffic path and 5.3 ms extra buffer. |
| [runners/parallel_random.py](runners/parallel_random.py) | Old random-layer runner with a 5.3 ms extra buffer. |
| [runners/parallel_real_old_v.py](runners/parallel_real_old_v.py) | Earlier grid/benchmark sweep with fixed experiment settings. |
| [runners/waste_analysis.py](runners/waste_analysis.py) | Old CGP waste analysis using historical configuration paths and a fixed buffer. |

Root simulator imports and relative input paths expect the repository root as
the working directory. If intentionally reproducing one of these setups, use
module invocation from that directory with the pinned SeQUeNCe dependency:

```text
python -m legacy.runners.parallel_real
```

The historical configuration and hard-coded files must also be available. Moving
these scripts does not update their old assumptions or make them supported current
workflows.

## Current entry points

| Workflow | Entry point |
| --- | --- |
| Trace-driven physical simulation | [run_trace_comparison.py](../run_trace_comparison.py) |
| Full-chain compiler/ODG comparison | [tools/compiler_study/](../tools/compiler_study/README.md) |
| Routing comparisons and congestion heatmaps | [tools/routing_research/](../tools/routing_research/README.md) |
| Other maintained experiment guides | [Documentation index](../docs/README.md) |

Current compiler and routing presets use zero additional pre-generation buffer.
Tests that deliberately configure a nonzero delay remain in the test suite;
they verify that elapsed time is counted correctly. Frozen reports, result
archives, and historical worklogs retain the original script paths as provenance.
