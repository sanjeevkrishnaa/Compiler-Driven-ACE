# Extra-application-memory consumption restored — 28 October 2026

**Superseded default:** subsequent online research distinguishes EPR ownership
transfer from data-qubit teleportation. In-place delivery is again the default
at this simulator's EPR-service boundary. This report preserves the explicit
extra-communication-slot experiment; see the [research and implementation](pair-consumption-research-2026-10-28.md).

At the user's request, direct compiler-memory ownership handoff is disabled by
default. The simulator and compiler comparison launchers now use `swap`: a
separate application communication memory must be reserved before consuming a
pair held in compiler memory. The controller's `reuse_compiler_memory` default
is false. Explicit `handoff` remains available for reproducing earlier evidence.
The routing launcher also defaults to swap and rejects reuse of completed
results with a different consumption mode or simulator seed set.

## Fresh matched latency comparison

Full original QFT-96 mesh/XY trace: 3,876 adjacent hops and 766 circuit layers,
simulator seeds 6–9. Four total communication memories/core; compiler allocation
and generation capacity C=1,2,3,4. Ready-first event admission, independent-qubit
concurrency, sequential dependent hops, full-chain preparation, two-layer minimum
lead, physical noise/fidelity/coherence, and the existing future-cache progress
guard are retained. No additional pre-generation buffer is configured or
subtracted. Compiler reservation duration remains 1,000 ms.

Latency is eligibility to completion, including admission, reservation/control,
generation, consumption and retries. Values are means across the four seeds;
p95 is the mean of individual run p95s.

| Policy | Mean hop latency, ms | p95, ms | Workload completion, s | Mean admission wait, ms |
| --- | ---: | ---: | ---: | ---: |
| ODG | 1.335462 | 3.150081 | 4.060008 | 0.007269 |
| Swap C=1 | 1.117096 | 2.800078 | 3.828425 | 0.034927 |
| Swap C=2 | 0.984647 | 2.775053 | 3.675670 | 0.111960 |
| **Swap C=3** | **0.960416** | **2.750058** | **3.576115** | **0.246932** |
| Swap C=4 | 396.580257 | 993.175065 | 165.330826 | 395.411527 |

**C=3 is the best tested allocation under the separate-memory requirement:**
28.1% lower mean hop latency and 11.9% shorter workload completion than ODG.
It leaves one of the four physical communication memories outside the compiler
allocation. C=2 is slightly slower but has lower admission waiting and higher
delivered EPR fidelity (0.940704 versus C=3's 0.937614; ODG is 0.949813).

C=4's 396.580 ms mean is dominated by **395.412 ms of admission waiting**.
When all four memories hold prepared pairs, consuming one still requires a
separate application memory. Useful pairs can wait until reservation expiry
releases capacity; 76.25% of generated compiler pairs expire unused in these
runs. This is the cost of combining C=4 allocation with the required extra-slot
consumption model and a four-memory physical bank. No hidden C=3 cap was added.

## Difference from the earlier handoff numbers

The earlier matched handoff means were C=1 1.103061 ms, C=2 0.913174 ms,
C=3 0.776262 ms and C=4 0.656721 ms. Restoring the extra-memory requirement
removes the approximately 0.66 ms operating point on this trace and budget.
The fresh swap results reproduce the earlier extra-slot allocation sweep.

The seven-route QFT/Draper/QAOA study also used handoff. Its frozen measurements
are retained and marked accordingly; its numerical routing recommendations
must not be assumed to hold unchanged under swap without new routing trials.

## Validation and evidence

All **20 complete policy/seed trials** pass physical ownership, pair-credit,
completion, hop-order and layer-barrier audits with zero violations. All 159
compiler tests and all 19 routing tests pass. A launcher dry run confirms that
omitting the consumption argument now emits `--compiler-pair-consumption swap`.

- [Aggregate values and sample standard deviations](data/extra-memory-revert-2026-10-28/aggregate.csv)
- [All seed rows](data/extra-memory-revert-2026-10-28/all_seeds.csv)
- [Audit outcomes](data/extra-memory-revert-2026-10-28/audits.csv)
- [Raw evidence, source snapshots and test logs](../../../results/extra_memory_revert_2026-10-28/README.md)

Reproduce using the pinned SeQUeNCe 0.8.1 dependency on `PYTHONPATH`:

```text
python -B -m tools.compiler_study.study_full_chain_latency --trace results/qft96_2seed_2026-10-26/traces/placements/mesh/T-HQA/qft96/seed_42/routes/xy/requests.txt --config config/final_config/grid_4x4_ace_3.json --seeds 6,7,8,9 --variants swap-c1-l2,swap-c2-l2,swap-c3-l2,swap-c4-l2,odg --workers 2 --output output/swap-revert-reproduction
```
