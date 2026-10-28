# Compiler memory handoff correction — 28 October 2026

**Current interpretation:** after a temporary requested extra-memory revert,
online research supports in-place ownership handoff at the EPR-delivery boundary.
It is again the default. These times do not include a data-teleportation circuit.
See the [source-backed lifecycle](pair-consumption-research-2026-10-28.md) and
the preserved [extra-slot comparison](extra-memory-revert-2026-10-28.md).

## Root cause

The old cached-pair path reserved a new application communication memory before
transferring the state from a compiler-held memory. At M=4/C=4, a core could
have four physically ready pairs and still be unable to consume any of them.
Ready-first ordering could not fix a capacity check that required a fifth slot.
Eventually the 1,000-ms compiler reservation expired, destroying the useful pair
and allowing fallback service. The prior matched C=4 result was 396.580 ms mean
latency, 993.175 ms p95, 165.331 s makespan, and 76.25% unused-pair expiry.
This was an ownership/admission defect, not evidence that full compiler
allocation is inherently slow.

## Corrected lifecycle

1. Admission previews a request-specific ready pair and both endpoint leases.
   The memory must still be entangled, its fidelity sufficient, and no other
   booking may conflict with the application's reservation window.
2. The application claims the existing compiler memory's timecard. The local
   booking changes from compiler ownership to application ownership without
   allocating a new memory or moving/resetting the quantum state.
3. Old compiler rule/timeout events are canceled and the compiler quota is
   decremented exactly once. Physical generation time, density matrix/noise,
   and the original physical coherence-expiration event remain intact.
4. The real RSVP request and approval still traverse the classical channels.
   The peer adopts its corresponding memory when the request arrives. The
   existing application generation protocol performs its normal pairing and
   cached-pair notification exchange. Its same-memory completion path avoids
   swapping a memory with itself and resetting the consumed state.
5. Application completion releases its new lease normally. A stale old compiler
   timeout cannot reset a reused slot. If a pair expires during RSVP, the peer
   rejects the claim, stale compiler occupancy is released, and ordinary retry
   uses physical generation. No success is fabricated from the lost pair.

There is no extra physical memory, no zero-delay delivery, no fidelity refresh,
and no changed latency definition. A regression compares native warm-service
time with the historical path when that path has a spare slot: it is identical.
The gain comes from avoiding unnecessary admission waiting and preparation waste.

## Progress when future pairs fill the pool

Full allocation can also expose a different resource cycle: a current request
is unprepared, all slots hold pairs for later layers, and those later layers
cannot activate until the current request completes. When no application is in
flight, the controller may release a blocking, ready, future-only compiler pair.
It frees the local lease and sends the existing remote expiry message over the
configured classical channel. The lost preparation is explicitly recorded as
`demand_progress` waste, and the displaced request retains normal fallback.

This is demand-driven cycle breaking, not a hidden C=3 cap. Full pools of ready
eligible pairs can be handed off concurrently, with no spare communication
slot. An explicit one-memory and two-memory full-pool regression verifies it.
No running application or incomplete physical generation attempt is canceled
by this progress guard.

## Verification and scope

All 159 compiler tests pass. Regressions cover full-pool consumption, concurrent
ready requests through one full core, unchanged native warm-service/control
time, preserved state and physical expiry, old-timeout cancellation, historical
swap-mode stalls, expiry during RSVP, and future-cache/current-demand cycles.
Physical audits enforce booking ownership, pair credits, completion, hop order,
and circuit layer barriers on full QFT-96 runs.

The allocation comparison retains M=4, seeds 6–9, mesh/XY, full-chain preparation,
two-layer minimum lead, ready-first admission, unchanged fidelity/coherence,
and zero artificial buffer. Additional XY seeds 10–13 and YX seeds 6–7 check
the correction beyond the original four seeds. This remains one workload and
the existing layer timing model, not a universal hardware-performance claim.

`--compiler-pair-consumption handoff` is the corrected default. The explicit
`swap` option preserves the historical extra-slot path for reproduction.
`tools/compiler_study/run_full_chain_latency.py` continues to use its explicit C=2 allocation;
add `--compiler-memories 4` for the full allocation. Both it and the generic
runner permit all C=1,2,3,4 values and now consume ready pairs
without additional communication memory.

Old reports/CSVs are retained unchanged and describe the prior implementation.
New comparison data and source fingerprints accompany this correction.

## Final matched results

XY, seeds 6–9, four physical memories per core. Latency is completion minus
eligibility, including control, admission and retries. p95 is the mean of
per-run p95 values, not a pooled quantile.

| Policy | Mean latency ms | p95 ms | Makespan s | Physically pre-ready % | Delivered fidelity |
| --- | ---: | ---: | ---: | ---: | ---: |
| ODG | 1.335462 | 3.150081 | 4.060008 | 0.00 | 0.949813 |
| Handoff C=1 | 1.103061 | 2.775072 | 3.813900 | 27.63 | 0.944840 |
| Handoff C=2 | 0.913174 | 2.625072 | 3.641494 | 52.24 | 0.940773 |
| Handoff C=3 | 0.776262 | 2.225053 | 3.506040 | 68.44 | 0.938024 |
| Handoff C=4 | **0.656721** | **1.900037** | **3.389160** | **82.55** | 0.935740 |

All runs complete 100%. C=4's main-comparison expiry is zero; C=3 has one
unused reservation expire in one seed (mean expiry 0.00951%). C=4 mean latency
is 50.8% below ODG, with an approximately 16.5% shorter makespan. The fidelity
tradeoff remains explicit: more consumed stored pairs lower delivered fidelity
relative to fresh ODG. No fidelity or coherence threshold was relaxed.

Additional XY seeds 10–13 give C=4 0.659301 ms versus ODG 1.319633 ms; YX seeds
6–7 give C=4 0.656147 ms versus ODG 1.351426 ms. All complete and pass the
physical/order audits. The progress guard records two yielded future pairs on
XY seed 13 and ten on YX seed 7; such drops are counted as waste, rather than
hidden. Main XY C=4 seeds 6–9 require zero progress yields.

The reported final allocation/confirmation corpus contains **32 full-trace
policy/seed runs**, all with clean audits, in addition to intermediate diagnostic
runs. [Every seed row](data/compiler-handoff-2026-10-28/all_seeds.csv),
[aggregates and sample SDs](data/compiler-handoff-2026-10-28/aggregate.csv), and
[audit outcomes](data/compiler-handoff-2026-10-28/audits.csv) are retained.

Reproduce from the repository root with the pinned SeQUeNCe 0.8.1 dependency:

```text
python tools/compiler_study/run_full_chain_latency.py --compiler-memories 4 --compiler-pair-consumption handoff --seeds 6,7,8,9 --trace results/qft96_2seed_2026-10-26/traces/placements/mesh/T-HQA/qft96/seed_42/routes/xy/requests.txt --config config/final_config/grid_4x4_ace_3.json --output output/handoff_reproduction
```
