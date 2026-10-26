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

## First validated checkpoint

The first complete paired cell fixes four shared memories per core, three
compiler-eligible memories for pre-generating policies, mapping seed 42,
physics seeds 0 and 1, and identical logical migrations for mesh XY and torus
Dijkstra. ODG uses no compiler memories. All ten policy/topology cells and
twenty policy-seed rows passed the execution-record and 100%-completion checks.
The [aggregate CSV](../../../results/qft96_2seed_2026-10-26/summaries/qft96_m4_checkpoint.csv)
and [individual seed rows](../../../results/qft96_2seed_2026-10-26/summaries/qft96_m4_seed_rows.csv)
contain the exact values and source job IDs; the PDF places the corresponding
table immediately after the figure.

| Policy | Mesh XY mean hop latency (ms) | Torus Dijkstra mean hop latency (ms) |
| --- | ---: | ---: |
| ODG | 1.327 | 1.320 |
| CGP | 1.803 | 2.061 |
| ACGP | 1.908 | 2.021 |
| Dynamic full-chain | 1.335 | 1.075 |
| Dynamic first-hop | 1.141 | 1.046 |

This is an exploratory two-physics-seed checkpoint, not the full-sweep result
or a general claim of superiority. Route counts alone did not predict the
policy ordering. The source rows report p95 latency, admission wait, makespan,
readiness, waste and fidelity as well as the mean above.

## Dynamic launch-policy phase

The earlier Dynamic-design work contains more than the two base policies
(`Dynamic-full-chain` and `Dynamic-first-hop`). Those variants are now
registered against the corrected QFT-96 corpus in
[`dynamic-variants_jobs.json`](../../../results/qft96_2seed_2026-10-26/manifests/dynamic-variants_jobs.json).
The old launcher was not reused because it hard-coded older route files,
settings and 30 seeds.

The registered variants are:

`baseline-layer-start`, `layer-delay-1ms`, `layer-delay-2ms`,
`layer-delay-3ms`, `layer-delay-4ms`, `layer-delay-6ms`,
`predecessor-start`, `predecessor-start-first-delay-2ms`,
`predecessor-start-first-delay-4ms`, `first-hop-only`,
`first-hop-only-delay-2ms`, `first-hop-only-delay-4ms`, and
`two-hops-predecessor-start`.

Each variant uses the same per-qubit event admission, M=4, C=3, generation
capacity 3, topology configuration, route trace and evaluation seeds 0 and 1.
The phase contains 143 jobs: 13 variants over 11 byte-distinct traces
(four mesh route families across three mapping seeds plus torus Dijkstra
across three mapping seeds). It is running separately from the frozen base
matrix. No variant ranking will be reported until every selected job passes
the same 100%-completion and provenance checks.
