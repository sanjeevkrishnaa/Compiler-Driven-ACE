# History versus Detour2, Greedy and XY, 2026-10-30

Complete 96-qubit QFT, QAOA and BV; T-HQA/OEE mapping seed 42, circuit seed 42,
4x4 mesh, four communication memories/core. All routes preserve identical
migration endpoints and layer placements. Physics seeds 60-63. Compiler C=4,
all-chain preparation, two-layer lead, ready-first event admission, native
handoff, 50 ms compiler reservation cap, zero artificial preparation buffer.
SeQUeNCe 0.8.1 at cf5283cdfd6692a82a090d15fb09fbc01bd322fc.
24 new History trials plus 72 previously measured matched XY/Greedy/Detour2 trials;
all 96 completed and passed audits, with identical engine-facing source hashes.

Readiness is the fraction of hop requests consuming a compiler pair physically
generated strictly before the request's first application submission. This is
not necessarily readiness at initial eligibility: admission waiting may precede
submission. Unused, expired and late-used preparations are not counted as hits.
ODG has no compiler prefetch, so its readiness metric is zero by definition.

## Compiler C=4

Means across four seeds; sample SDs are retained in aggregate.csv. Fidelity is
mean delivered EPR fidelity. Migration latency sums the sequential hop service
intervals (including admission once) for each logical migration. It accounts for
route-length differences; it is not a data-teleportation circuit simulation.

| Workload | Route | Hop latency (ms) | Migration latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| qft | xy | 0.6395 | 1.1639 | 3.2721 | 93.579 | 83.32 |
| qft | greedy | 0.6347 | 1.1551 | 3.2729 | 93.568 | 83.69 |
| qft | detour2 | 0.6101 | 1.1208 | 3.2578 | 93.534 | 85.70 |
| qft | history | 0.5890 | 1.0721 | 3.2238 | 93.497 | 87.85 |
| qaoa | xy | 1.1071 | 2.2767 | 3.8435 | 93.820 | 61.67 |
| qaoa | greedy | 1.0486 | 2.1563 | 3.7476 | 93.795 | 63.69 |
| qaoa | detour2 | 1.0581 | 2.2198 | 3.8167 | 93.766 | 64.35 |
| qaoa | history | 1.0036 | 2.0637 | 3.7075 | 93.776 | 65.33 |
| bv | xy | 0.4458 | 0.7643 | 1.5857 | 93.241 | 100.00 |
| bv | greedy | 0.4458 | 0.7643 | 1.5857 | 93.253 | 100.00 |
| bv | detour2 | 0.4458 | 0.7643 | 1.5857 | 93.241 | 100.00 |
| bv | history | 0.4458 | 0.7643 | 1.5857 | 93.241 | 100.00 |

## Static demand and route length

| Workload | Route | Hops | Excess demand above four slots | Overloaded core-layers |
| --- | --- | ---: | ---: | ---: |
| qft | xy | 3833 | 184 | 131 |
| qft | greedy | 3833 | 153 | 112 |
| qft | detour2 | 3869 | 48 | 35 |
| qft | history | 3833 | 105 | 86 |
| qaoa | xy | 7913 | 1016 | 600 |
| qaoa | greedy | 7913 | 834 | 535 |
| qaoa | detour2 | 8073 | 504 | 306 |
| qaoa | history | 7913 | 821 | 534 |
| bv | xy | 24 | 0 | 0 |
| bv | greedy | 24 | 0 | 0 |
| bv | detour2 | 24 | 0 | 0 |
| bv | history | 24 | 0 | 0 |

## ODG on identical routes

| Workload | Route | Hop latency (ms) | Migration latency (ms) | Makespan (s) | EPR fidelity (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| qft | xy | 1.3324 | 2.4250 | 3.8453 | 94.981 |
| qft | greedy | 1.3358 | 2.4312 | 3.8172 | 94.981 |
| qft | detour2 | 1.3217 | 2.4281 | 3.8629 | 94.981 |
| qft | history | 1.3249 | 2.4113 | 3.8320 | 94.981 |
| qaoa | xy | 1.3888 | 2.8559 | 4.0605 | 94.981 |
| qaoa | greedy | 1.3619 | 2.8006 | 4.0470 | 94.981 |
| qaoa | detour2 | 1.3479 | 2.8278 | 4.0987 | 94.981 |
| qaoa | history | 1.3624 | 2.8015 | 4.0653 | 94.981 |
| bv | xy | 1.3584 | 2.3286 | 1.6076 | 94.981 |
| bv | greedy | 1.4615 | 2.5054 | 1.6101 | 94.981 |
| bv | detour2 | 1.3584 | 2.3286 | 1.6076 | 94.981 |
| bv | history | 1.3584 | 2.3286 | 1.6076 | 94.981 |

## Interpretation and limits

- qft, History vs xy: hop latency -7.89%, migration latency -7.89%, makespan -1.48%, readiness +4.53 percentage points.
- qft, History vs greedy: hop latency -7.19%, migration latency -7.19%, makespan -1.50%, readiness +4.16 percentage points.
- qft, History vs detour2: hop latency -3.45%, migration latency -4.35%, makespan -1.04%, readiness +2.15 percentage points.
- qaoa, History vs xy: hop latency -9.35%, migration latency -9.35%, makespan -3.54%, readiness +3.66 percentage points.
- qaoa, History vs greedy: hop latency -4.29%, migration latency -4.29%, makespan -1.07%, readiness +1.64 percentage points.
- qaoa, History vs detour2: hop latency -5.15%, migration latency -7.03%, makespan -2.86%, readiness +0.98 percentage points.
- bv, History vs xy: hop latency +0.00%, migration latency +0.00%, makespan +0.00%, readiness +0.00 percentage points.
- bv, History vs greedy: hop latency +0.00%, migration latency +0.00%, makespan +0.00%, readiness +0.00 percentage points.
- bv, History vs detour2: hop latency +0.00%, migration latency +0.00%, makespan +0.00%, readiness +0.00 percentage points.

History uses only shortest paths. It minimizes current-layer incremental
overload first, then incremental squared load plus 0.1 times cumulative
prior-layer core visits. History is updated after each layer and never decays.
It is offline predicted traffic, not a runtime queue or occupancy measurement.
Static overload reduction is not a runtime guarantee; route selection can shift
admission and preparation/storage timing. Fidelity measures delivered EPR
pairs, not full circuit output fidelity. BV has no static overload and all
routes keep 24 hops. Its 316 empty layers contribute roughly 1.58 seconds through
the existing 5 ms empty-layer gap, dominating its simulated makespan. Absolute
latencies retain the configured 100 us classical-message overhead. No latency
window is subtracted. One fixed mapping per workload and four physics seeds do
not establish universal routing superiority. Detour optimization uses a two-second
per-layer solver limit; structural.csv records any layers without an optimality
proof. Unchanged total migration count makes migration latency a fairer routing
comparison than per-hop latency alone when routes have different lengths.

Reproduce with the commands in the dated evidence archive; generate History from
the same input mappings and simulate seeds 60,61,62,63 at 50 ms. Derived tables
and audits accompany this report; the prior XY/Greedy report retains its sources.

History has the lowest compiler mean latency and makespan on QFT and QAOA among these four routes under the current settings; BV ties. This updates the earlier recommendation based on the old 1000 ms cap, not a universal superiority claim. Fidelity differences are small and slightly favour XY.

[Raw evidence and reproduction commands](../../../../results/history_comparison_2026-10-30/README.md).
