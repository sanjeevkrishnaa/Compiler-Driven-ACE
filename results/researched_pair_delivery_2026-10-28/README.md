# Source-backed in-place EPR delivery verification

[Research, primary sources, implementation and latency scope](../../docs/research/compiler-pregeneration/pair-consumption-research-2026-10-28.md).

`evidence.zip` contains eight fresh, complete QFT-96 trials, four simulator seeds
for ODG and compiler C=4, all with zero physical invariant violations. It includes
timing/decision/pair records, metadata and source fingerprints, the input trace,
configuration, and implementation/test snapshots. `SHA256SUMS.txt` verifies the
archive; `MANIFEST.json` inside it hashes every member. All member hashes were
checked after writing the archive. `compiler-tests.log` records 161 passing tests.
`repository-tests.log` records the final full repository suite: 188 tests passed.

The default is in-place EPR ownership transfer. Metadata version 5 explicitly
labels these as **entanglement-delivery** results and records that data
teleportation and data-memory occupancy are not simulated. The terminal
benchmark consumer discards the delivered pair; it is not a teleportation
application that frees a live received data qubit.
