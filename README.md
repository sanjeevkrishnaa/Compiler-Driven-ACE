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

Historical local/service-time claims are not the current headline metric. The
correctness branch defines latency as request eligibility to EPR delivery,
including admission wait, reservation, retries, and generation, while excluding
cached-pair storage before eligibility. On the current QFT-96 per-qubit control,
ODG is faster than the baseline Dynamic policy on that fair metric; Dynamic's
research goal is to remove this admission-wait gap honestly, not to preserve an
older number. See [the correctness audit](docs/research/ace-correctness-audit-2026-10-25.md)
and the [golden study](docs/research/golden-study/README.md).

For QFT-96 with four memories per core, the final allocation sweep shows that
full-chain Dynamic at C=2 beats ODG in aggregate mean latency across all five
route/topology groups; C=3 over-allocates compiler capacity on mesh. Use the
explicit `tools/run_full_chain_latency.py` preset for a matched recheck. See
the [latency diagnosis](docs/research/dynamic-latency-diagnosis-2026-10-27.md)
for values, fidelity tradeoffs, and the historical 0.691-ms metric distinction.
The follow-up [full-chain optimization study](docs/research/full-chain-optimization-2026-10-27.md)
tests 17 configurations and confirms a two-layer minimum lead at C=2 on
separate XY/YX physics seeds. The launcher now defaults to that lead; use
`--planner-lead-layers 1` to reproduce the earlier C=2 baseline.
The [ready-pair priority correction](docs/research/ready-priority-2026-10-28.md)
changes current event admission to serve eligible ready-pair requests before
ODG, then admit concurrent ODG into remaining capacity. Reproduce historical
FIFO comparisons with `--admission-priority fifo`; the current preset explicitly
selects `ready-first`.
The [C=1 through C=4 ready-first sweep](docs/research/ready-allocation-2026-10-28.md)
compares complete matched-seed runs, including C=4's reservation-induced stalls
and expiry. All four allocations complete, but C=4 is substantially slower.
Those C=4 results used the historical extra-slot consumption path. The
[compiler-memory handoff correction](docs/research/compiler-memory-handoff-2026-10-28.md)
lets an application consume a pair in its existing communication slot, keeping
native RSVP and consumption timing. C=4 now averages about 0.657 ms on the same
XY seeds, with 100% completion and zero expiry. The reproduction launcher accepts
`--compiler-memories 4`; use `--compiler-pair-consumption swap` only to reproduce
the older path.

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

The [standalone QFT-96 final report](docs/latex/qft96_final/README.md) presents
the complete mesh/torus results, verified congestion atlas, policy/memory curves,
allocation and launch-policy experiments, with tables and committed CSV sources.

The [October 25 pre-golden-study report](docs/latex/oct25_pre_golden/README.md)
collects routing and Dynamic preparation experiments in a separate LaTeX/PDF
report, with source-linked graphs, tables, seed data and validation evidence.

See the [documentation index](docs/README.md) for current results, research
notes and protocol reference. Generated
simulation output, logs and caches are ignored; curated results live in `results/`.

Research foundations:
[Design and Simulation of the Adaptive Continuous Entanglement Generation Protocol](https://arxiv.org/abs/2502.01964),
[Adaptive, Continuous Entanglement Generation for Quantum Networks](https://ieeexplore.ieee.org/document/9798130).

## Fresh golden study

The consolidated ODG/CGP/ACGP/Dynamic study is intentionally separate from the
historical result folders. Its contract blocks an experiment until its workload
traces, hashes, seed sets, route policy, and configuration are explicit. Start at
[the golden-study README](docs/research/golden-study/README.md). The frozen base
manifest contains 110 distinct T-HQA request traces, 30 paired evaluation seeds,
every registered memory allocation, and 1,808,400 policy-seed simulations. The
first two complete slices---GHZ and BV with T-HQA placement and mesh-XY
routing---contain 556 validated jobs and 32,880 policy-seed simulations across all
registered memory allocations. Their tables and figures are in the
[execution progress record](docs/research/golden-study/03-execution-progress.md).
The congestion-adaptive threshold remains a separate training-only phase.
