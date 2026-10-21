# Ten-workload congestion study

This structural study maps ten actual MQT Bench circuits using the supplied
HQA mapper with OEE initial placement. Each circuit is analyzed under mapping/
hardware seeds 42, 43 and 44; circuit generation and parameter binding are held
fixed. No physical simulation was run for these 30 analyses.

The architecture is a 4x4 mesh with 128 total physical slots and four
communication memories/core. Each core has four data slots, including one
initial vacancy for HQA migration: the circuit width is 48 logical qubits.
Dynamic preparation uses three compiler slots and one fallback/adoption slot.

| Workload | Pattern | Overloaded active layers, mean % | Overloaded-layer range |
|---|---|---:|---:|
| QAOA | Repeated dense graph interactions | 71.57% | 114â€“122 |
| QFT | Structured long-range Fourier interactions | 65.18% | 69â€“77 |
| Draper QFT adder | Fourier-basis arithmetic | 41.30% | 54â€“63 |
| Graph state | Sparse degree-2 graph preparation | 33.33% | 2 |
| Random circuit | Heterogeneous gate patterns | 8.00% | 173â€“194 |
| Real-Amplitudes VQE | Repeated reverse-linear ansatz | 6.06% | 1â€“2 |
| CDKM/Cuccaro | Carry-dependent ripple arithmetic | 0.64% | 1 |
| BMW/QUARK cardinality | Repeated nearest-neighbor RXX layers | 0% | 0 |
| Bernsteinâ€“Vazirani | Shared flag/oracle interactions | 0% | 0 |
| GHZ | Sequential nearest-neighbor preparation | 0% | 0 |

A layer is overloaded if any core has more than four incident hop requests.
Both endpoints are counted. Layer demand is not observed simultaneous memory
occupancy: same-qubit hop dependencies and ACE's stricter one-request/core
batching are reported separately. Zero overload is a valid control result;
these measurements do not establish a physical rerouting speedup.

QAOA, QFT and Draper are useful candidates for congestion-aware routing studies
under this setup. Graph state illustrates isolated bursts. Random's high total
traffic but lower overloaded-layer fraction reflects the normalized circuit's
temporal structure; a burst percentage alone is insufficient to rank cost.

## Retained data

The [complete archive](../../results/congestion/mqt_ten_workload_congestion_results.zip)
contains 30 normalized circuits, mappings, validated traces, dynamic schedules,
per-core/per-layer/per-link tables, heatmaps, reports and reproduction scripts.
It retains 480 per-core trial summaries and 20,640 layer records containing
every core's demand. Extract it and open `START_HERE.html`.

- [Aggregate workload statistics](../../results/congestion/aggregate_workloads.csv)
- [Aggregate per-core statistics](../../results/congestion/aggregate_core_hotspots.csv)
- [Validation record](../../results/congestion/validation.json)

The archive also includes the mapper source snapshot and file checksums. All
traces passed evolving-placement and adjacency checks; per-layer trace outputs
agree with mappings, data-only occupancy stays bounded, and per-core/link totals
match raw hop counts. See [pipeline instructions](../../tools/congestion_study/README.md)
for the exact knobs and commands.
