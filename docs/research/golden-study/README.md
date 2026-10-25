# Golden ACE study

This is the fresh, consolidated experiment program. Earlier result directories are
historical/audit inputs; they are not silently reused as golden-study observations.

The machine-readable contract is [study_contract.json](../../../results/golden_study_2026-10-25/study_contract.json).
It fixes the metrics, policy names, routing boundary, capacity sweep, and acceptance
criteria before a final run is admitted to the registry.

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
policy implementations pass the same completion and metric checks.

Every accepted result receives one `registry.csv` row, a raw-output path, hashes,
and a corresponding CSV table. A graph without its CSV and numeric table is rejected.

## Status

The contract and registry scaffold are in place. Workload inventory, final seed
sets, exact physical configuration, and adaptive-policy parameter selection remain
intentionally unfilled rather than guessed.
