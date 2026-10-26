# QFT-96 congestion characterization

This directory contains the trace-level congestion analysis for every
validated QFT-96 mapping/routing cell in the 26 October study. It is separate
from ACE timing: it measures demand implied by the route trace and therefore
can be generated while the physical simulations are still running.

Coverage:

- 15 mapping/routing cells: three T-HQA mapping seeds, mesh XY/YX/
  shortest-reliable/maximum-reliability, and torus Dijkstra;
- capacities 2, 3, 4, 6, 8, 16, 32, and 64 memories per core;
- both `hop` and `route` counting;
- total overload, source/destination (“own”) overload, and relay-only overload;
- one CSV row per trace/capacity/variant and one per-core CSV row;
- 240 heatmaps, each with total, own, and relay-only panels.

The `hop` definition counts an internal relay twice (arrival and departure),
while the `route` definition counts a qubit route once at each core it visits.
Relay-only overload means total demand exceeds capacity while endpoint demand by
itself does not. Percentages use communication-active layers only; the 540
non-communication layers in the 766-layer QFT trace are not treated as zero
congestion.

Files:

- `trace_congestion_summary.csv`: aggregate overload and excess-demand rows;
- `per_core_congestion.csv`: source/destination and relay split for every core;
- `heatmaps/`: route-specific PNG heatmaps;
- `manifest.json`: schema, coverage, and definitions;
- generator: `tools/golden_study/analyze_qft96_congestion.py`.

The trace hashes and route provenance are copied into every CSV row so a figure
can always be traced to its exact QFT request file.
