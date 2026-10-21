# QFT layer congestion and observed delay

Analysis date: 2026-10-21. Source: the original 96-qubit trace at
`C:/Users/sanje/Downloads/qft_requests.txt`, SHA-256
`61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`.
Timing comes from repaired ACE QFT seeds 0–2, not the old uncorrected runs.

## Direct answer

The trace has 766 original layers, 227 with communication and 539 without,
on a 4x4 mesh with 4,954 adjacent-hop requests. Count each hop once at each
endpoint core. A layer is overloaded at C if at least one core has more than
C incident hop requests. These are layer totals, not simultaneous occupancy.

| Capacity per core | Layers over capacity | Fraction of active layers | Overloaded core-layer combinations | Excess endpoint demand | Hops touching an overloaded core |
|---|---:|---:|---:|---:|---:|
| Four physical communication qubits | **150** | **66.08%** | 563 | 3,487 | 3,687 / 4,954 (74.42%) |
| Three compiler reservation slots | **158** | **69.60%** | 1,010 | 4,497 | 4,307 / 4,954 (86.94%) |

The four-qubit count is 150/766 = 19.58% of all layers, including empty ones.
There are 4,629 requests in the 150 overloaded layers, of which 3,687 directly
touch an overloaded core. Excess endpoint incidences are not extra EPR pairs:
both endpoints contribute and a relay contributes on incoming and outgoing hops.

## Spatial and temporal hotspots

| Core | Mesh position (row, column) | Total incident hops | Peak requests in one layer | Layers over four |
|---|---|---:|---:|---:|
| 9 | (2, 1) | 2,218 | **28** | **145** |
| 5 | (1, 1) | 1,536 | 20 | 122 |
| 8 | (2, 0) | 1,230 | 16 | 114 |
| 1 | (0, 1) | 694 | 9 | 74 |

Core IDs and compiler layers are zero-based. The largest peak is layer 372:
62 hops, core 9 demand 28, core 5 demand 18, core 8 demand 16, and core 13
demand 10. Cores 0, 3, 12 and 15 never exceed four in any layer.

## Delay in the repaired simulator

Timing below is the mean over dynamic-policy seeds 0–2. Within-layer waiting
is first application submission minus entry to its original compiler layer.
It is reconstructed from measured elapsed batch times and verified against
both measured makespan and request service records. All these dynamic/ODG
trials have zero request retries.

| Original-layer category | Layers | Requests | Sum of measured layer durations | Mean within-layer waiting per hop |
|---|---:|---:|---:|---:|
| Demand over four somewhere | 150 | 4,629 | **26.478 s** | **98.41 ms** |
| Demand within four everywhere, active only | 77 | 325 | 1.735 s | 12.40 ms |
| All active layers | 227 | 4,954 | 28.213 s | 92.77 ms |

The 150 overloaded layers account for about 93.85% of active communication-layer
elapsed time. Whole-trace dynamic makespan is 30.903 s; 2.690 s comes from the
explicit delay after empty layers. Waiting overlaps between requests, so the
individual waiting times must not be summed and called wall-clock delay.

For layer 372 specifically, measured duration is **351.90 ms**, mean pre-submission
waiting is **158.54 ms**, and the last batch starts **345.27 ms** after layer entry.

There is a major execution-policy qualification: ACE currently allows only
**one request per core per batch**, and preserves trace order at every core.
The 227 active layers become **4,696 batches**. Each batch receives a 5.3 ms
buffer, totaling **24.8888 s**; the overloaded layers alone get 4,386 batches
and **23.2458 s of buffers**, plus **3.2324 s of exposed service**.
Layer 372 becomes 57 batches, including 302.1 ms of buffers.

Consequently, 98.41 ms is observed scheduling/serialization waiting in hot
layers, including necessary same-qubit hop dependencies. It is **not a causal
estimate of delay solely induced by having four communication qubits**. The
existing mean request-latency metric starts at application submission and
therefore excludes this pre-submission waiting.

## Is there a routing opportunity?

Consecutive same-qubit adjacent hops within a layer form 1,770 hop chains.
This grouping uses the communication trace; omitted gate operations are not
reconstructed. All current chains are shortest Manhattan paths.

- **1,107 chains (62.54%) have multiple equal-length shortest paths.** This
  allows a first experiment that balances load without adding hops.
- Core 9's 2,218 incidences include **1,972 internal relay incidences (88.91%)**
  and only 246 chain endpoint incidences. Core 5 has 1,254 relay incidences;
  core 8 has 1,076. Concentration is strongly driven by the selected paths.
- No layer has fixed chain-endpoint demand above four. Thus none of the 150
  overloaded layers is forced by source/destination demand alone.
- Summing incidences that are mandatory across **all shortest paths** gives a
  stronger lower bound: layers **276, 280, 288, 292 and 296** still exceed four
  at some core under any choice of shortest paths. Clearing those requires
  detours, placement changes or temporal scheduling.
- Only 364 of core 9's 2,218 incidences are mandatory across shortest-path
  choices. This is a lower bound, not a guarantee that the other 1,854 can all
  be removed simultaneously while respecting other cores' capacity.

The other 145 overloaded layers are candidates for shortest-path balancing;
the lower-bound test does not prove that all 145 can be cleared jointly.

## Separating scheduling from routing

A dependency-preserving greedy abstract scheduler, with the same routes and
up to four incident requests per core per wave, uses **1,146 waves**. With
unlimited core capacity, same-qubit dependencies still require **1,053 waves**.
The current ACE batching uses 4,696 waves. A four-capacity layer-372 packing
uses ten waves, versus six dependency-only waves and 57 current ACE batches.

A fixed-service replay holds each hop's measured buffer-plus-service duration
constant, then repacks the waves. Across all active layers it yields 7.533 s
at capacity four versus 6.901 s with capacity unconstrained: a **0.632 s
difference in that surrogate model**. The current measured active-layer time
is 28.213 s. These replay values are scheduling diagnostics, **not predicted
physical speedups or measured rerouting gains**. They omit changed pair
readiness, generation contention, decoherence and ownership/adoption overlap.
ACE's current app cannot execute four same-core requests concurrently.

The useful next experiment is congestion-aware selection among equal-length
shortest paths, with migration endpoints and dependencies preserved. Compare
peak/overloaded-core demand, hop count and repaired ACE makespan. Report the
effect of batching separately; otherwise a routing result will conflate the
four-qubit capacity with ACE's stricter one-request/core execution policy.
Detours should be a later experiment because they add EPR demand and can move
the hotspot to another core.

## Artifacts and reproduction

- `output/qft_congestion_characterization/layers.csv`: every original layer,
  overloaded core IDs, core demands, batch counts and abstract wave counts.
- `output/qft_congestion_characterization/cores.csv`: per-core statistics.
- `output/qft_congestion_characterization/observed_layer_delay.csv`: every
  active original layer's measured timing, for each seed and ODG/dynamic.
- `output/qft_congestion_characterization/summary.json`: counts, exact
  overloaded layer lists and aggregated trial delay data.
- `output/qft_congestion_characterization/qft_hotspots.png`: figure.

Run from the SeQUeNCe workspace:

```powershell
python -B -m tools.trace_analysis.characterize_qft_congestion --trace C:/Users/sanje/Downloads/qft_requests.txt --ace C:/Users/sanje/Desktop/BTP/ACE --study C:/Users/sanje/Desktop/BTP/ACE/output/compiler_repaired_qft96_3seed/runs.json --output output/qft_congestion_characterization
```
