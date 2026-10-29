# Documentation

## Start here

- [Heavy-workload routing comparison: QFT, Draper and QAOA, with congestion heatmaps](research/routing/heavy-workloads-2026-10-28/README.md)
- [Current source-backed pair-delivery model and physical-memory ownership](research/compiler-pregeneration/pair-consumption-research-2026-10-28.md)
- [Extra-memory experiment and revert comparison](research/compiler-pregeneration/extra-memory-revert-2026-10-28.md)
- [Compiler-memory handoff results](research/compiler-pregeneration/compiler-memory-handoff-2026-10-28.md)
- [Compiler pre-generation study index: current versus historical results](research/compiler-pregeneration/README.md)
- [Compiler experiment tools and reproduction commands](../tools/compiler_study/README.md)
- [Committed full-trace handoff evidence](../results/compiler_memory_handoff_2026-10-28/README.md)
- [Repository structure and dated study map](project-structure.md)
- [Legacy runner archive: historical buffers and paths](../legacy/README.md)

## Historical reports and prior handoffs

The reports below describe earlier scheduler, timing and reservation models.
Use the current handoff report above for the corrected compiler-consumption path.

- [Comprehensive report (PDF): what was wrong, how and why it was fixed, Experiments 1 and 2 in full, why dynamic pre-generation is slower than on-demand, ODG/dynamic/CGP/ACGP compared, repository map, timeline](latex/ace_report/ace_report.pdf) — LaTeX source in [`latex/ace_report/`](latex/ace_report)
- [Handoff for the deep-study phase: 96-qubit plan, mapping code, ACE/SeQUeNCe bug hunt, latency definition, improving dynamic](plans/handoff-deep-study-2026-10-25.md)
- [Handoff: state, open decisions, pitfalls](plans/handoff-2026-10-24.md)
- [Golden ACE study: fresh contract, registry, and experiment gates](research/golden-study/README.md)
- [Why dynamic is slower than on-demand: code reading, measurements, ablations](reports/dynamic-vs-odg-diagnosis.md)
- [ODG, dynamic, CGP and ACGP on nine benchmarks (mesh and torus)](reports/four-policy-comparison.md)

## Current implementation and results

- [Compiler repair validation and reproduction](reports/compiler-repair-validation.md)
- [Ten-workload MQT congestion study](reports/mqt-congestion-study.md)
- [Original QFT congestion and observed delay](reports/qft-congestion-characterization.md)
- [Communication-memory budget sweep: what congestion costs](reports/congestion-memory-sweep.md)
- [ACE congestion budget study: why ACE cannot measure contention](reports/ace-congestion-budget-study.md)
- [Reservation latency root-cause investigation](reports/ace-latency-root-cause.md)
- [Workload pipeline usage and architecture knobs](../tools/congestion_study/README.md)
- [Congestion memory-budget sweep: reproduction](../tools/congestion_memory_sweep/README.md)

## Additional workload analysis

- [Small TraceGen hotspot study](reports/tracegen-small-hotspots.md)
- [Full-scale TraceGen hotspot study](reports/tracegen-fullscale-hotspots.md)

## Reference

- [Qubit mapper (QM2026/HQA): provenance, verification and how a trace is produced](../mapper/PROVENANCE.md)
- [Metrics glossary: every measured parameter](reference/metrics-glossary.md)
- [Adaptive continuous protocol](reference/adaptive-protocol.md)
