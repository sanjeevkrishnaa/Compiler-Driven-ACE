# Final 224-qubit matrix

Run from the repository root on main, using the study Python environment:

```powershell
git pull --ff-only origin main
git submodule update --init --recursive
python -B tools/run_final_matrix.py --jobs 2 --output output/final-results-224
```

The environment needs the mapper/MQT dependencies and pinned SeQUeNCe 0.8.1;
use the repository's `make setup` if they are not installed. No Excel or Node
installation is required. CSV files open directly in Excel. If the engine lives
elsewhere, supply `--engine-root C:/path/to/SeQUeNCe-0.8.1`.

The default matrix is 180 simulations per physics seed:

- Ten committed 224-qubit circuits: BV, DJ, GHZ, Graphstate, BMW Quark Cardinality,
  Draper QFT Adder, QFT, QAOA, Exact QPE, BMW Quark Copula.
- History and XY routes from the same T-HQA placement and migrations (mapping seed 42).
  History accumulates all past layers; routing uses its existing capacity-4 score
  for both communication-memory budgets, so memory comparisons share a trace.
- 4x4 mesh, 16 data slots/core: 14 initially occupied and 2 spare; 224 logical
  qubits total. Communication slots are additional: 4 or 8 per core.
- ODG-4, CGP-4, ACGP-4, CD-4, ODG-8, CGP-8, ACGP-8, CD-8 and CD-unlimited.
- Pregeneration quotas: 3/4 and 6/8 for CD and autonomous CGP/ACGP caches.
  `--autonomous-cache legacy3` restores the old fixed 3-slot CGP/ACGP cache.
- CD uses exact L-2 on active layers, trace order, borrowing, immediate refill,
  completion cleanup, demand priority, and the existing 50 ms reservation window.
- CD unlimited uses 256 communication slots/core by default. Each run must pass
  an offline comparison against a sufficient memory bound and a physical
  booked-plus-outstanding capacity check. A saturated bound fails explicitly;
  use a NEW output directory with `--unlimited-slots 512` if needed. This is a
  validated finite approximation, not a simulator infinity setting.

Physics seed defaults to 60. For repeated-seed final evidence:

```powershell
python -B tools/run_final_matrix.py --seeds 60,61,62 --jobs 2 --output output/final-results-224-3seed
```

This is 540 runs. Every row remains a separate seed observation; no silent
averaging or confidence intervals. Increase `--jobs` only if RAM permits.

Console output shows a completed-run bar/percentage, case IDs and per-running-case
completed transfer counts, refreshed every five seconds. Mapping progress names
the current workload. `progress.json` is machine-readable. Resume after Ctrl+C
by issuing the exact same command. Fully audited, validated cases are reused;
interrupted cases restart. Changed source, traces or settings are rejected. The
job count may change on resume. Use a fresh output directory for a new experiment.
Keep results.csv closed in Excel while runs are updating it.

Outputs under `--output`:

- `results.csv` (UTF-8 BOM for Excel) and `results.json`: updated after every
  validated run, including raw simulator metrics and source-folder references.
- `specification.json`: settings and simulator/mapper/circuit/engine source hashes.
- `inputs/`, `routed/`: mappings, routes and frozen traces.
- `runs/<workload>/<route>/<case>/seed_<seed>/`: logs, command, metadata, summary,
  request timings, pair lifecycle counts, physical audit and validation marker.

Metric definitions:

| Column | Definition |
|---|---|
| `latency_ms` | Mean transfer eligibility-to-completion latency, including admission/control/retries |
| `makespan_ms` | Total workload completion time |
| `avg_fidelity` | Mean delivered EPR fidelity including fallback (0–1) |
| `coverage` | Fraction with a physically cached pair ready before first application submission; readiness, not guaranteed adoption |
| `expiry_pairs` | Expired/released unused pairs; legacy expiry can include rejection/failed handoff |
| `cancelled_pairs` | Generated pairs discarded after target completion; still waste |
| `unused_pairs` | Generated cached pairs remaining at workload termination |
| `eviction_pairs` | Zero: no separate eviction operation is implemented |
| `wastage` | (Expiry + cancellation + remaining unused + eviction) / pregenerated pairs |

Fractions use 0–1; multiply by 100 for percentages. With no generated cached pairs,
wastage is blank (undefined), not a measured zero. ODG demand-generated pairs
are excluded from the pregeneration waste denominator. Compiler lifecycle counters
are authoritative for CD; the shared physical pair observer supplies CGP/ACGP
counts. Raw protocol metrics are also preserved. EPR delivery is simulated;
local data teleportation gates/reset time and quantum data occupancy are not.

Inspect the specification without running simulations:

```powershell
python -B tools/run_final_matrix.py --dry-run
```

Subset example (use a separate output directory):

```powershell
python -B tools/run_final_matrix.py --workloads ghz --routes xy --cases ODG-4 CD-4 CD-unlimited --output output/final-smoke
```

## Capacity-matched eight-slot rerun (2026-11-13)

The final runner now uses cumulative History routing with capacity **4** for
four-slot cases and **8** for eight-slot cases. XY is independent of this score.
Mapping still uses the same seed-42 placement with 16 data slots per core;
the exported 20-slot header is the mapper's 16+4 reference, not runtime memory.
Physical seed indexing remains at the four-memory reference to preserve the
previous random-stream convention. Runtime slots and History routing capacity
are separate settings; both now equal eight in the eight-slot History runs.

Run only ODG/CGP/ACGP/CD with eight slots (240 simulations):

```powershell
python -B tools/run_final_matrix.py --cases ODG-8 CGP-8 ACGP-8 CD-8 --routes history xy --seeds 60,61,62 --jobs 4 --output output/final-results-224-3seed-history-c8
```

Use a **new** output directory; never reuse the old C4-routed output. Repeating
this exact command resumes validated completed jobs and restarts interrupted
jobs. Do not edit simulator sources during the run. CSV output is
`output/final-results-224-3seed-history-c8/results.csv`; it records
`history_routing_capacity` (blank for XY) and `trace_sha256`. The output
specification and routed-trace manifest also record capacity. C8 traces live
under `routed-c8`, separately from legacy `routed` (C4).

Keep the old complete CSV. The corrected final matrix will replace only its
240 eight-slot observations, keyed by workload, route, case and physics seed,
with these 240 new rows; retain its 240 four-slot rows and 60 CD-unlimited rows.
CD-unlimited intentionally retains its original C4-routed ideal-resource
reference; this command does not rerun or relabel it as C8. Its routing is
therefore different from the corrected eight-slot History results, and it
cannot be described as a same-trace memory-only comparison against those rows.
Earlier eight-slot History numbers and their derived plots/sweeps must not be
presented as capacity-matched C8 evidence. XY traces should remain unchanged.
