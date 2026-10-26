# QFT-96 focused execution

The first reduced-seed run is now dedicated to QFT-96. It is isolated from the
interrupted 30-seed ten-workload study so that the two evidence sets cannot be
mixed.

## Frozen contract

- Workload: `qft` (96 logical qubits).
- Placement: T-HQA, mapping seeds 42, 43 and 44.
- Mesh routes: XY, YX, shortest-reliable and maximum-reliability.
- Torus route: Dijkstra only.
- Communication memories: 2, 3, 4, 6, 8, 16, 32 and 64 per core.
- Compiler allocations: every value from 0 through `M-1`; ODG uses zero.
- Policies: ODG, CGP, ACGP, Dynamic full-chain and Dynamic first-hop.
- Evaluation seeds: exactly 0 and 1 for this focused run.
- Source and route hashes are recorded in the generated manifest.

The planner produced 15 conceptual route aliases, 11 distinct request-trace
hashes, 3,058 jobs and 12,056 policy-seed evaluations. Results are written
under `results/golden_study_2026-10-26_2seeds/`. No QFT ranking is reported
until all jobs complete and the validation rate is 100%.

The complete machine-readable plan is
[`execution_spec.json`](../../../results/golden_study_2026-10-26_2seeds/execution_spec.json),
and the generated job manifest is
[`base-evaluation_jobs.jsonl.gz`](../../../results/golden_study_2026-10-26_2seeds/manifests/base-evaluation_jobs.jsonl.gz).
