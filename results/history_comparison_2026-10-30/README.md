# History comparison evidence, 2026-10-30

[Report](../../docs/research/routing/history-comparison-2026-10-30/README.md).

24 new History trials plus 72 previously measured matched XY/Greedy/Detour2
trials: all complete and audited. The archive retains circuits and mappings,
benchmark factory sources, routed traces and static demand, exact commands,
per-request timing and pair readiness records, 96 audits, runtime source hashes,
source snapshots, reproduction commands and derived tables. The engine-facing
source fingerprints are identical across all 96 trials. The pinned engine
remains the third_party/SeQUeNCe submodule. Report analysis computes each
migration's sequential-hop latency without double-counting admission waiting.

ZIP CRC and all member SHA-256 values were verified after writing. SHA256SUMS
records the archive checksum; manifest.json records member checksums. Earlier
archives remain frozen. Reproduce using study/history-reproduce.txt.
