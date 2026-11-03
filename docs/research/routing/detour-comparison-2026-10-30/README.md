# Detour2 versus Greedy and XY, 2026-10-30

Complete 96-qubit QFT, QAOA and BV; T-HQA/OEE mapping seed 42, circuit seed 42,
4x4 mesh, four communication memories/core. All routes preserve identical
migration endpoints and layer placements. Physics seeds 60-63. Compiler C=4,
all-chain preparation, two-layer lead, ready-first event admission, native
handoff, 50 ms compiler reservation cap, zero artificial preparation buffer.
SeQUeNCe 0.8.1 at cf5283cdfd6692a82a090d15fb09fbc01bd322fc.
24 new Detour2 trials plus 48 previously measured matched XY/Greedy trials;
all 72 completed and passed audits, with identical engine-facing source hashes.

Readiness is the fraction of hop requests consuming a compiler pair physically
generated strictly before the request's first application submission. This is
not necessarily readiness at initial eligibility: admission waiting may precede
submission. Unused, expired and late-used preparations are not counted as hits.
ODG has no compiler prefetch, so its readiness metric is zero by definition.

## Compiler C=4

Means across four seeds; sample SDs are retained in aggregate.csv. Fidelity is
mean delivered EPR fidelity. Migration latency sums the sequential hop service
intervals (including admission once) for each logical migration. It accounts for
Detour2's additional hops; it is not a data-teleportation circuit simulation.

| Workload | Route | Hop latency (ms) | Migration latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| qft | xy | 0.6395 | 1.1639 | 3.2721 | 93.579 | 83.32 |
| qft | greedy | 0.6347 | 1.1551 | 3.2729 | 93.568 | 83.69 |
| qft | detour2 | 0.6101 | 1.1208 | 3.2578 | 93.534 | 85.70 |
| qaoa | xy | 1.1071 | 2.2767 | 3.8435 | 93.820 | 61.67 |
| qaoa | greedy | 1.0486 | 2.1563 | 3.7476 | 93.795 | 63.69 |
| qaoa | detour2 | 1.0581 | 2.2198 | 3.8167 | 93.766 | 64.35 |
| bv | xy | 0.4458 | 0.7643 | 1.5857 | 93.241 | 100.00 |
| bv | greedy | 0.4458 | 0.7643 | 1.5857 | 93.253 | 100.00 |
| bv | detour2 | 0.4458 | 0.7643 | 1.5857 | 93.241 | 100.00 |

## Static demand and route length

| Workload | Route | Hops | Excess demand above four slots | Overloaded core-layers |
| --- | --- | ---: | ---: | ---: |
| qft | xy | 3833 | 184 | 131 |
| qft | greedy | 3833 | 153 | 112 |
| qft | detour2 | 3869 | 48 | 35 |
| qaoa | xy | 7913 | 1016 | 600 |
| qaoa | greedy | 7913 | 834 | 535 |
| qaoa | detour2 | 8073 | 504 | 306 |
| bv | xy | 24 | 0 | 0 |
| bv | greedy | 24 | 0 | 0 |
| bv | detour2 | 24 | 0 | 0 |

## ODG on identical routes

| Workload | Route | Hop latency (ms) | Migration latency (ms) | Makespan (s) | EPR fidelity (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| qft | xy | 1.3324 | 2.4250 | 3.8453 | 94.981 |
| qft | greedy | 1.3358 | 2.4312 | 3.8172 | 94.981 |
| qft | detour2 | 1.3217 | 2.4281 | 3.8629 | 94.981 |
| qaoa | xy | 1.3888 | 2.8559 | 4.0605 | 94.981 |
| qaoa | greedy | 1.3619 | 2.8006 | 4.0470 | 94.981 |
| qaoa | detour2 | 1.3479 | 2.8278 | 4.0987 | 94.981 |
| bv | xy | 1.3584 | 2.3286 | 1.6076 | 94.981 |
| bv | greedy | 1.4615 | 2.5054 | 1.6101 | 94.981 |
| bv | detour2 | 1.3584 | 2.3286 | 1.6076 | 94.981 |

## Interpretation and limits

- qft, Detour2 vs xy: hop latency -4.60%, migration latency -3.70%, makespan -0.44%, readiness +2.38 percentage points.
- qft, Detour2 vs greedy: hop latency -3.87%, migration latency -2.97%, makespan -0.46%, readiness +2.01 percentage points.
- qaoa, Detour2 vs xy: hop latency -4.43%, migration latency -2.50%, makespan -0.70%, readiness +2.68 percentage points.
- qaoa, Detour2 vs greedy: hop latency +0.90%, migration latency +2.94%, makespan +1.85%, readiness +0.66 percentage points.
- bv, Detour2 vs xy: hop latency +0.00%, migration latency +0.00%, makespan +0.00%, readiness +0.00 percentage points.
- bv, Detour2 vs greedy: hop latency +0.00%, migration latency +0.00%, makespan +0.00%, readiness +0.00 percentage points.

Static overload reduction is not a runtime guarantee; detours add EPR-service
hops and can shift preparation/storage timing. Fidelity measures delivered EPR
pairs, not full circuit output fidelity. BV has no static overload and all
routes keep 24 hops. Its 316 empty layers contribute roughly 1.58 seconds through
the existing 5 ms empty-layer gap, dominating its simulated makespan. Absolute
latencies retain the configured 100 us classical-message overhead. No latency
window is subtracted. One fixed mapping per workload and four physics seeds do
not establish universal routing superiority. Detour optimization uses a two-second
per-layer solver limit; structural.csv records any layers without an optimality
proof. Unchanged total migration count makes migration latency a fairer routing
comparison than per-hop latency alone when routes have different lengths.

Reproduce with the commands in the dated evidence archive; generate Detour2 from
the same input mappings and simulate seeds 60,61,62,63 at 50 ms. Derived tables
and audits accompany this report; the prior XY/Greedy report retains its sources.

[Raw evidence and reproduction commands](../../../../results/detour_comparison_2026-10-30/README.md).
