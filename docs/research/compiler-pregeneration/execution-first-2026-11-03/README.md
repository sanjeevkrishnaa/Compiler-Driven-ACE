# Execution-first layer activation, 2026-11-03

Branch codex/execution-first-pregeneration. QAOA96, frozen T-HQA/OEE mapping
seed 42 and History routes, physics seed 60 only. M=4/C=4, generation capacity
four, original logical-layer lookback 2-8, planner age limit ten, all chain hops,
50 ms compiler reservations, ready-first event admission and native handoff.
Empty layers use the original 5 ms gap. All six trials completed all 7913
requests and passed runtime audits. The rerun of the original ordering matches
the earlier seed-60 latency and makespan exactly. All ODG rows are identical
across the three variants, and engine-facing source fingerprints match.

## Change

Original: activate layer, trigger scheduled preparations, release current
requests, then run event-driven demand admission.

New default: activate layer, release all eligible current requests without
queuing separate admission events, synchronously run one ready-first admission
pass, then trigger the layer's scheduled preparations at the same timestamp.
Ready-pair handoffs and ODG requests that fit are admitted before new preparation.
It does not wait for demand completion; execution and preparation still overlap.
All eligible requests are collected before admission to retain ready-first order.
Empty layers still trigger preparation before their 5 ms wait. Preparations
already stored for future layers are not removed by this ordering change.
Physical reservation state machines and the offline planner are unchanged.

A separate guarded variant additionally enables existing --demand-first. That
controller schedules launches at least 1 ps later and applies _can_prepare:
reject speculation touching queued eligible demand, and check both endpoints'
free capacity after accounting for admitted requests whose remote bookings are
still in flight. Rejections use existing compiler retries. This protects demand
beyond the initial activation pass. It is NOT silently part of the new default.

## Results

| Variant | Hop latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) | Admission wait (ms/hop) |
| --- | ---: | ---: | ---: | ---: | ---: |
| original | 1.0044 | 3.7064 | 93.777 | 65.41 | 0.2102 |
| execution-first | 0.9177 | 3.5488 | 93.839 | 65.93 | 0.1565 |
| execution-first-guarded | 0.8642 | 3.4967 | 93.860 | 66.51 | 0.1149 |
| ODG control | 1.3732 | 4.0941 | 94.981 | N/A | 0.0358 |

- execution-first vs original: latency -8.63%; makespan -4.25%; admission waiting -25.51%.

- execution-first-guarded vs original: latency -13.96%; makespan -5.66%; admission waiting -45.31%.

The observed admission-wait reduction supports the execution-priority rationale;
these are single-seed outcomes and do not establish robustness across mappings
or physics seeds. Readiness counts consumption of a pair created before first
application submission, not necessarily before initial eligibility. Fidelity is
delivered EPR fidelity, not circuit output fidelity. The 5 ms empty-layer gap is
still a placeholder; neither local gate execution nor data teleportation is
simulated. No pregeneration window is subtracted from latency.

## Validation and reproduction

205 simulator and 19 routing tests pass. New tests verify current requests are
all released before the initial admission pass, that admission happens before
preparation, that the original ordering remains selectable, and that empty
layers still launch preparation and retain their gap. Historical equivalence
fixtures explicitly select preparation-first.

```text
make run WORKLOAD=qaoa ROUTING=history SEEDS=60 OUTPUT=output/execution-first-new
make run WORKLOAD=qaoa ROUTING=history SEEDS=60 ACTIVATION_ORDER=preparation-first OUTPUT=output/preparation-first-control
```

Direct CLI: --layer-activation-order execution-first or preparation-first.
Add --demand-first for the separate guarded test (same other preset flags).
The exact commands for all variants are in the evidence archive. Default basis
is logical and default empty gap is restored to 5 ms. Cached physical results
must match activation order, layer basis, gap, consumption mode, seeds and window.
