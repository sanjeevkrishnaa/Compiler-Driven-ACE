# ACE congestion budget study — 2026-10-23

378 runs, 0 failures. Produced by `tools/ace_congestion_budget/run_budget_sweep.py`
on branch `codex/compiler-fixes-congestion-study`.

Findings and interpretation: [`docs/reports/ace-congestion-budget-study.md`](../../docs/reports/ace-congestion-budget-study.md)
Column meanings: [`docs/reference/metrics-glossary.md`](../../docs/reference/metrics-glossary.md)

| File | Contents |
| --- | --- |
| `results.csv` | 378 rows x 58 columns, one row per (workload, mapping seed, budget, strategy, physics seed) |
| `verification.txt` | validity checks and summary tables as generated |
| `run_metadata.tar.gz` | per-run `metadata.json`: resolved parameters, source file hashes, seed algorithm |

## Read this before using the numbers

**This study does not measure congestion.** ACE applies `serialize_core_conflicts`
unconditionally whenever a compiler controller is attached, which rewrites each
trace layer into batches where no core appears twice. Peak demand per core falls
from 24 to 1, so a core never needs more than one communication memory and the
budget cannot bind.

Two checks establish this:

- on-demand latency is identical to every digit across budgets 2, 3, 4 and 32;
- GHZ, which has zero overloaded layers, still responds to the budget under
  `dynamic`. The zero-congestion control failed.

The budget axis is acting as a cap on planner coverage, not on contention:
correlation(planner coverage, readiness) = +1.0000 and
correlation(readiness, latency) = -0.9975.

Read the `dynamic` rows as a **pre-generation coverage sweep**. Congestion cost
has only been measured on the native SeQUeNCe backend, in
`docs/reports/congestion-memory-sweep.md`.

Never compare these milliseconds with native SeQUeNCe milliseconds.
