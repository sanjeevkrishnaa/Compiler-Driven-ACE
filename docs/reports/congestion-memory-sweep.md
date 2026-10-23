# Communication-memory budget sweep: what congestion costs

## Headline

Congestion costs **latency, not fidelity**. Restricting communication memories from an
uncongested 32 per core down to 2 raises mean request latency by 27.9% to 58.4% on the four
congested workloads. At the project's standard budget of four memories the penalty is 3.2% to
11.9%. Delivered fidelity under on-demand generation is invariant at 0.949813356353841 across
every budget and every workload in this simulator configuration. That is an observation about
this model, not a general finding that congestion cannot affect fidelity.

Under dynamic pre-generation the fidelity story inverts: fidelity *degrades* as the budget
grows, because a larger compiler bank holds more pairs for longer.

## Scope and backend

This study was run on the **native SeQUeNCe backend**, not ACE.

ACE cannot execute in the current environment. `node.py` requires `msg.dst` and `msg.src` on
every `Message`, which are supplied by the `anub-dota/qnoc-stress-testing` fork named in
`docs/archive/project-handoff-2026-09-06.md`. That repository returns `Repository not found`,
and neither local SeQUeNCe checkout provides those fields. The ACE path stays blocked until
the fork is available again.

| Item | Value |
| --- | --- |
| Runner | `example/multicore_entanglement/run_native_compiler_trace.py` |
| SeQUeNCe commit | `7b8cb2eb8998777f9f9a5ab4f39ef687f645b8d2` (branch `codex/native-compiler-4x4-physical`) |
| Traces | `results/congestion/mqt_ten_workload_congestion_results.zip`, each `<workload>/seed_<n>/requests.txt` |
| Architecture | 4x4 mesh, 16 cores, 48 logical qubits, 8 physical slots per core |
| Workloads | QFT, QAOA, Draper QFT adder, Graph state (congested) + GHZ (zero-congestion control) |
| Mapping seeds | 42, 43, 44 |
| Physics seeds | 3 per run (0, 1, 2) |
| Budgets | 2, 3, 4, 32 (plus 64 on QFT as a saturation check) |
| Strategies | `odg`, `dynamic` |
| Runs | 126, all completing 100% of requests |

Every run's trace SHA-256 was verified against the source file in the zip, and every run's
recorded `communication_memories` was verified to match the intended budget.

## Memory partitioning, and why the two strategies are not directly comparable

The two strategies take different code paths in the runner, which matters for interpretation.

- **`odg`** takes `simulate_sequence_workload(mode='odg', config=config)`. The sweep sets
  `pregeneration_memories = 0`, so all `communication_memories` serve demand and nothing is
  reserved for a compiler. This isolates pure contention.
- **`dynamic`** takes `simulate_native_compiler_trace(...)`, which with static allocation
  computes `compiler_memories = communication_memories - on_demand_reserve` and
  `on_demand_reserve` defaults to 1. The recorded partition is therefore `3+1` at a budget of
  four and `31+1` at 32, reproducing the project's established split.

**Consequence:** an on-demand versus dynamic comparison in this data is confounded by
demand-bank size — on-demand has the whole bank for demand, dynamic has one slot. Settling
that comparison requires the runner's `matched-odg` strategy as a separate arm. The
within-strategy budget sweep reported here is unaffected.

## Results: latency

Mean request latency in ms, on-demand generation, averaged over 3 mapping seeds x 3 physics
seeds. Penalty is measured against the uncongested 32-memory arm.

| Workload | Overloaded layers | Peak core-layer demand | c=2 | c=3 | c=4 | c=32 | Penalty at c=2 | Penalty at c=4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| QFT | 65.18% | 24 | 0.22741 | 0.18030 | 0.16068 | 0.14355 | +58.4% | +11.9% |
| QAOA | 71.57% | 18 | 0.18965 | 0.15309 | 0.13863 | 0.12688 | +49.5% | +9.3% |
| Graph state | 33.33% | 13 | 0.17594 | 0.14229 | 0.13224 | 0.12162 | +44.7% | +8.7% |
| Draper adder | 41.30% | 11 | 0.13589 | 0.11637 | 0.10961 | 0.10625 | +27.9% | +3.2% |
| GHZ (control) | 0% | 2 | 0.07354 | 0.07354 | 0.07354 | 0.07354 | 0.0% | 0.0% |

### The control

GHZ returns **exactly one latency value across all four budgets within each mapping seed**:
0.07093965327777778 (seed 42), 0.07372368105555556 (seed 43), 0.07595006994444443 (seed 44).
Its `pending_ms` is 1e-9 ms, meaning no queueing at all. The 0.07354 in the table is the mean
of the three seeds.

Every congested workload returns four distinct latency values across the same four budgets in
every mapping seed. A workload with no congestion is completely insensitive to the memory
budget, which is what makes the other four rows attributable to congestion rather than to the
budget change itself.

### Saturation

The QFT arm at 64 memories reproduces the 32-memory arm exactly, run for run, across all three
mapping seeds. Case 2 is saturated, not merely large.

### Effect size against seed noise

For QFT on-demand across all three mapping seeds, the 2-memory range is
[0.21723, 0.23421] and the 32-memory range is [0.13669, 0.14803]. The ranges are fully
separated, so the budget effect is far larger than seed-to-seed variation.

### Mechanism

For QFT on-demand, `pending_ms` collapses from 0.13062 to 0.01159 (-91.1%) as the budget
grows, while `generating_ms` *rises* from 0.09658 to 0.13174. The bottleneck is queueing for a
free communication memory; removing it shifts the constraint onto the physical link, so the
net latency gain is smaller than the pending-time collapse alone suggests.

### Peak demand, not overloaded-layer percentage, predicts the penalty

Ranking the five workloads by peak core-layer demand (24, 18, 13, 11, 2) reproduces the penalty
ranking exactly. Ranking by overloaded-layer percentage does not: QAOA has the highest overload
fraction (71.57%) yet a smaller penalty than QFT (65.18%), and Graph state (33.33%, peak 13)
outranks Draper (41.30%, peak 11).

The structural metric currently used to select congested workloads is therefore the wrong
predictor of physical cost, and peak core-layer demand should replace it. With five workloads
this is a rank agreement, not a fitted relationship.

## Results: fidelity

Mean EPR fidelity at teleportation.

| Workload | ODG c=2 | ODG c=32 | Dynamic c=2 | Dynamic c=32 |
| --- | ---: | ---: | ---: | ---: |
| QFT | 0.94981 | 0.94981 | 0.93469 | 0.90856 |
| QAOA | 0.94981 | 0.94981 | 0.93361 | 0.90486 |
| Draper adder | 0.94981 | 0.94981 | 0.92667 | 0.89637 |
| Graph state | 0.94981 | 0.94981 | 0.92659 | 0.90054 |
| GHZ (control) | 0.94981 | 0.94981 | 0.89427 | 0.87724 |

On-demand fidelity is exactly 0.949813356353841 in every one of the 63 on-demand runs, because
pairs are consumed immediately and never sit in storage. Under dynamic pre-generation fidelity
decreases monotonically with the budget for all four congested workloads: a larger compiler
bank means more pairs prepared in advance, held longer, decohering further.

**The memory budget buys latency and spends fidelity, and only pre-generation makes congestion
a fidelity question at all.**

## Caveats

1. The on-demand versus dynamic comparison is confounded by demand-bank size, as described
   above. Only within-strategy budget comparisons are supported by this data.
2. GHZ was added as a zero-congestion control beyond the four workloads identified by the
   characterization. It is not part of the congested set.
3. Random circuit (8.00%), VQE Real-Amplitudes (6.06%) and CDKM ripple-carry adder (0.64%) also
   have non-zero overloaded-layer percentages. "Not zero" is seven of the ten workloads, not
   four; the four studied here are the four highest.
4. These are native SeQUeNCe milliseconds. They must not be compared with ACE milliseconds.
5. Three mapping seeds and three physics seeds per point. Confidence intervals over a larger
   seed count are not yet computed.
6. The structural percentages quoted for context come from the ten-workload study, which
   simulates no EPR physics.
7. **No conflict serialization and no same-qubit dependency ordering.** These runs used no
   experiment contract (`conflict_serialization = None`, `experiment_contract = None` in all
   126 run records; source layers equal serialized layers). Every hop is submitted at its
   trace-layer time, so a relayed qubit's two sequential hops are demanded concurrently. The
   table measures the cost of the supplied concurrent hop-level demand. It is a conditional
   result, not a verified end-to-end execution schedule for the mapped circuits, and the net
   direction of the bias is not determined by this data.
8. **The 32-memory arm is a counterfactual resource increase.** The mapped study provides eight
   physical slots per core, four of them communication. Thirty-two is not the smallest
   uncongested budget; it was chosen to exceed the peak core-layer demand of 24. The
   64-memory QFT arm confirms 32 saturates, not that anything smaller does not.
9. **Provenance: the SeQUeNCe checkout was dirty when these runs were made** (`git.dirty` is
   true in the run records), so commit `7b8cb2eb` alone does not pin the exact runner state.
10. The repository keeps the 126 `study.json` summaries, not the per-request traces.

## Reproducing

See `tools/congestion_memory_sweep/README.md`.

## Artifacts

| File | Contents |
| --- | --- |
| `results/congestion_memory_sweep/results.csv` | One row per run: config, latency, fidelity, pending/generating split, trace SHA-256 |
| `results/congestion_memory_sweep/study_configs.tar.gz` | The 126 `study.json` provenance records |
| `tools/congestion_memory_sweep/run_sweep.py` | The driver that produced them |
