# Experiment 2: how much of each core's congestion is its own demand, and how much is relay traffic

Data and figures: `results/experiment2_own_vs_relay_2026-10-24/` (CSV and PNG per capacity and counting variant).
Code: `tools/experiment2/split_congestion.py` (tests in `tools/experiment2/tests/`). Structural analysis of the archived
mapped traces: it counts demand, it simulates no physics, and it is independent of the request scheduler.

## Definitions

* A **route** is a qubit's consecutive hops within one layer. Its first source and final destination are its **endpoints**;
  every core in between is a **relay**. (The traces already split a long move into one hop per link.)
* For a core and a layer, **D** is the number of hops touching the core. **D_end** counts the touches that are a route
  endpoint; **D_relay** counts the rest. A relay core is touched by two hops of the route (one arriving, one leaving), so
  it contributes 2; an endpoint contributes 1. D = D_end + D_relay.
* With capacity C (communication memories per core), a layer is **overloaded** for the core when D > C. It is
  **own-overloaded** when D_end > C (endpoint demand alone is too much) and **relay-only-overloaded** when
  D_end <= C < D (it would have fit without relay traffic). These sets are disjoint and together are exactly the
  overloaded layers, so own% + relay-only% is the heatmap's overloaded%.
* Percentages are over communication-active layers, per mapping seed, then the equal-weight mean over seeds 42, 43, 44.
* *Relay share of the excess* is the part of `max(0, D - C)` that endpoint demand alone would not have caused:
  `(max(0, D - C) - max(0, D_end - C)) / max(0, D - C)`, summed over layers.
* Two ways of counting, both reported. **hop** is the archive's counting (above). **route** counts qubits in flight under
  per-qubit ordering: a route's hops run one after another, so a relay core needs one memory for it at a time, not two.

## Validation

* With the **hop** counting, own% + relay-only% reproduces **all 160 cells** of the project's per-core heatmap (at its
  printed 0.1% resolution), and the per-core relay incidences, incident hops and peak layer demand reproduce **all 480
  per-trial rows** of the archive's `all_trials_cores.csv` exactly. Both are pinned by tests.
* The two sets add up to the overloaded layers for every core and seed (tested), and route counting never reports more
  overload than hop counting (tested).

## Result 1: at the modelled capacity of 4, congestion is relay congestion

Hottest core of each workload (hop counting, capacity 4):

| Workload | Hottest core | Overloaded % | own % | relay-only % | Relay share of its demand when overloaded | Relay share of its excess |
|---|---|---:|---:|---:|---:|---:|
| BMW / QUARK cardinality | none | 0.0 | 0.0 | 0.0 | - | - |
| QFT | C10 | 58.0 | 0.0 | 58.0 | 78% | 100% |
| Draper QFT adder | C10 | 23.4 | 0.0 | 23.4 | 81% | 100% |
| Bernstein–Vazirani | none | 0.0 | 0.0 | 0.0 | - | - |
| QAOA | C10 | 56.0 | 0.0 | 56.0 | 81% | 100% |
| GHZ | none | 0.0 | 0.0 | 0.0 | - | - |
| CDKM ripple-carry adder | C6 | 0.6 | 0.0 | 0.6 | 85% | 100% |
| VQE real amplitudes | C9 | 4.5 | 0.0 | 4.5 | 80% | 100% |
| Graph state | C5 | 33.3 | 0.0 | 33.3 | 93% | 100% |
| Random circuit | C9 | 3.2 | 0.0 | 3.2 | 87% | 100% |

Peak demand, to show how close endpoint demand comes to the capacity:

| Workload | Peak demand D at one core in one layer | Peak endpoint demand D_end | Peak routes through one core |
|---|---:|---:|---:|
| BMW / QUARK cardinality | 2 | 1 | 1 |
| QFT | 24 | 4 | 13 |
| Draper QFT adder | 11 | 4 | 7 |
| Bernstein–Vazirani | 2 | 1 | 1 |
| QAOA | 18 | 5 | 10 |
| GHZ | 2 | 1 | 1 |
| CDKM ripple-carry adder | 9 | 2 | 5 |
| VQE real amplitudes | 5 | 2 | 3 |
| Graph state | 13 | 3 | 7 |
| Random circuit | 12 | 3 | 6 |

At capacity 4 endpoint demand alone almost never exceeds the capacity: its peak is 4 in QFT and Draper, 5 in QAOA and
at most 3 in the other workloads, while total demand reaches 24. The only own-overload at capacity 4 is in QAOA, at the
corner cores C0 and C3 (0.61% of active layers each), which is 0.44% of QAOA's overload; in every other workload it is zero. The cores that overload are the central ones (C5, C6,
C9, C10) that many routes pass through, so the overload is caused by routes passing through, not by routes starting or
ending there. Where overload exists, relay touches are about 78 to 93% of the demand in the overloaded layers.

## Result 2: smaller memory budgets bring in own-demand overload

Share of the overloaded core-layers that come from own endpoint demand (hop counting); in brackets, the total overload
in core-layer percentage points summed over the 16 cores (so 100 means the equivalent of one core overloaded in every layer):

| Workload | C=1 | C=2 | C=3 | C=4 |
|---|---:|---:|---:|---:|
| BMW / QUARK cardinality | 0.0% (60) | no overload | no overload | no overload |
| QFT | 76.8% (990) | 10.1% (542) | 7.1% (518) | 0.0% (302) |
| Draper QFT adder | 54.5% (568) | 6.9% (221) | 6.4% (191) | 0.0% (87) |
| Bernstein–Vazirani | 0.0% (56) | no overload | no overload | no overload |
| QAOA | 51.9% (840) | 14.9% (538) | 2.3% (405) | 0.4% (279) |
| GHZ | 0.0% (60) | no overload | no overload | no overload |
| CDKM ripple-carry adder | 0.4% (181) | 0.0% (5) | 0.0% (3) | 0.0% (2) |
| VQE real amplitudes | 2.0% (230) | 0.0% (82) | 0.0% (24) | 0.0% (11) |
| Graph state | 26.0% (578) | 9.5% (350) | 0.0% (178) | 0.0% (133) |
| Random circuit | 15.7% (304) | 1.8% (82) | 0.0% (47) | 0.0% (14) |

With four memories almost nothing is own-overload. With one memory a core is overloaded by its own endpoint demand as
soon as two routes start or end there, so QFT is 77% own-overload at capacity 1 and mostly relay-overload from capacity 2
upward. A routing change that moves traffic away from the central cores can only remove the relay part; the own part is a
floor set by the mapping.

## Result 3: counting qubits in flight, not hops

A relay needs one memory at a time, not two, so the demand is lower. Same table with route counting:

| Workload | C=1 | C=2 | C=3 | C=4 |
|---|---:|---:|---:|---:|
| BMW / QUARK cardinality | no overload | no overload | no overload | no overload |
| QFT | 86.8% (876) | 11.5% (472) | 12.8% (287) | 0.0% (160) |
| Draper QFT adder | 76.0% (407) | 9.5% (160) | 17.1% (72) | 0.0% (10) |
| Bernstein–Vazirani | no overload | no overload | no overload | no overload |
| QAOA | 59.7% (730) | 20.7% (388) | 4.5% (204) | 1.2% (104) |
| GHZ | no overload | no overload | no overload | no overload |
| CDKM ripple-carry adder | 10.7% (6) | 0.0% (2) | 0.0% (1) | 0.0% (1) |
| VQE real amplitudes | 5.3% (86) | 0.0% (11) | no overload | no overload |
| Graph state | 37.5% (400) | 18.2% (183) | 0.0% (111) | 0.0% (50) |
| Random circuit | 39.6% (121) | 7.0% (21) | 0.0% (4) | 0.0% (1) |

Route counting finds less overload (for example core C10 at capacity 4 is overloaded in 46.4% of QFT's active layers against 58.0% under hop counting, and in 4.6% against 23.4% for Draper), and relay traffic is still essentially all of what remains at capacity 4. Which counting the simulator behaves like is
a scheduler fact: under the corrected per-qubit scheduler a chain's next hop is admitted only after the previous one finishes,
which is the route counting.

## What this does and does not say

* It says where demand comes from, measured on the archived mappings. It does not say what a routing algorithm would
  achieve: that needs a routing policy that exists and is simulated, and none does yet.
* It bounds the benefit of one. Removing every relay touch at capacity 4 would remove essentially all of the overload
  (all of it except QAOA's 0.44%), because endpoint demand is almost always within capacity; that is an upper bound, since the routes cannot all avoid central
  cores. At capacity 1 or 2 a router could remove at most the relay share shown in Result 2.
* The traces' hop paths are shortest paths with a reliability tie-break, not dimension-ordered routes
  (only 46.7% of multi-hop routes match XY), so the relay locations are as the mapper produced them.
