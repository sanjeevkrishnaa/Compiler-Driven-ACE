# ACE TraceGen communication hotspot study

This is a structural study of the original 96-qubit QFT trace at
`C:\Users\sanje\Downloads\qft_requests.txt` and three *additional* 16-qubit,
16-core, 4×4 mesh traces in `C:\Users\sanje\Desktop\BTP\ACE\data\tracegen\`.
The 16-qubit QFT trace is a smaller, newly generated workload; it is not a copy
or subset of the original QFT. This report counts each adjacent-hop
request against both endpoint cores in its compiler layer. The relevant ACE
setting allows at most **three compiler reservations per core**, with four
physical memories total. A core-layer is overloaded at capacity `C` when its
incident hop count exceeds `C`.

These are *layer demand* counts, not observed simultaneous memory occupancy.
Multi-hop moves within one layer have dependent hops, and ACE's current
comparison runner serializes every pair of requests sharing a core, even when
three memories are available. The counts identify routing and scheduling
pressure; they do not by themselves predict physical latency or fidelity.

## Hotspots and capacity sensitivity

| Workload | Hop requests | Layers with traffic | C=1 | C=2 | C=3 | C=4 | Peak core-layer demand |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original QFT-96 | 4,954 | 227 of 766 | 221 | 159 | **158** | 150 | Core 9: 28 |
| New QFT-16 | 46 | 30 of 126 | 12 | 2 | **2** | 0 | Core 1: 4 |
| Cuccaro | 9 | 5 of 218 | 3 | 1 | **0** | 0 | Core 1: 3 |
| Random, depth 80 | 62 | 24 of 33 | 16 | 7 | **7** | 2 | Core 1: 8 |

At the operating limit of three, the **original QFT-96** overloads **158 of
227 traffic-bearing layers**; 4,307 of 4,954 hop requests touch an overloaded
core in their layer. Core 9 is the largest hotspot, with 2,218 total hop
incidences and a peak of **28** in layer 372. Core 5 has 1,536 incidences and
a peak of 20; core 8 has 1,230 and a peak of 16. All 16 cores initially hold
six logical qubits. This is the workload used in the original ACE compiler
experiments.

The **new QFT-16** overloads only layers **48 and 52**: core 1 receives four
hop incidences in each. Cuccaro never exceeds three.
Random overloads are layers **4, 9, 12, 15, 17, 19, and 22**. Layer 12 is the
worst, with core 1 at **8** and core 2 at **7**; it has 10 hop requests from five
logical-qubit migrations. Random has 16 excess core-hop incidences above the
three-memory limit across its eight overloaded core-layers. New QFT-16 has two.

The three *new 16-qubit traces* have a much more concentrated placement than
the original QFT. Each starts with six qubits on core 0, six on core 1, and
four on core 2; **13 of 16 cores start empty**. Every new QFT-16 and Cuccaro hop
touches core 1 (46/46 and 9/9 respectively); 58/62 random hops do too.
Core 1 is therefore the hotspot **within the new 16-qubit suite**. Its total
incident-hop counts are 46 for QFT-16, 9 for Cuccaro, and 58 for random. Random's next busiest core is
core 2 with 32 incidences and a peak of seven in layer 12.

For the original QFT, rerouting cannot be assessed from the small-trace
detours below. Its largest loads are on central relay cores, but many
migrations interact within a layer and all cores already hold data qubits.
Rerouting may shift contention and add many EPR hops. A joint placement,
routing, and communication-sublayer study is needed before recommending it.

For the new traces, capacity sensitivity is sharp: moving from two to three
available communication memories eliminates Cuccaro's sole overloaded layer,
but does not change the number of overloaded QFT-16 or random layers. Moving
from three to four eliminates new QFT-16 overloads and cuts random overloaded layers from seven
to two; random layer 12 still exceeds four at two cores.

## Could alternate paths help?

The detour analysis in this section applies **only to the new 16-qubit traces**.
I reconstructed whole qubit migrations from consecutive same-qubit hops, then
searched simple 4×4 mesh paths with at most two extra hops for each overloaded
layer. The migration's start and final core remain fixed, so the trace's final
placement remains valid. One example is `0→1→2` becoming
`0→4→5→6→2`: it removes relay load from core 1 but doubles the migration from
two to four EPR hops.

| Workload | Three-memory hot layers cleared by detours | Added hop requests | Remaining hot layers |
| --- | ---: | ---: | ---: |
| New QFT-16 | 2 of 2 | +4 (46→50, +8.7%) | 0 |
| Cuccaro | 0 needed | 0 | 0 |
| Random | 6 of 7 | +12 (62→74, +19.4%) | Layer 12 |

For new QFT-16 layers 48 and 52, rerouting one `0→2` migration per layer is enough.
For random layers 4, 9, 15, 17, 19, and 22, one two-hop migration detour per
layer is enough. These are feasible *structural* improvements, not measured
performance gains: extra physical EPR generation, storage, and migration
steps can outweigh fewer same-layer conflicts.

**Layer 12 cannot meet a three-memory limit through routing alone.** Core 1
has two unavoidable migration endpoints and thus cannot relay another path:
each relay would add two incidences, taking it to at least four. Three other
migrations must then avoid core 1 while entering or leaving core 0. Core 0's
only other neighbor is core 4, so all three must pass through core 4, giving
core 4 at least six incidences. This exceeds three regardless of how the
remaining paths are chosen. Splitting this layer into communication sublayers
or changing qubit placement is necessary. With four memories, one feasible
detour set clears layer 12 with **eight additional hop requests** and moves
load to multiple otherwise idle cores; that is a costly option.

## Recommendation

Prioritize **capacity-aware placement and communication sublayer scheduling**.
The new 16-qubit traces pack the workload into three cores, creating a
standing bottleneck that detours cannot fully remove. Evaluate a more spread
initial placement in TraceGen, then compare total hop count and ACE physical
latency/fidelity. For the new traces, retain shortest routes for Cuccaro;
test the eight cheap QFT-16/random detours as an ablation, with layer 12 split into
sublayers. Record generated/used EPR pairs, retries, end-to-end completion
time, and fidelity alongside mean request latency. ACE currently resets the
request timestamp on retry, so its existing mean latency does not include
earlier failed attempts; rerouting should not be judged from that metric alone.

No physical rerouting experiment has been run for this report. Its conclusion
is that rerouting is **plausible for isolated relay hotspots**, while the main
random burst requires scheduling or placement changes. Extra hops can reduce
contention yet increase generation work and decoherence; the net benefit needs
a paired-seed physical comparison.
