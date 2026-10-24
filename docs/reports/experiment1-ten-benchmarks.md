# Experiment 1: latency, fidelity and congestion of the ten benchmarks across communication-memory budgets

Data: `results/experiment1_ten_benchmarks_2026-10-24/` (`results.csv`, one row per run; `cell_summary.csv`; figures).
Code: `tools/experiment1/` (driver, analysis, this report's generator). ACE-internal numbers on the corrected
(per-qubit, event-admission) scheduler only; never compare these milliseconds with native SeQUeNCe's, and never merge them
with results from the legacy scheduler. Physical parameters are ACE's current, undecided ones
(`ace-physical-parameters.md`); the sensitivity section shows what the ACGP paper's values would change.

## Design

* **Workloads:** the ten MQT circuits of the characterization (GHZ, Bernstein-Vazirani, BMW/QUARK cardinality, VQE real
  amplitudes, CDKM ripple-carry adder, graph state, Draper QFT adder, QAOA, QFT, random circuit), on the 4x4 mesh, three
  mapping seeds each (42, 43, 44), traces unmodified from the archive.
* **Memory budget:** communication memories per core, 1, 2, 3, 4, 6, 8, 16, 32 (QFT also 64). **1 to 4 are modelled** (the ACGP
  paper's Table I gives four communication qubits per core). **6 to 32 are counterfactual** (what-if capacity), marked `*`.
* **Policies:** *on-demand* (nothing pre-generated; isolates contention) and *dynamic* compiler pre-generation, with
  the compiler allowed to hold at most `budget - 1` memories per core at once (the memories are a shared pool that any request can use), so dynamic starts at 2.
* **Seeds:** three physics seeds per mapping, so **nine runs per cell**. Tables give mean ± standard deviation over the nine; the
  figures draw the min to max band. 1,368 runs.
* **Latency** is the common definition: from the moment a request could first be asked for (its layer starting, or the previous
  hop of its qubit completing) until it completes, minus the fixed 5.3 ms pre-generation lead. Waiting for a memory counts.

## Controls

* PASS every run completes every request -- 1368 rows, 0 not ok
* PASS zero-congestion control: GHZ on-demand latency does not respond to the budget -- 0 of 9 (mapping, physics) runs vary across budgets
* PASS saturation: QFT with 64 memories reproduces 32 run for run (relative 1e-6) -- 18 runs compared, largest relative difference 7.96e-12
* PASS on-demand delivered fidelity does not depend on the budget -- 0 of 90 runs vary
* PASS on-demand latency does not rise when memory is added, beyond seed-to-seed noise -- 639 budget steps: 1 rise by less than the physics-seed spread (largest 0.0005 ms), 0 rise by more

The first full run failed two of these for reasons that were not physical, and the controls were refined (tests pin them):
the saturation check compared to exact equality although a few requests "waited" the one picosecond the scheduler leaves after
a release, and a single on-demand step rose by 0.0005 ms with more memory (0.05%, a thirtieth of the physics-seed spread), which
is sampling noise because a delayed request draws different random numbers. A "wait" now means more than a microsecond.

## Result 1: what congestion costs on-demand requests

Request latency in ms, on-demand (mean ± sd over nine runs):

| Workload | 1 | 2 | 3 | 4 | 6* | 8* | 16* | 32* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GHZ | 1.17 ± 0.11 | 1.17 ± 0.11 | 1.17 ± 0.11 | 1.17 ± 0.11 | 1.17 ± 0.11 | 1.17 ± 0.11 | 1.17 ± 0.11 | 1.17 ± 0.11 |
| Bernstein–Vazirani | 1.22 ± 0.12 | 1.22 ± 0.12 | 1.22 ± 0.12 | 1.22 ± 0.12 | 1.22 ± 0.12 | 1.22 ± 0.12 | 1.22 ± 0.12 | 1.22 ± 0.12 |
| BMW / QUARK cardinality | 1.12 ± 0.04 | 1.12 ± 0.04 | 1.12 ± 0.04 | 1.12 ± 0.04 | 1.12 ± 0.04 | 1.12 ± 0.04 | 1.12 ± 0.04 | 1.12 ± 0.04 |
| VQE real amplitudes | 2.32 ± 0.14 | 1.11 ± 0.05 | 1.11 ± 0.05 | 1.11 ± 0.05 | 1.11 ± 0.05 | 1.11 ± 0.05 | 1.11 ± 0.05 | 1.11 ± 0.05 |
| CDKM ripple-carry adder | 1.66 ± 0.22 | 1.24 ± 0.05 | 1.17 ± 0.03 | 1.14 ± 0.03 | 1.14 ± 0.03 | 1.14 ± 0.03 | 1.14 ± 0.03 | 1.14 ± 0.03 |
| Graph state | 9.14 ± 1.14 | 2.72 ± 0.54 | 1.53 ± 0.30 | 1.24 ± 0.13 | 1.18 ± 0.08 | 1.18 ± 0.08 | 1.18 ± 0.08 | 1.18 ± 0.08 |
| Draper QFT adder | 7.36 ± 0.84 | 2.16 ± 0.20 | 1.30 ± 0.05 | 1.15 ± 0.02 | 1.13 ± 0.02 | 1.13 ± 0.02 | 1.13 ± 0.02 | 1.13 ± 0.02 |
| QAOA | 10.92 ± 0.41 | 3.42 ± 0.14 | 1.74 ± 0.06 | 1.27 ± 0.02 | 1.14 ± 0.01 | 1.13 ± 0.01 | 1.13 ± 0.01 | 1.13 ± 0.01 |
| QFT | 14.42 ± 0.35 | 4.72 ± 0.14 | 2.39 ± 0.09 | 1.59 ± 0.05 | 1.21 ± 0.02 | 1.15 ± 0.02 | 1.13 ± 0.02 | 1.13 ± 0.02 |
| Random circuit | 2.99 ± 0.10 | 1.27 ± 0.02 | 1.12 ± 0.01 | 1.11 ± 0.01 | 1.11 ± 0.01 | 1.11 ± 0.01 | 1.11 ± 0.01 | 1.11 ± 0.01 |

Cost of too few memories, relative to the same workload with 32 (saturated), on-demand:

| Workload | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|---:|
| GHZ | +0% | +0% | +0% | +0% | +0% | +0% |
| Bernstein–Vazirani | +0% | +0% | +0% | +0% | +0% | +0% |
| BMW / QUARK cardinality | +0% | +0% | +0% | +0% | +0% | +0% |
| VQE real amplitudes | +109% | +0% | +0% | +0% | +0% | +0% |
| CDKM ripple-carry adder | +46% | +9% | +3% | +0% | +0% | +0% |
| Graph state | +676% | +131% | +30% | +5% | +0% | +0% |
| Draper QFT adder | +549% | +90% | +14% | +1% | +0% | +0% |
| QAOA | +863% | +202% | +53% | +12% | +1% | -0% |
| QFT | +1170% | +316% | +110% | +40% | +6% | +1% |
| Random circuit | +170% | +14% | +1% | +0% | +0% | +0% |

* **Budget 1 is severe where there is congestion:** QFT 12.7x the saturated latency, QAOA 9.6x, graph state
  7.8x, Draper 6.5x. Workloads with no overload (GHZ, Bernstein-Vazirani, BMW) do not respond at all
  (GHZ, Bernstein–Vazirani, BMW / QUARK cardinality).
* **At the modelled four memories the penalty is small to moderate:** QFT +40%, QAOA +12%, graph state
  +5%, Draper +1%, CDKM +0%, random circuit +0%.
* **Memory buys latency with diminishing returns.** The smallest budget within 5% of the saturated latency is
  GHZ 1, Bernstein–Vazirani 1, BMW / QUARK cardinality 1, VQE real amplitudes 2, CDKM ripple-carry adder 3, Graph state 6, Draper QFT adder 4, QAOA 6, QFT 8, Random circuit 3.
* **The floor is generation, not contention:** with 32 memories the on-demand latency is 1.11 to 1.22 ms across the ten
  workloads, which is also what the workloads with no overload show at every budget.

## Result 2: congestion as waiting, and its structural source

Fraction of requests that waited more than a microsecond for a free memory, on-demand (mean over nine runs):

| Workload | 1 | 2 | 3 | 4 | 6* | 8* | 16* | 32* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GHZ | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bernstein–Vazirani | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| BMW / QUARK cardinality | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| VQE real amplitudes | 0.205 | 0.002 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| CDKM ripple-carry adder | 0.033 | 0.020 | 0.011 | 0.002 | 0.000 | 0.000 | 0.000 | 0.000 |
| Graph state | 0.602 | 0.281 | 0.121 | 0.029 | 0.000 | 0.000 | 0.000 | 0.000 |
| Draper QFT adder | 0.536 | 0.211 | 0.055 | 0.008 | 0.000 | 0.000 | 0.000 | 0.000 |
| QAOA | 0.671 | 0.376 | 0.172 | 0.058 | 0.004 | 0.000 | 0.000 | 0.000 |
| QFT | 0.696 | 0.430 | 0.249 | 0.130 | 0.031 | 0.007 | 0.000 | 0.000 |
| Random circuit | 0.254 | 0.042 | 0.006 | 0.001 | 0.000 | 0.000 | 0.000 | 0.000 |

The structural overload of the same traces at the same capacity (% of communication-active layers in which some core exceeds the
capacity, pooled over mapping seeds; independent of any simulation):

| Workload | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|---:|
| GHZ | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Bernstein–Vazirani | 25.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| BMW / QUARK cardinality | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| VQE real amplitudes | 54.5% | 31.8% | 10.6% | 6.1% | 0.0% | 0.0% |
| CDKM ripple-carry adder | 96.2% | 0.8% | 0.8% | 0.6% | 0.6% | 0.4% |
| Graph state | 100.0% | 83.3% | 50.0% | 33.3% | 33.3% | 22.2% |
| Draper QFT adder | 92.8% | 65.5% | 59.7% | 41.3% | 15.0% | 3.1% |
| QAOA | 98.2% | 85.1% | 79.1% | 71.6% | 56.6% | 34.8% |
| QFT | 94.6% | 75.9% | 75.9% | 65.2% | 56.5% | 41.1% |
| Random circuit | 90.0% | 35.5% | 25.4% | 8.0% | 1.7% | 0.3% |

Across the 60 (workload, budget 1 to 8) points, the structural overload and the on-demand latency penalty are strongly
rank-correlated: Spearman ρ = 0.85 (p = 1.1e-17). So the heatmap's static count predicts which
workloads pay and how the cost falls as memory is added, though the counts say nothing about the size of the cost.
Where the overload comes from (mostly relaying through the central cores) is Experiment 2
(`experiment2-own-vs-relay.md`).

## Result 3: pre-generation (dynamic) against on-demand, and the fidelity price

Request latency in ms, dynamic:

| Workload | 2 | 3 | 4 | 6* | 8* | 16* | 32* |
|---|---:|---:|---:|---:|---:|---:|---:|
| GHZ | 0.51 ± 0.07 | 0.26 ± 0.00 | 0.26 ± 0.00 | 0.26 ± 0.00 | 0.26 ± 0.00 | 0.26 ± 0.00 | 0.26 ± 0.00 |
| Bernstein–Vazirani | 0.46 ± 0.07 | 0.24 ± 0.00 | 0.24 ± 0.00 | 0.24 ± 0.00 | 0.24 ± 0.00 | 0.24 ± 0.00 | 0.24 ± 0.00 |
| BMW / QUARK cardinality | 0.49 ± 0.02 | 0.25 ± 0.00 | 0.25 ± 0.00 | 0.25 ± 0.00 | 0.25 ± 0.00 | 0.25 ± 0.00 | 0.25 ± 0.00 |
| VQE real amplitudes | 1.52 ± 0.20 | 1.19 ± 0.16 | 0.88 ± 0.07 | 0.41 ± 0.00 | 0.25 ± 0.00 | 0.25 ± 0.00 | 0.25 ± 0.00 |
| CDKM ripple-carry adder | 0.76 ± 0.06 | 0.38 ± 0.03 | 0.30 ± 0.01 | 0.30 ± 0.01 | 0.30 ± 0.01 | 0.30 ± 0.01 | 0.30 ± 0.01 |
| Graph state | 6.36 ± 0.79 | 5.01 ± 0.59 | 3.23 ± 0.82 | 1.60 ± 0.39 | 0.95 ± 0.13 | 0.27 ± 0.04 | 0.25 ± 0.00 |
| Draper QFT adder | 4.55 ± 0.43 | 3.67 ± 0.34 | 2.48 ± 0.38 | 1.60 ± 0.17 | 0.89 ± 0.23 | 0.25 ± 0.01 | 0.25 ± 0.00 |
| QAOA | 6.89 ± 0.28 | 5.33 ± 0.19 | 3.88 ± 0.17 | 2.70 ± 0.13 | 1.86 ± 0.08 | 0.35 ± 0.04 | 0.25 ± 0.00 |
| QFT | 10.06 ± 0.54 | 7.49 ± 0.33 | 5.57 ± 0.21 | 3.73 ± 0.25 | 2.78 ± 0.19 | 0.80 ± 0.16 | 0.25 ± 0.00 |
| Random circuit | 1.91 ± 0.08 | 1.37 ± 0.04 | 0.94 ± 0.02 | 0.56 ± 0.02 | 0.38 ± 0.02 | 0.25 ± 0.00 | 0.25 ± 0.00 |

Delivered EPR fidelity, dynamic (on-demand delivers 0.9498 in every workload at every budget):

| Workload | 2 | 3 | 4 | 6* | 8* | 16* | 32* |
|---|---:|---:|---:|---:|---:|---:|---:|
| GHZ | 0.9344 ± 0.0003 | 0.9254 ± 0.0002 | 0.9254 ± 0.0002 | 0.9254 ± 0.0002 | 0.9254 ± 0.0002 | 0.9254 ± 0.0002 | 0.9254 ± 0.0002 |
| Bernstein–Vazirani | 0.9345 ± 0.0004 | 0.9266 ± 0.0002 | 0.9266 ± 0.0002 | 0.9266 ± 0.0002 | 0.9266 ± 0.0002 | 0.9266 ± 0.0002 | 0.9266 ± 0.0002 |
| BMW / QUARK cardinality | 0.9343 ± 0.0001 | 0.9253 ± 0.0001 | 0.9253 ± 0.0001 | 0.9253 ± 0.0001 | 0.9253 ± 0.0001 | 0.9253 ± 0.0001 | 0.9253 ± 0.0001 |
| VQE real amplitudes | 0.9344 ± 0.0004 | 0.9203 ± 0.0007 | 0.9165 ± 0.0003 | 0.9128 ± 0.0004 | 0.9125 ± 0.0001 | 0.9125 ± 0.0001 | 0.9125 ± 0.0001 |
| CDKM ripple-carry adder | 0.9354 ± 0.0001 | 0.9247 ± 0.0001 | 0.9227 ± 0.0001 | 0.9210 ± 0.0000 | 0.9210 ± 0.0000 | 0.9210 ± 0.0000 | 0.9210 ± 0.0000 |
| Graph state | 0.9341 ± 0.0013 | 0.9236 ± 0.0020 | 0.9189 ± 0.0040 | 0.9158 ± 0.0043 | 0.9128 ± 0.0022 | 0.9111 ± 0.0002 | 0.9112 ± 0.0001 |
| Draper QFT adder | 0.9368 ± 0.0007 | 0.9257 ± 0.0015 | 0.9218 ± 0.0007 | 0.9154 ± 0.0007 | 0.9148 ± 0.0006 | 0.9158 ± 0.0000 | 0.9158 ± 0.0000 |
| QAOA | 0.9390 ± 0.0002 | 0.9298 ± 0.0004 | 0.9245 ± 0.0006 | 0.9167 ± 0.0004 | 0.9136 ± 0.0004 | 0.9137 ± 0.0003 | 0.9143 ± 0.0000 |
| QFT | 0.9386 ± 0.0006 | 0.9306 ± 0.0010 | 0.9274 ± 0.0007 | 0.9215 ± 0.0005 | 0.9189 ± 0.0003 | 0.9185 ± 0.0006 | 0.9202 ± 0.0000 |
| Random circuit | 0.9320 ± 0.0001 | 0.9186 ± 0.0005 | 0.9130 ± 0.0004 | 0.9075 ± 0.0002 | 0.9068 ± 0.0001 | 0.9070 ± 0.0000 | 0.9071 ± 0.0000 |

* **For the congested workloads dynamic is slower than on-demand at small budgets, because its prepared pairs may occupy up to `budget - 1`
  of the memories** and requests then wait for a free one (workloads with no congestion gain from pre-generation at once). The first budget at which dynamic is faster than on-demand in the same total budget is
  GHZ 2, Bernstein–Vazirani 2, BMW / QUARK cardinality 2, VQE real amplitudes 4, CDKM ripple-carry adder 2, Graph state 8, Draper QFT adder 8, QAOA 16, QFT 16, Random circuit 4.
  So whether pre-generation helps depends on how much memory there is to spend on it, and at the modelled four memories it
  helps only the workloads with little congestion.
* **At 32 memories dynamic reaches 0.24 to 0.30 ms**, a request served from an already generated pair, against
  1.11 to 1.22 ms on-demand. The smallest budget within 10% of that is GHZ 3, Bernstein–Vazirani 3, BMW / QUARK cardinality 3, VQE real amplitudes 8, CDKM ripple-carry adder 4, Graph state 16, Draper QFT adder 16, QAOA 32, QFT 32, Random circuit 16:
  the congested workloads need far more than the modelled four.
* **Fidelity is the price.** Delivered fidelity under dynamic (at most 0.9390) is below the on-demand 0.9498 everywhere and falls as the
  compiler bank grows from 2 to about 8 memories and then levels off (probably because more pairs are prepared earlier and wait longer in storage; the storage time was not measured here): for example QFT 0.9386 at 2 memories to
  0.9189 at 8. The largest drop below the on-demand value in these tables is 0.0430, under ACE's 1 s coherence time.
* **Workloads with no overload at four memories (GHZ, Bernstein–Vazirani, BMW / QUARK cardinality) still change between 2 and 3 memories under dynamic**
  (GHZ 0.51 to 0.26 ms; Bernstein–Vazirani 0.46 to 0.24 ms; BMW / QUARK cardinality 0.49 to 0.25 ms). The structural overload there is zero, so this is not congestion. The
  earlier budget study attributed the same effect to planner coverage (one compiler memory at a budget of two cannot prepare
  every request); that explanation is carried over, not re-tested here.

## Sensitivity: the ACGP paper's memory parameters (exploratory)

Not a result of the study: the physical parameters are undecided. This arm reruns five workloads at budgets 2, 4, 8, 32,
mapping seed 42, three physics seeds, with coherence time 1 ms and memory efficiency 0.85 (ACGP Table I) instead of ACE's
1 s and 0.95, everything else unchanged. Each cell is `ACE → Table I`, mean of three runs.

Request latency (ms), on-demand:

| Workload | 2: ACE → Table I | 4: ACE → Table I | 8: ACE → Table I | 32: ACE → Table I |
|---|---:|---:|---:|---:|
| GHZ | 1.21 → 1.48 | 1.21 → 1.48 | 1.21 → 1.48 | 1.21 → 1.48 |
| Graph state | 2.42 → 2.84 | 1.19 → 1.49 | 1.19 → 1.48 | 1.19 → 1.48 |
| Draper QFT adder | 2.26 → 2.60 | 1.16 → 1.44 | 1.13 → 1.41 | 1.13 → 1.41 |
| QAOA | 3.59 → 3.94 | 1.28 → 1.55 | 1.14 → 1.40 | 1.14 → 1.40 |
| QFT | 4.60 → 4.94 | 1.57 → 1.84 | 1.15 → 1.40 | 1.14 → 1.39 |

Request latency (ms), dynamic:

| Workload | 2: ACE → Table I | 4: ACE → Table I | 8: ACE → Table I | 32: ACE → Table I |
|---|---:|---:|---:|---:|
| GHZ | 0.51 → 1.51 | 0.26 → 1.39 | 0.26 → 1.53 | 0.26 → 1.53 |
| Graph state | 7.21 → 7.93 | 4.24 → 7.93 | 1.11 → 7.56 | 0.25 → 1.38 |
| Draper QFT adder | 4.78 → 8.09 | 2.45 → 6.79 | 1.08 → 6.65 | 0.25 → 4.54 |
| QAOA | 7.25 → 11.03 | 4.07 → 10.33 | 1.97 → 9.89 | 0.25 → 7.24 |
| QFT | 9.43 → 13.21 | 5.46 → 12.53 | 2.62 → 11.82 | 0.25 → 8.93 |

Delivered fidelity, dynamic:

| Workload | 2: ACE → Table I | 4: ACE → Table I | 8: ACE → Table I | 32: ACE → Table I |
|---|---:|---:|---:|---:|
| GHZ | 0.9345 → 0.7861 | 0.9255 → 0.7861 | 0.9255 → 0.7813 | 0.9255 → 0.7813 |
| Graph state | 0.9324 → 0.7861 | 0.9152 → 0.7861 | 0.9124 → 0.7846 | 0.9112 → 0.7846 |
| Draper QFT adder | 0.9368 → 0.7861 | 0.9224 → 0.7861 | 0.9140 → 0.7861 | 0.9158 → 0.7861 |
| QAOA | 0.9392 → 0.7861 | 0.9252 → 0.7861 | 0.9138 → 0.7861 | 0.9143 → 0.7861 |
| QFT | 0.9392 → 0.7861 | 0.9274 → 0.7861 | 0.9188 → 0.7861 | 0.9202 → 0.7861 |

What the sensitivity arm shows (all counts summed over its dynamic runs):

* **The parameters decide whether pre-generation works at all.** With ACE's 1 s coherence, 56778 of the 56778 compiler pairs
  generated in the matching main-arm runs were used. With 1 ms coherence, **6 of 15700 were used and 15694 expired
  unused**; 83850 of 83856 requests fell back to on-demand generation. So dynamic then pays for pairs it
  never uses: at 32 memories its latency is 8.93 ms for QFT, 7.24 for QAOA and 4.54 for Draper, against 0.25 ms with ACE's values. A likely contributor, not tested here, is that the
  planner is told pairs stay valid for 10 layers (`--coherence-time-layers 10`) and a layer lasts several milliseconds, far
  longer than 1 ms.
* **On-demand latency rises by 0.26 to 0.42 ms** in every cell, a roughly constant offset that leaves the shape of the
  budget curves unchanged. The likely cause, not isolated here, is the lower memory efficiency making each generation attempt less likely to succeed.
* **On-demand fidelity is not parameter-independent:** 0.9498 under ACE's values against 0.7861 with Table I's, the same
  in every workload and budget (every pair waits about the same time before it is delivered). The fidelity numbers of this
  experiment are therefore set by the coherence time, and say nothing about the physics until it is decided.
* The delivered fidelity of dynamic under Table I is likewise between 0.7715 and 0.7861 in all
  cells.

Conclusion for the reader: **the congestion results (how waiting, and latency, depend on the memory budget) are structural and
change little with these parameters; the pre-generation and fidelity results depend entirely on them.**

## Limits

* One machine, one parameter set, nine runs per cell. Standard deviations are across mapping and physics seeds together.
* Budgets above four are counterfactual; they say what more memory would buy, not what the hardware has.
* The counts of overload (Result 2) are structural; the latency numbers depend on the scheduler (corrected, event admission,
  scheduler modelled as a central controller reading the reservation tables instantly) and on the harness constants (5.3 ms
  lead, 50 ms window, 5 ms empty-layer gap).
* Only on-demand and dynamic were run; fixed pre-generation and the autonomous caches (continuous, adaptive-continuous) are
  not in this experiment.
* No routing policy exists yet, so nothing here measures what a better routing algorithm would achieve; Experiment 2 bounds
  it structurally.
