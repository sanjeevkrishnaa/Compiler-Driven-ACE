# QFT-96 experimental design contract

This is the frozen design for the QFT-96 study. It is the template that will
be transferred to the other workloads only after the QFT pipeline and
congestion definitions are accepted.

## Factorial dimensions

Each result is identified by the following immutable factors:

| Factor | QFT-96 levels |
| --- | --- |
| Placement | T-HQA, mapping seeds 42, 43, 44 |
| Mesh routing | XY, YX, shortest-reliable, maximum-reliability |
| Torus routing | Dijkstra only |
| Topology | 4 x 4 mesh or 4 x 4 torus |
| Total memories/core | 2, 3, 4, 6, 8, 16, 32, 64 |
| Compiler memories/core | Every legal integer `C=0,...,M-1` |
| Baseline policies | ODG, CGP, ACGP, Dynamic full-chain, Dynamic first-hop |
| Dynamic structural policies | Layer-start, predecessor-start, chain depth `N=1`, `N=2`, and later `N=3,4,all` |
| Evaluation physics seeds | 0 and 1, declared before execution |

The current base matrix uses 11 byte-distinct traces after route deduplication,
while the mapping audit retains all 15 conceptual mapping/routing cells. A
trace hash, source lock, configuration hash, and seed list are mandatory for
every result. No result is reusable merely because a `summary.csv` exists.

## What congestion means

Congestion is a **trace-level demand property**, not a synonym for measured
latency. For each communication-active layer `l` and core `c`, let `P_l` be
the qubit routes in that layer.

* **Hop demand** `D_h(c,l)`: each route endpoint contributes one incident hop;
  each internal relay contributes two (arrival and departure).
* **Route demand** `D_r(c,l)`: a route contributes one in-flight occupancy at
  each distinct core it visits. This is the appropriate lower-bound view when
  consecutive hops of one qubit are serialized.
* **Endpoint demand** `E(c,l)`: only the first and final core of each route
  contributes one. It is called source/destination demand in the figures.
* **Relay demand** is `D(c,l)-E(c,l)` for the selected counting definition.

For capacity `C`, a core-layer is overloaded when `D(c,l)>C`. It is
source/destination (own) overload when `E(c,l)>C`, and relay-only overload when
`E(c,l) <= C < D(c,l)`. These two categories are disjoint and exactly partition
the overloaded core-layers. Percentages are computed over communication-active
layers only; idle circuit layers are not counted as zero-congestion evidence.

The heatmaps therefore answer **where the route creates demand**. ACE timing
metrics answer **how that demand is scheduled**. We do not infer one from the
other. The simulator results must be joined to the congestion tables by the
exact trace hash, topology, capacity, policy, and physics seed.

## Dynamic policy taxonomy

The primary comparison treats structural policies as algorithms:

1. `layer-start`, all scheduled chain hops;
2. `predecessor-start`, where later-hop preparation is released when the
   preceding application request starts;
3. `chain-hops-prepared=N`, with the remaining hops served on demand;
4. the congestion-threshold policy, after a QFT-specific threshold is trained
   on disjoint seeds and frozen before evaluation.

`preparation-delay-ms` is not a distinct algorithm. It is an auxiliary
sensitivity axis for the trigger timing and must not be used to claim five
different Dynamic methods. The current 1, 2, 3, 4 and 6 ms points are retained
as an appendix/ablation. They do not replace the structural depth sweep.

The current runner passes `--no-congestion-threshold`; that policy is therefore
explicitly out of the frozen base result and requires its own preregistered
phase.

## Required reported metrics

For every completed cell, report both per-request and whole-workload values:

- mean, median, p95 and maximum arrival-to-completion latency;
- admission wait, RSVP/control time, generation/service time and retry wait;
- makespan and layer completion time;
- completion rate and starvation/failure count;
- delivered fidelity and retry count;
- generated, utilized, expired and remaining EPR pairs;
- protocol/compiler waste and hit/fallback rates;
- trace congestion: total, own, relay-only, excess demand and per-core heatmap.

## Artifact contract and later scaling

Each machine receives a disjoint manifest slice, but all machines use the same
source lock, SeQUeNCe identity, trace hashes, configuration hashes, command
line, and output schema. Workers write atomic job directories; aggregation is
performed only after seed rows and hashes validate. The QFT chapter links the
manifest, raw CSVs, congestion tables, heatmaps, and generated report tables so
every plotted point remains reproducible.

