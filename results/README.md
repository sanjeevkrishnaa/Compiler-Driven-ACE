# Experiment evidence

Raw records are grouped by dated study. Each current evidence folder includes a
README, a compressed archive, a SHA-256 checksum and validation logs. Human-readable
analysis, derived tables and figures belong under `docs/research/`; executable
workflows belong under `tools/`. Archived source snapshots record the code used
for that experiment and need not match later edits.

| Study | Contents | Analysis |
| --- | --- | --- |
| [Researched pair delivery](researched_pair_delivery_2026-10-28/README.md) | Current in-place EPR delivery, eight full-trace confirmations and physical-state regressions. | [Memory lifecycle and metric scope](../docs/research/compiler-pregeneration/pair-consumption-research-2026-10-28.md) |
| [Heavy routing](heavy_routing_2026-10-28/README.md) | Seven routes on QFT, Draper and QAOA; 192 audited trials and frozen inputs. | [Comparison and heatmaps](../docs/research/routing/heavy-workloads-2026-10-28/README.md) |
| [Extra-memory experiment](extra_memory_revert_2026-10-28/README.md) | Explicit separate-slot consumption; 20 full-trace trials. | [Swap allocation comparison](../docs/research/compiler-pregeneration/extra-memory-revert-2026-10-28.md) |
| [Original handoff correction](compiler_memory_handoff_2026-10-28/README.md) | Earlier C=1..4 validation and holdout evidence. | [Handoff report](../docs/research/compiler-pregeneration/compiler-memory-handoff-2026-10-28.md) |

Older golden-study, QFT-96, congestion and benchmark directories remain frozen
historical evidence. Their own manifests and READMEs define their inputs and
validation scope. Do not mix their configurations or timing definitions with
the current EPR-delivery results.

Local duplicate runs under ignored `output/` may be removed only after verifying
the retained archive and hashes. Temporary caches are rebuildable; unique raw
research records, circuit inputs, provenance and test fixtures are not junk.
