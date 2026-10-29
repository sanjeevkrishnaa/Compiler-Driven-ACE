# Extra-memory revert evidence

[Analysis and full allocation table](../../docs/research/compiler-pregeneration/extra-memory-revert-2026-10-28.md).

`evidence.zip` preserves the 20 fresh QFT-96 policy/seed runs, exact commands,
metadata/source hashes, complete timing records, admission decisions, physical
audits, compiler pair records, original input trace, configuration and source
snapshots. `SHA256SUMS.txt` verifies the archive. The compiler and routing test
logs are included alongside the archive.

All 20 runs complete every hop and have zero invariant violations. These runs
use explicit separate application-memory consumption (`swap`). Subsequent
source-backed research restored in-place EPR delivery as the default; this
archive remains the frozen extra-slot experiment.
