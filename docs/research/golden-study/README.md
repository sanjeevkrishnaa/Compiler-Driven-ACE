# Golden ACE study

This is the fresh, consolidated experiment program. Earlier result directories are
historical/audit inputs; they are not silently reused as golden-study observations.

The machine-readable contract is [study_contract.json](../../../results/golden_study_2026-10-25/study_contract.json).
It fixes the metrics, policy names, routing boundary, capacity sweep, and acceptance
criteria before a final run is admitted to the registry.

The implementation-level baseline mapping and its remaining fairness gates are in
[the scheduler audit](00-policy-audit.md). The frozen ten-workload QASM corpus,
the explicit T-HQA/HQA mapping jobs, and the import/mapping tools are all under
[`results/golden_study_2026-10-25`](../../../results/golden_study_2026-10-25).

## Research questions

1. Which EPR policy—ODG, CGP, ACGP, or a compiler-driven Dynamic policy—has the
   best latency, makespan, readiness, waste, and fidelity trade-off?
2. How does the answer change across total communication-memory capacities
   2, 3, 4, 6, 8, 16, 32, and 64 per core?
3. Is measured congestion attributable to endpoints, relay cores, or both?
4. Can routing reduce relay congestion while holding the placement fixed?
5. Does a torus with Dijkstra routing change those answers?

## Execution gates

No final simulation begins until all ten workload traces have an immutable inventory
entry, every route is replay-validated, seed sets are locked, and all four baseline
policy implementations pass the same completion and metric checks. The ten QASM
inputs have been copied with checksums from the historical archive, but they are
inputs only: T-HQA and HQA placements are regenerated into a new hashed contract.

The mapping control plane is deliberately dependency-checked. First run
`python -m tools.golden_study.prepare_inputs --root ...` to verify the archived
input corpus, then `python -m tools.golden_study.map_inputs --root ... --plan` to
inspect every mapping job. `--execute` refuses to run unless qmap and its QASM
parser dependency are installed, rather than falling back to a different parser.

Every accepted result receives one `registry.csv` row, a raw-output path, hashes,
and a corresponding CSV table. A graph without its CSV and numeric table is rejected.

## Status

The contract, source corpus, mapper-job manifest, and route-export code are in
place. Fresh mappings are blocked only by the currently absent optional `pytket`
QASM parser dependency. Workload inventory, final seed sets, exact physical
configuration, and adaptive-policy parameter selection remain intentionally
unfilled rather than guessed.
