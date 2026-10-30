# Reservation-window evidence, 2026-10-29

See the [measurement report](../../docs/research/compiler-pregeneration/reservation-window-2026-10-29.md)
and [derived tables](../../docs/research/compiler-pregeneration/data/reservation-window-2026-10-29/).

`evidence.zip` contains 54 explicit-window compiler trials plus the final
compiler/ODG default smoke comparison: exact commands, input traces, pair
lifecycles, timing and admission records, metadata, 56 clean audits, configuration,
aggregate tables, test logs and source snapshots. `manifest.json` lists every
member's SHA-256 and length. ZIP CRCs and every member hash were verified after
writing; `SHA256SUMS` fingerprints the archive.

`evaluation_sources/` matches the source hashes recorded during all 54 window
trials before default activation. `final_sources/` matches the default smoke
metadata and includes study tools. The evaluated source commit was
`5fb8a629d87f821315b48eb287aba6961c8e839b` plus the recorded pair-booking
instrumentation. Final default activation is a subsequent working-tree change;
source fingerprints, rather than the base commit alone, identify it.

Inputs are frozen 96-qubit T-HQA seed-42 XY traces from the dated routing archive.
`inputs_manifest.json` identifies their exact source members and hashes. The
baseline pair-age profile came from seeds 60–63 in that archive. Preserve the
pinned SeQUeNCe dependency and regenerate absolute command paths for another
machine. Selection seeds 60/61 and held-out seeds 64/65 are distinct; default
smoke uses QFT96 seed 6. No alternate placements were evaluated.
