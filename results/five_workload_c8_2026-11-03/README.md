# Five-workload C=8 evidence, 2026-11-03

[Metrics table](../../docs/research/workload-metrics/five-workload-c8-2026-11-03/README.md)
and [definitions](../../docs/research/workload-metrics/five-workload-c8-2026-11-03/definitions.md).

4x4 mesh, 14 data slots plus 8 communication memories/core, 208 logical qubits,
T-HQA/OEE mapping seed 42, C=8, physics seed 60. XY/History, ODG/compiler: all
20 trials complete and audited. History routing uses capacity eight. Chain
coverage is sampled at layer opening before admission/preparation. Waste rates
are disjoint percentages of generated compiler pairs. See profile.json and
metric definitions for all assumptions and denominators.

The archive includes the five circuits, mappings and manifests; benchmark
factory sources; routed traces and demand; exact commands; timing, admission,
chain snapshots, pair lifecycles and audits; runtime metadata; source snapshots
matching runtime fingerprints; tests and derived tables. The exact routing and
simulation driver is reproduce-routing-and-simulation.py. Input generation is
recorded in sources/tools/workload_metrics/README.md and input study metadata.

All ZIP CRCs and member SHA-256 values were verified after writing. SHA256SUMS
records the archive hash. The engine remains pinned SeQUeNCe 0.8.1 at
cf5283cdfd6692a82a090d15fb09fbc01bd322fc. Quantum Volume uses Qiskit generation;
this is not a measured hardware Quantum Volume score. Local gates and data
teleportation are not simulated. 208 simulator and 19 routing tests passed.
