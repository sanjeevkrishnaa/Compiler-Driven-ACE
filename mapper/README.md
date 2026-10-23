# QM2026: Quantum Circuit Mapping

QM2026 maps logical qubits in a quantum circuit onto a network of capacity-limited quantum cores. It provides four default mapping strategies plus the opt-in T-HQAR route variant, deterministic experiment runners, communication traces, and a tested command-line interface.

## Included algorithms

| Name | Placement decision cost | Physical path and billed cost | Assignment method |
| --- | --- | --- | --- |
| HQA | uniform 0/1/2 transfer cost | shortest-hop path; `d / reliability` | Hungarian matching |
| T-HQA | shortest-hop distance `d` | shortest-hop path; `d / reliability` | Hungarian matching |
| TR-HQA | shortest-path `d / reliability` | same shortest-hop path; `d / reliability` | Hungarian matching |
| GTR-QA | shortest-path `d / reliability` | same shortest-hop path; `d / reliability` | greedy selection |
| T-HQAR | shortest-hop distance `d` | maximum-product-reliability path; that path's `d / reliability` | Hungarian matching |

Each run maps every circuit time slice, beginning with the first. It evaluates
communication cost from the destination actually assigned to each initially
infeasible two-qubit operation: the sum of `distance / reliability` from each
operand's pre-slice core to that destination. The initial placement is retained
only as the pre-circuit `A_0` seed.

## Quick start

Use Python 3.10–3.12.

```bash
make install
make test
make run
```

`make install` creates `.venv` and installs the project with the optional circuit-generation and plotting tools. To use an existing virtual environment instead:

```bash
python -m pip install -e '.[dev,tools]'
python -m qmap list
python -m qmap run --grid 4x4 --benchmark qft
```

## Common commands

```bash
# Inspect supported mappers and an architecture
python -m qmap list
python -m qmap describe --grid 4x4 --topology mesh

# Map a generated workload with all four strategies
python -m qmap run --grid 4x4 --benchmark qft

# Compare shortest-routed T-HQA with maximum-reliability-routed T-HQAR
python -m qmap run --grid 4x4 --benchmark qft --placers T-HQA,T-HQAR --hop-count

# Include the total gate-routing hop count beside communication cost
python -m qmap run --grid 4x4 --topology ata --benchmark qft --hop-count

# Measure HQA, TR-HQA and GTR-QA mapper execution time in isolated workers
python -m qmap run --grid 4x4 --benchmark qft --measure-time

# Map an OpenQASM circuit
python -m qmap run --grid 4x4 --qasm path/to/circuit.qasm --placers TR-HQA,HQA

# Run scaling, reliability, or ablation studies
make scaling
make reliability
make ablation
```

Commands write CSV, JSON, summary, and metadata files beneath `results/` unless `--no-write` is passed. `--seed` controls every random draw, so a command is reproducible from its recorded metadata.

## Exporting inter-core requests

`generate.py` runs HQA and writes its initial logical-qubit placement followed
by every migration, grouped by circuit layer and expanded into one request per
physical link. For example, a migration routed through cores `0 -> 1 -> 2`
produces `(qubit, 0, 1)` and `(qubit, 1, 2)`.

```bash
python generate.py \
  --benchmark qft \
  --initial-placement oee \
  --cores 16 \
  --reliability-min 0.1 \
  --reliability-max 1.0 \
  --seed 42 \
  --output results/qft_requests.txt
```

Mesh is the default topology, and `--cores` is converted to an exact, near-square
mesh (for example, 16 cores becomes `4x4`). Use `--topology line`, `tree`, `torus`,
or `ata` when required. `--qubits-per-core` defaults to 8 and
`--reserved-ancilla` defaults to 2.

## Mapper execution-time measurements

Append `--measure-time` to `qmap run` to compare HQA, TR-HQA and GTR-QA for
one fixed circuit and architecture configuration. It uses process-isolated
`pyperf` workers and reports median, mean and p95 wall-clock time side by side.
The timed scope includes each mapper's route-cost preparation, look-ahead,
initial placement and assignment rounds. It excludes circuit/architecture
setup, validation, metric evaluation, plotting and result I/O. Results include
raw `pyperf` samples plus CSV and reproducibility metadata under
`results/timing/` by default. Use `--timing-processes`, `--timing-values`,
`--timing-warmups`, and `--timing-min-time` to adjust the protocol.

## Reproduction experiments

Two complete, deterministic experiment runners are included. Their outputs are written below
`results/`, which is ignored by Git.

```bash
# Run all 64 Table 1 topology, size, and benchmark cells with the selected settings.
make table1

# Run all benchmarks, initial placements, normalizations, reliability bands, and cells.
# This performs 1,536 mappings and may take a substantial amount of time.
make extensive-run
```

`make table1` writes `results/table1/measurements.csv` and `report.md`, including each
benchmark's configuration. `make extensive-run` writes `measurements.csv`, `summary.csv`,
and `report.md` under `results/extensive-run`; its report gives the highest mean measured-gain
configuration for each benchmark. The line topology always uses `U[0.95, 1.00]`.

## Project layout

```
qmap/
  architecture/  core network construction and link reliability
  circuit/       circuit representation, OpenQASM loading, benchmarks, slicing
  metrics/       paths, reliability, transfer cost, look-ahead interactions
  placement/     mapping algorithms and assignment solvers
  experiments/   scaling, reliability, and ablation runners
  io/            result and communication-trace writers
  cli/           command-line interface
tests/           unit and integration tests
```

## Mapping model

An architecture is an undirected graph of quantum cores. The built-in `ata` topology
(also accepted as `all-to-all`) connects every pair of cores directly, so every
inter-core transfer has one hop. HQA, T-HQA, TR-HQA, and GTR-QA route transfers
on a shortest-hop path, choosing the most reliable path when several paths have
the same hop count. T-HQAR instead chooses the maximum-product-reliability path,
using `-log(p(e))` as the additive path weight and hop count as its tie-breaker.
If `p(e)` is the reliability of each link on the selected path, its path
reliability is the product of link probabilities and its expected transfer cost is:

```
cost(source, destination) = hops(source, destination) / path_reliability(source, destination)
```

The implementation evaluates this expression in log space to avoid
underflowing a long path reliability to zero. Costs that exceed float64's
representable range are saturated at a documented finite ceiling so they stay
usable by the assignment solver without introducing `inf` or `NaN`.

Placement and physical routing are separate stages. T-HQA and T-HQAR use the
same shortest-distance placement matrix and therefore produce the same mapping
for the same initial placement and configuration. They differ only when the
selected physical route has a more reliable alternative to the shortest route.
Explicit initial-placement strategies such as `oee_cost` remain a separate,
user-selected preprocessing step.

The mapper processes an ASAP time-sliced circuit. When the operands of a two-qubit gate reside on different cores, it chooses a destination core subject to capacity, optionally using future interactions as a look-ahead attraction term. The initial workload reserves `reserved_ancilla` qubits per core as teleportation headroom; subsequent mapping uses the physical core capacity, allowing temporary storage during a placement transition.

Evaluation reports four route metrics. For every non-empty operand path selected for a resolved inter-core gate, with edges `e`, it accumulates:

- expected communication cost: `hops / product(p(e))`;
- EPR latency: `sum(1 / p(e))`;
- hop count: the number of edges;
- path quality: `product(p(e))`.

The run totals are sums over all such selected operand paths. An operand already resident at the selected destination has no physical path and contributes zero to all four totals. EPR latency and path quality are always included in CLI, CSV, and JSON results. Pass `--hop-count` to include hop count as well. Communication traces include all four values per migration and their aggregate trace totals.

## Development

```bash
make test       # unit and integration tests
make lint       # Ruff checks, if installed
make clean      # remove generated runtime artifacts only
```

The runtime package has no import-time file generation. Quantum SDKs are isolated to the OpenQASM loader and benchmark generator; the mapping core and test suite use NumPy, SciPy, and NetworkX.
