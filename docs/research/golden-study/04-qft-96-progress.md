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

The mapper-generated QFT-96 T-HQA placements have now been exported for all
three mapping seeds. The seed-42 mapper output reproduces the earlier QFT-96
summary exactly: 96 qubits, 766 layers, 1,965 logical migrations and 3,876
shortest-route hops. The placement is held fixed between mesh and torus for each
seed. The exporter validates that all 15 adjacent-hop traces replay to their
corresponding placement. The complete route audit is in
[`mapping_audit.csv`](../../../results/qft96_2seed_2026-10-26/validation/mapping_audit.csv),
and the grouped route visual and complete table are in the PDF report.

The [execution specification](../../../results/qft96_2seed_2026-10-26/execution_spec.json)
and [job manifest](../../../results/qft96_2seed_2026-10-26/manifests/base-evaluation_jobs.jsonl.gz)
declare 15 conceptual route aliases, 11 distinct request traces, 3,058 jobs
and 12,056 policy-seed evaluations. Two physics seeds are an exploratory sample;
their standard deviation is descriptive, not strong inferential evidence.
No QFT-96 latency ranking is reported until matched policy cells complete and
validate.
