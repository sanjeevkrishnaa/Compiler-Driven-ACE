# Compiler-Driven ACE

Physical ACE/SeQUeNCe experiments for on-demand, continuous, adaptive continuous,
and compiler-directed EPR generation in multicore quantum architectures.

The compiler path supports request-specific one-shot preparation, fixed and
dynamic scheduling, physical fallback, dependency-preserving communication
batches, safe reservation release, and retry-inclusive latency accounting.

## Compiler experiments

Use the compatible SeQUeNCe fork from
[qnoc-stress-testing](https://github.com/anub-dota/qnoc-stress-testing), with
its `SeQUeNCe` directory installed in your Python environment or on PYTHONPATH.

```powershell
$env:PYTHONPATH = 'C:/path/to/qnoc-stress-testing/SeQUeNCe'
python run_compiler_pregeneration.py --trace C:/path/to/requests.txt --strategies on-demand,fixed,dynamic --seeds 0,1,2 --total-memories 4 --compiler-memories 3 --output output/compiler_study
```

The repaired dynamic policy reduced mean request latency by 37.52% on the
original QFT-96 trace (three matched seeds) and 55.70% on the small random
trace (ten matched seeds), compared with the corrected ODG baseline. These
are workload-specific results; storage still reduces EPR fidelity.
See [validation and reproduction](docs/reports/compiler-repair-validation.md).

## Workload congestion study

`tools/congestion_study` runs actual MQT Bench circuits or supplied QASM through
the provided HQA/TraceGen mapper, exports mappings and traces, and produces
offline HTML/CSV/JSON hotspot reports. Physical simulation is optional.

```powershell
python -m pip install -r tools/congestion_study/requirements.txt
python tools/congestion_study/run_study.py --mapper-dir C:/path/to/tracegen --workloads bmw_quark_cardinality qft draper_qft_adder bv qaoa ghz cdkm_ripple_carry_adder vqe_real_amp graphstate randomcircuit --seeds 42 43 44 --output output/congestion_study
```

Defaults: 4x4 mesh, 128 total physical qubits, four communication memories/core,
dynamic preparation, and 48 logical circuit qubits. Each core initially has
three occupied data slots, one spare data slot for migration, and four
communication slots. The hardware budget is explicit and configurable.

- [Study tool and options](tools/congestion_study/README.md)
- [Ten-workload findings](docs/reports/mqt-congestion-study.md)
- [Complete study archive, including raw per-core data](results/congestion/mqt_ten_workload_congestion_results.zip)
- [Compact cross-workload table](results/congestion/aggregate_workloads.csv)

## Tests

```powershell
python -B -m unittest discover -s test -p 'test_compiler*.py' -v
python -B -m unittest discover -s test -p 'test_congestion*.py' -v
python -B -m unittest discover -s tools/congestion_study/tests -v
```

Compiler lifecycle tests require the compatible SeQUeNCe fork and its physical
dependencies. The characterization unit tests use the Python standard library.

## Documentation

See the [documentation index](docs/README.md) for current results, research
notes, protocol reference and archived implementation handoffs. Generated
simulation output, logs and caches are ignored; curated results live in `results/`.

Research foundations:
[Design and Simulation of the Adaptive Continuous Entanglement Generation Protocol](https://arxiv.org/abs/2502.01964),
[Adaptive, Continuous Entanglement Generation for Quantum Networks](https://ieeexplore.ieee.org/document/9798130).
