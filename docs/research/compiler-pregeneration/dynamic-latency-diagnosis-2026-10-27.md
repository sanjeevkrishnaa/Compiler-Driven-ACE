# Full-chain Dynamic latency diagnosis — 27 October 2026

The approximately 0.6-ms historical Dynamic result and the corrected request
latency measure different intervals. The timing matrix records 0.691 +/-
0.008 ms using legacy serialized release and a 5.3-ms subtraction. Current
latency is completion minus eligibility, including admission and retries.
See [the historical timing matrix](../../reports/qft96-timing-model-matrix-2026-10-25.md).

## Allocation is the immediate fix

The earlier M=4/C=3 comparison was only one allocation. The final campaign
already evaluates every C from zero to M-1. Full-chain Dynamic with C=2 has
lower aggregate mean latency than ODG in every route/topology group at M=4.
This retains preparation eligibility for all chain hops; it does not enable
the first-hop filter or change request timing or physical hardware.

| Topology / route | ODG mean ms | Full-chain C=3 mean ms | Full-chain C=2 mean ms |
| --- | ---: | ---: | ---: |
| Mesh / XY | 1.326580 | 1.335109 | 1.104872 |
| Mesh / YX | 1.325960 | 1.413849 | 1.058236 |
| Mesh / shortest reliable | 1.337145 | 1.427122 | 1.192460 |
| Mesh / maximum reliability | 1.362280 | 1.693036 | 1.324231 |
| Torus / Dijkstra | 1.325973 | 1.113481 | 0.999233 |

Source: [all allocations CSV](../../latex/qft96_final/data/all_allocations_all_metrics.csv),
physics seeds 0 and 1. XY/YX have one distinct trace each; the reliability
routes and torus have three distinct traces each. These are means of run means,
not a pooled request distribution. C=2 is a retrospective configuration
choice from these observations; independent seeds are needed for confirmation.
Maximum-reliability's small mean gain is not a demonstrated significant gain.

On mesh/XY, mean admission waiting is 0.007959 ms for ODG, 0.550706 ms for
Dynamic C=3, and 0.149164 ms for Dynamic C=2. Makespan improves from 4.032682 s
for ODG to 3.775823 s for C=2. Delivered EPR fidelity is 0.949813 for ODG,
0.943782 for C=3, and 0.946087 for C=2. Completion is 100% for all these rows.
Thus C=2 improves both latency and fidelity over C=3, but still has lower
delivered fidelity than ODG. This tradeoff must remain visible.

The source supports the contention diagnosis: compiler reservations and demand
book the same timecards; compiler quota C bounds speculative occupancy. With
three compiler leases on a four-memory core, only one slot remains for demand
while those leases overlap. C=2 leaves more concurrent demand capacity. Demand
still uses any unoccupied shared memory; there is no fixed bank partition.

## Explicit reproduction preset

The initial `tools/compiler_study/run_full_chain_latency.py` preset pins M=4, C=2, generation capacity=2,
full-chain eligibility, layer-start triggering, lookahead=8, planner coherence=10,
zero artificial lead, per-qubit release, event admission, and starvation guard.
ODG uses the same four physical memories, trace and seeds. The existing runner
writes source hashes and all parameters to metadata.json alongside summary.csv.
Frozen campaign defaults/results remain unchanged. The follow-up
[optimization study](full-chain-optimization-2026-10-27.md) changes the launcher's
default minimum lead to two layers after separate-seed validation. Add
`--planner-lead-layers 1` to the command below to reproduce this initial baseline.

From the repository root, with the study's compatible SeQUeNCe 0.8.1 revision
`cf5283cdfd6692a82a090d15fb09fbc01bd322fc` on PYTHONPATH:

```text
python tools/compiler_study/run_full_chain_latency.py --compiler-reservation-ms 1000 --trace results/qft96_2seed_2026-10-26/traces/placements/mesh/T-HQA/qft96/seed_42/routes/xy/requests.txt --config config/final_config/grid_4x4_ace_3.json --seeds 0,1 --output output/full_chain_m4_c2_recheck
```

Use an independent seed set before making a new performance claim. A broader
policy change should be evaluated across latency tails, makespan, completion,
fidelity, admission wait, waste and expiry; recovering the historical 0.691-ms
number is not an appropriate target under the corrected metric.

## Local verification

Seeds 0 and 1 exactly reproduce the archived M=4/C=2 mesh/XY averages:
ODG 1.326580 ms; full-chain Dynamic 1.104872 ms.

Fresh seeds 2, 3, 4 and 5 give mean request latency 1.338887 +/- 0.014517 ms
for ODG and 1.080225 +/- 0.027253 ms for full-chain Dynamic (sample SD across
run means). Dynamic improves in every paired seed; reduction in the means is
19.32%. Mean makespan improves from 4.056958 s to 3.782573 s; mean per-run p95
latency improves from 3.100084 ms to 2.925075 ms. Every run completes all 3,876
hop requests. Delivered fidelity is 0.949813 for ODG and 0.945810 for Dynamic.
Fresh verification is limited to mesh/XY; other routes retain archived evidence.

Evidence: [fresh seed rows](data/dynamic-latency-2026-10-27/fresh-seeds-summary.csv),
[aggregates](data/dynamic-latency-2026-10-27/fresh-seeds-aggregate.json),
[source hashes and parameters](data/dynamic-latency-2026-10-27/fresh-seeds-metadata.json),
[reproduction rows](data/dynamic-latency-2026-10-27/reproduction-summary.csv),
and [allocation comparison](data/dynamic-latency-2026-10-27/allocation-evidence.csv).

All 141 existing compiler tests pass. Runtime: Python 3.14.7, SeQUeNCe 0.8.1
from an unmodified git archive at cf5283cdfd6692a82a090d15fb09fbc01bd322fc,
NumPy 2.5.1, SciPy 1.18.0, NetworkX 3.6.1, QuTiP 5.3.1. ACE base revision:
0b475ee3c8f3cd7db0e3e76b5369d3a425ff1460. Initial runs with the locally
available qnoc dependency produced zero completions even for ODG, were stopped,
and are excluded. The fix changes the explicit allocation preset; physical
generation, scheduling algorithms and latency definitions are unchanged.
