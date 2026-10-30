# Compiler-Driven ACE

Physical ACE/SeQUeNCe experiments for on-demand, continuous, adaptive-continuous,
and compiler-directed EPR generation in multicore quantum architectures.

The current compiler path uses full-chain preparation, ready-first event
admission, and ownership handoff of a prepared pair's existing communication
memory. Latency is completion minus eligibility, including admission, control
and retries; no preparation window is subtracted.
These metrics measure EPR delivery. Data-qubit teleportation gates, destination
data-memory occupancy, and local reset/transfer costs are not simulated.

The compiler reservation lifetime defaults to **50 ms**; see the [window sweep and validation](docs/research/compiler-pregeneration/reservation-window-2026-10-29.md). Override with `--compiler-reservation-ms`.

## Start here

- [Current compiler implementation and results](docs/research/compiler-pregeneration/compiler-memory-handoff-2026-10-28.md)
- [Source-backed pair consumption, memory lifecycle and metric scope](docs/research/compiler-pregeneration/pair-consumption-research-2026-10-28.md)
- [Seven-route QFT/Draper/QAOA comparison and congestion heatmaps](docs/research/routing/heavy-workloads-2026-10-28/README.md)
- [Compiler study history and metric changes](docs/research/compiler-pregeneration/README.md)
- [Documentation index](docs/README.md)
- [Project structure](docs/project-structure.md)
- [Committed handoff evidence](results/compiler_memory_handoff_2026-10-28/README.md)

## One-command workload run

With the study Python environment active and GNU Make installed:

```text
git submodule update --init --recursive
make run WORKLOAD=qaoa ROUTING=greedy
```

This generates a fresh 96-qubit circuit, maps it with T-HQA, writes the selected
routed trace, then simulates compiler C=4 and ODG on four physics seeds. Only the
selected workload is generated. The runner sets PYTHONPATH and a writable temp
folder automatically. Output defaults to `output/qaoa-greedy/`; results are in
`simulation/qaoa/seed_42/greedy/summary.csv` beneath it.

Use `make dry-run` to inspect commands, or `make trace`, `make route` and
`make simulate` for individual stages. Override `PYTHON`, `WORKLOAD`, `ROUTING`,
`QUBITS`, `SEEDS`, `RESERVATION_MS` or `OUTPUT` as needed. Use fresh output folders
for new experiments; `run` refuses to overwrite existing mapping inputs.
Mapping seed is currently fixed to 42 by the routing study pipeline.

Without Make (including Windows), the equivalent command is:

```text
python -B tools/run_workload.py run --workload qaoa --routing greedy
```

Use an environment with the mapper/MQT Bench and pinned-engine dependencies
already installed; these commands do not install Python packages.

## Run the full-chain comparison

Use SeQUeNCe 0.8.1 at commit
`cf5283cdfd6692a82a090d15fb09fbc01bd322fc` in your Python environment or on
PYTHONPATH. The engine is pinned as a Git submodule under `third_party/SeQUeNCe`.
Initialize it with `git submodule update --init --recursive` (or clone ACE with
`git clone --recurse-submodules`). Preserve the exact revision when comparing results.

```powershell
$env:PYTHONPATH = (Resolve-Path 'third_party/SeQUeNCe').Path
python -m tools.compiler_study.run_full_chain_latency --compiler-memories 4 --seeds 6,7,8,9 --trace results/qft96_2seed_2026-10-26/traces/placements/mesh/T-HQA/qft96/seed_42/routes/xy/requests.txt --config config/final_config/grid_4x4_ace_3.json --output output/handoff_reproduction
```

The preset keeps four physical communication memories per core, a two-layer
minimum lead, all-hop eligibility, ready-first admission and physical audits.
Use `--dry-run` to inspect the complete command. The simulator entry point is
`run_trace_comparison.py`; the [compiler tools guide](tools/compiler_study/README.md)
describes policy sweeps and aggregation. The historical extra-slot consumption
path remains available through `--compiler-pair-consumption swap`.

## Pinned runtime launcher

The checked-in shell launcher pins the imported SeQUeNCe 0.8.1 checkout and
rejects other versions, including the separate native SeQUeNCe 1.0.0 fork.
Run it from a POSIX shell such as Bash:

```bash
tools/run_ace.sh -B run_trace_comparison.py --trace data/tracegen/qft16_seed101.txt --strategies on-demand,fixed,dynamic --seeds 0,1,2 --total-memories 4 --compiler-memories 3 --output output/compiler_study
```

Its defaults are this checkout's `.venv` and bundled `third_party/SeQUeNCe` submodule.
Set `ACE_PYTHON` and `SEQUENCE_ROOT` explicitly for another verified 0.8.1
installation. New experiments record the actual Python executable, imported
`sequence.__file__`, SeQUeNCe version/commit and ACE commit in metadata, in
addition to the EPR-delivery scope and source fingerprints.

Earlier workload-specific measurements remain in the
[compiler repair validation report](docs/reports/compiler-repair-validation.md).

## Repository layout

| Directory | Contents |
| --- | --- |
| [ace/](ace/README.md) | Simulator implementations grouped by compiler, simulation, protocols, resources, topology, applications, observability and traffic. |
| Root Python launchers | Four compatibility CLI entry points; their implementations live under `ace/cli/`. |
| [tools/compiler_study/](tools/compiler_study/README.md) | Full-chain comparison, policy experiments and audited summaries. |
| [tools/routing_research/](tools/routing_research/README.md) | Fixed-placement routing experiments, analysis and annotated congestion heatmaps. |
| [legacy/](legacy/README.md) | Historical standalone runners with fixed buffers/paths; excluded from current experiment guidance. |
| tools/ | Other mapping, congestion, verification and frozen-study workflows, grouped by purpose. |
| [docs/](docs/README.md) | Current guides, research, historical reports and LaTeX sources. |
| config/final_config/ | Physical mesh and torus configurations. |
| data/, data_direct_map/, real_benchmarks/ | Existing trace and benchmark inputs. |
| [examples/](examples/README.md) | Small request-format examples. |
| [test/](test/README.md) | Regression tests and compatibility-preserved request fixtures. |
| mapper/ | Vendored mapper and its provenance; see [mapper/PROVENANCE.md](mapper/PROVENANCE.md). |
| [results/](results/README.md) | Versioned experiment evidence, manifests, validated results and reports. |
| output/ | Ignored local simulations, diagnostics and temporary files. |

Simulator implementations are grouped under `ace/`; root CLI commands and fixture paths retain their established locations. Frozen
result logs and reports are evidence and remain versioned; scratch console dumps
and rebuildable caches are not part of the maintained source tree.
The older `parallel_real`, `parallel_random`, earlier real-workload sweep, and
waste-analysis scripts live under `legacy/runners/`. Start current work with
`run_trace_comparison.py` or the compiler/routing tools linked above.

## Verify

With the pinned dependency available:

```text
python -B -m unittest discover -s test -v
python -B -m unittest discover -s test -p "test_compiler*.py" -v
```

The committed handoff study includes 32 full-trace policy/seed runs with physical
ownership and ordering audits. Its figures apply to QFT-96 and the documented
layer timing model, with the fidelity/storage tradeoff reported explicitly.

## Other workflows

- [MQT workload congestion pipeline](tools/congestion_study/README.md)
- [Ten-workload congestion findings](docs/reports/mqt-congestion-study.md)
- [Frozen golden-study contract](docs/research/golden-study/README.md)
- [Original QFT-96 final report](docs/latex/qft96_final/README.md)
- [Historical October 25 report](docs/latex/oct25_pre_golden/README.md)
