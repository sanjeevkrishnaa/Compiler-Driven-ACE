# QAOA exact generation-lead sweep evidence

The workbook is saved at
`outputs/01a1a8b4-eb78-7a00-9b8b-8e0b77555f04/QAOA_generation_lead_sweep.xlsx`.
The narrative report is `docs/qaoa-lead-sweep-2026-11-10.md`.

`runs.csv` retains all measured metrics for the 18 route/lead cases.
`aggregate.csv` contains the transfer-count-weighted route aggregation.
`evidence.json` contains measurements, source locators, fingerprints and ranking.
Each case directory preserves the exact simulation command, runtime/source
metadata, summary and physical/order audit. These compact files are byte copies
of the original result files. Full event, timing and pair traces remain at the
original locations recorded in `manifest.json`.

The selected objective is lowest pooled mean request latency, not a composite
latency/waste score. The observed winner is L-9, with L-8 only about 0.13% slower
and lower pooled waste. XY individually favors L-9; History favors L-8. All runs
use physics seed 60 and mapping seed 42. Defaults were not changed.

`collect.py` performs independent validation and aggregation against the original
source locators in the manifest. `write_report.py` writes the CSVs and report.
`build_workbook.mjs` authors the Excel workbook with the bundled
`@oai/artifact-tool` library. To regenerate, use the bundled Node runtime and a
local node_modules junction to the bundled package directory, as required by the
spreadsheet skill. `verify_xlsx.py` checks exported cached values, chart bindings,
colors, panes, formula errors and ZIP integrity. No native Excel application
recalculation check was performed.

To reproduce physical cases, use each case's command.json from the ACE worktree
with the recorded interpreter, pinned engine on PYTHONPATH and a fresh output
directory. The compiler source fingerprints in metadata are authoritative; the
L-2/L-3 data were reused only after confirming identical implementation sources.
