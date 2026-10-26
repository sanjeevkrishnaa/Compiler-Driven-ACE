# QFT-96 focused execution

The first attempted reduced-seed run was stopped after validation found that the
Golden `qft` input is a 48-qubit circuit, not QFT-96. Its partial outputs are
not QFT-96 evidence and must not be aggregated.

## Frozen contract

- Required workload: the separate mapper-generated `qft_96` circuit (96 logical
  qubits), not the 48-qubit Golden `qft` workload.
- Required placement: T-HQA, mapping seeds 42, 43 and 44.
- Mesh routes: XY, YX, shortest-reliable and maximum-reliability.
- Torus route: Dijkstra only.
- Communication memories: 2, 3, 4, 6, 8, 16, 32 and 64 per core.
- Compiler allocations: every value from 0 through `M-1`; ODG uses zero.
- Policies: ODG, CGP, ACGP, Dynamic full-chain and Dynamic first-hop.
- Evaluation seeds: exactly 0 and 1 for this focused run.
- Source and route hashes are recorded in the generated manifest.

The repository currently contains a complete routed QFT-96 trace set only for
the existing reconstructed placement under
`results/routing_study_2026-10-25/qft96/` (seed 42). The mapper comparison
reports T-HQA summaries for seeds 42--44, but does not archive the corresponding
per-layer partitions and route traces for seeds 43 and 44. Those partitions must
be exported before a three-seed QFT-96 matrix can be generated. No QFT-96
ranking is reported until the 96-qubit input, all selected placement seeds,
route hashes and all jobs validate.
