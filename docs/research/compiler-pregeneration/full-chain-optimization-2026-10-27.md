# Full-chain compiler optimization — 27 October 2026

## Why two compiler memories beat three

All comparisons retain four physical communication memories per core and
eligibility-to-completion latency. Every hop remains eligible for compiler
preparation; there is no first-hop or chain-depth filter.

In this implementation, a cached EPR occupies its compiler-reserved memory
while an application must book another communication memory to consume it.
`generation.py::ShEntanglementGenerationAadaptive.start` finds the cached pair;
`swap_two_memory` transfers its state into the application's memory, then
releases the old compiler lease. Admission does not reuse the occupied compiler
timecard directly. Thus a snapshot with three cached pairs at a four-memory
core leaves only one application slot; two cached pairs leave two application
slots. For r ready pairs, simultaneous local cached-pair service is bounded by
min(r, M-r), ignoring additional link/dependency constraints. This is an
explanation of the current consumption path, not a universal optimum theorem.

The archived XY/seed-0,1 decomposition directly measures the tradeoff:

| Policy | Mean admission ms | Mean generation/service ms | Mean latency ms |
| --- | ---: | ---: | ---: |
| ODG | 0.007959 | 1.118620 | 1.326580 |
| Full-chain C=2 | 0.149164 | 0.755552 | 1.104872 |
| Full-chain C=3 | 0.550706 | 0.583642 | 1.335109 |

Raising C from two to three saves 0.171910 ms of service but adds 0.401541 ms
of admission waiting. The approximately 0.230-ms net penalty explains the
regression. More physically prepared pairs do not automatically imply lower
request latency. Common control delay and small retry terms account for the
remaining difference between the two component columns and total latency.

## Controlled alternatives

Selection used full QFT-96 mesh/XY traces and physics seeds 30 and 31. Hardware,
trace, data placement, request window and timing metric are held fixed. The
offline planner's generation-capacity argument is a planning constraint, not a
change to the physical generation hardware.

| Configuration | Mean request latency ms |
| --- | ---: |
| ODG | 1.314363 |
| Offline full-chain C=3, one-layer lead | 1.310263 |
| Offline full-chain C=2, one-layer lead | 1.090114 |
| C=2, minimum two-layer lead | **0.996625** |
| C=2, minimum three-layer lead | 0.996818 |
| C=2, minimum four-layer lead | 1.008029 |
| C=1, minimum two-layer lead | 1.101519 |
| C=2, planner generation capacity raised from two to three | 1.090114 |
| C=2, demand-first preparation and release-triggered retry | 1.077458 |
| C=2, two-layer lead plus demand-first admission | 0.996625 |
| C=2, ready-pair reassignment/replenishment | 1.092036 |
| C=2, two-layer lead plus reassignment | 0.996625 |
| C=3, two-layer lead plus reassignment | 1.167135 |
| Refillable runtime candidate queue, C=2 | 1.363157 |
| Refillable runtime candidate queue, C=3 | 2.207990 |
| Runtime queue with demand-first admission, C=2 | 1.310062 |
| Runtime queue with two-layer lead, C=2 | 1.358580 |

The two-layer lead improves physical readiness from 42.27% to 52.24% on these
selection runs. Service falls from 0.739594 to 0.655123 ms, while admission
waiting slightly decreases from 0.150325 to 0.141502 ms. The third lead layer
does not improve readiness and lowers fidelity further, so it is not selected.
Extra planner generation capacity alone changes nothing: memory occupancy is
the binding offline constraint here.

The runtime queue admits all full-chain candidates as capacity frees rather
than discarding offline-blocked requests. It obeys the same physical quotas and
timecards, but speculative reservation competition harms readiness and demand
latency. These flags remain opt-in research alternatives, not recommended
defaults. Reassignment allows only an earlier request on the same edge to take
an unstarted future target's pair, then attempts to replenish the displaced
target. It preserves physical ownership but adds no benefit to the selected
two-layer policy in this trace.

## Frozen choice and separate-seed confirmation

After selection, freeze C=2 and minimum lead=2; keep the full offline dynamic
candidate search, eight-layer lookahead, layer-start launch, all-hop eligibility,
event admission with starvation guard, zero artificial buffer, and the same
physical hardware. Neither runtime queuing nor reassignment is enabled.

XY confirmation uses physics seeds 6,7,8,9; YX uses 6,7. These seeds were not
used to select the candidate in this study. Means +/- sample SD are across run
means, not pooled request samples or confidence intervals.

| Route | ODG mean ms | C=2, lead=1 mean ms | C=2, lead=2 mean ms | Paired reduction vs ODG |
| --- | ---: | ---: | ---: | ---: |
| XY (four seeds) | 1.335462 +/- 0.025374 | 1.119565 +/- 0.061278 | **1.013505 +/- 0.019177** | **24.11%** |
| YX (two seeds) | 1.351426 +/- 0.012990 | 1.159143 +/- 0.015708 | **1.008196 +/- 0.020360** | **25.40%** |

| XY confirmation metric | ODG | Selected full-chain Dynamic |
| --- | ---: | ---: |
| Mean per-run p95 latency | 3.150081 ms | 2.775066 ms |
| Mean workload makespan | 4.060008 s | 3.674120 s |
| Completion | 100% | 100% |
| Delivered EPR fidelity | 0.949813 | 0.940605 |

This is a latency/fidelity tradeoff, not a Pareto improvement over ODG. Longer
preparation lead stores pairs longer. No fidelity or coherence setting was
relaxed. The result is established only for these QFT-96 routes and the existing
layer timing model, including its five-ms empty-layer gap. Layers are not a
calibrated gate-duration model, so this does not establish universal latency or
hardware performance. The historical buffer-subtracted 0.691-ms number remains
a different metric and is not a target for this study.

## Implementation and verification

`tools/compiler_study/run_full_chain_latency.py` is the recommended reproduction preset. Its
minimum lead now defaults to two; pass `--planner-lead-layers 1` for the initial
C=2 baseline. Existing frozen campaign defaults/results remain unchanged.

`tools/compiler_study/study_full_chain_latency.py` runs the full-chain alternatives and retains
exact commands, per-job metadata/source hashes, per-request timing, pair records,
and physical audit results. `tools/compiler_study/summarize_full_chain_latency.py` requires
100% completion and a clean audit before including a row. `--audit-events` checks
memory ownership, credits/completions, per-qubit hop order, and layer barriers.

All **52 full-trace policy/seed runs** passed their physical audits. All **145
compiler tests pass**, including new runtime-queue and reassignment regressions.
The recommended policy needs no physical generation or latency-definition
change. The experimental policy extensions are disabled by default.

Evidence:

- [Aggregates and standard deviations](data/full-chain-optimization-2026-10-27/aggregate.csv)
- [Every seed/policy observation](data/full-chain-optimization-2026-10-27/all_seeds.csv)
- [All 52 audit outcomes](data/full-chain-optimization-2026-10-27/audits.csv)

ACE base: 0b475ee3c8f3cd7db0e3e76b5369d3a425ff1460. Dependency: unmodified
SeQUeNCe 0.8.1 source at cf5283cdfd6692a82a090d15fb09fbc01bd322fc.
Runtime: Python 3.14.7, NumPy 2.5.1, SciPy 1.18.0, NetworkX 3.6.1, QuTiP 5.3.1.
