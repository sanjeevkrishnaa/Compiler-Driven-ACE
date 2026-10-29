# Heavy-routing evidence — 2026-10-28

[Report, recommendation and heatmaps](../../docs/research/routing/heavy-workloads-2026-10-28/README.md)

The [evidence archive](evidence.zip) contains:

- `study/traces/`: all 21 routed full-workload request files, core-demand arrays and link counts.
- `study/simulation/`: 168 primary trials across seven routes, three workloads, ODG/compiler C=4 and four simulator seeds. Each route folder contains exact commands, summaries, source-hash metadata, physical invariant audits, admission decisions, hop timings and compiler-pair records.
- `study/validation/`: 24 fresh-seed QAOA trials on XY, greedy and minhop, with the same evidence.
- `inputs96/`: the three normalized 96-qubit circuits, complete T-HQA placement matrices, mapping validation/provenance and original exported requests.
- `sources/`: routing tools/tests, mapping/analysis helpers, physical runtime modules and configuration snapshots.
- `MANIFEST.json`: SHA-256 and size of every archived file.
- `PROVENANCE.json`: package versions, Python version, runtime identity, source hashes and the checkout base commit. Source snapshots include the new uncommitted research tools.

Figures are stored once in the report directory, in PNG and PDF formats where
applicable, rather than duplicated in this archive. Temporal heatmaps are PNG.

All **192 trials completed every request and passed physical ownership/order
audits with zero violations**. Every generated route preserves migration
endpoints and reproduces its original placement after every layer. The
[routing test log](tests.log) records 19 passing tests.

[SHA256SUMS.txt](SHA256SUMS.txt) checks the archive;
[provenance.json](provenance.json) records its size, member count and environment.
The archive was opened, tested for CRC errors, and every member checked against
its SHA-256 manifest after creation.

The base checkout commit is `36a5ad7`; no production scheduler code was changed
for this comparison. Physical runtime: SeQUeNCe 0.8.1, commit
`cf5283cdfd6692a82a090d15fb09fbc01bd322fc`.

To regenerate plots and tables from archived measurements, extract the ZIP and
run `tools/routing_research/report_heavy_routing.py --output <extracted>/study`
from the repository. To rerun physical trials or regenerate mappings, follow
the [reproduction commands](../../tools/routing_research/README.md) using a new
output folder and the compatible physical dependency.
