# ACE congestion budget study — plan

**Status: PLAN ONLY. No results yet. Nothing in this document is measured.**

## The question

The ten-workload characterization produced a per-core congestion heatmap, but it
simulates no physics: it counts how often a core's incident hop demand in a layer
exceeds its communication capacity. It shows *where* pressure concentrates, not
what that pressure costs.

This study puts physics behind the structure and answers: **what does
communication-memory congestion cost in request latency and delivered EPR
fidelity?**

Two cases, as posed:

- **Case 1 — congestion present.** 2, 3 or 4 communication qubits per core.
- **Case 2 — congestion removed.** Enough communication qubits that no core-layer
  can ever exceed capacity.

## Why "unlimited" is 32

Not an arbitrary large number. From `aggregate_workloads.csv`, the peak
core-layer demand over the selected workloads is:

| Workload | Peak core-layer demand |
| --- | ---: |
| QFT | 24 |
| QAOA | 18 |
| Graph state | 13 |
| Draper QFT adder | 11 |
| GHZ (control) | 2 |

The maximum is 24, so **any budget of 24 or more guarantees that no core-layer
ever exceeds capacity** — congestion is structurally impossible, not merely rare.
This study uses 32, with a 64-memory arm on QFT to confirm 32 already saturates
(if 64 reproduces 32 run-for-run, 32 is genuinely the unlimited case).

## Scope

| Axis | Values |
| --- | --- |
| Backend | ACE |
| Workloads | `qft`, `qaoa`, `draper_qft_adder`, `graphstate` — the four congested workloads from the characterization |
| Control | `ghz` — zero overloaded layers, peak demand 2 |
| Mapping seeds | 42, 43, 44 |
| Physics seeds | 0, 1, 2 |
| Budgets | 2, 3, 4, 32 (+64 on QFT) |
| Policies | `on-demand`, `dynamic` |

Traces are the ones the characterization already produced
(`<workload>/seed_<n>/requests.txt`), so the structural numbers and these
physical numbers describe the same mapped circuits.

### Why GHZ is included

GHZ has zero overloaded layers at every budget. If its latency moves when the
budget changes, the measurement is picking up something other than congestion and
the whole study is invalid. It is a falsification control, not a result.

### Why both policies

- **`on-demand`** reserves nothing for a compiler, so the entire bank serves
  demand. This isolates contention with no pre-generation effect mixed in — it is
  the clean congestion measurement.
- **`dynamic`** is the project's policy, and answers whether congestion costs more
  or less once pre-generation is in play.

They are **not** compared against each other here (see Known limits).

## Memory partitioning per budget

| Budget | `--total-memories` | `--compiler-memories` | Demand bank |
| ---: | ---: | ---: | ---: |
| 2 | 2 | 1 | 1 |
| 3 | 3 | 2 | 1 |
| 4 | 4 | 3 | 1 |
| 32 | 32 | 31 | 1 |
| 64 | 64 | 63 | 1 |

`on-demand` always takes `--compiler-memories 0`, so the whole bank serves demand.

For `dynamic` the rule is `compiler = budget - 1`, holding one slot for demand.
At a budget of four this reproduces the project's established 3+1 split, so the
standard configuration remains a point on the curve rather than a special case.

## Two code changes this study requires

Both are committed before any run, so the result is reproducible from one branch.

### 1. `node.py` — classical message routing (REQUIRED, blocks everything)

This branch's `node.py` has no `send_message` override, so a message carries no
`dst`/`src` and `receive_message` raises
`AttributeError: 'NetworkManagerMessage' object has no attribute 'dst'`.

ACE meshes only have neighbour classical channels, so a message to a non-adjacent
core must be forwarded hop by hop. The fix — already present and working on
`codex/strict-compiler-4plus0` — stamps the final destination on the message and
forwards one XY hop at a time.

This was previously misdiagnosed as requiring the unreachable
`anub-dota/qnoc-stress-testing` fork. It does not: the fix is local, and porting
it makes ACE run from this branch alone.

### 2. Entanglement-efficiency instrumentation (measurement, no physics change)

`compiler_waste_percentage` is computed by the compiler controller, so it exists
only for compiler policies and is blank for the autonomous caches — the two
families cannot be compared on efficiency.

The adaptive-continuous protocol already counts
`num_generated/used/unused_entanglement_pairs` on every router under every
policy, but `parallel_core.py` never surfaces them. Aggregating them into `stats`
gives one efficiency metric defined identically for every policy.

**This is instrumentation only.** It must be regression-checked: the locked
Random-16 and QFT-96 validation numbers must reproduce to zero difference, or the
patch is wrong.

## Metrics

| Metric | Why |
| --- | --- |
| `average_request_latency_ms` | the primary cost of congestion |
| `average_delivered_epr_fidelity` | does congestion cost fidelity, or only time? |
| `protocol_generated/used/unused_pairs` | entanglement spent per unit of work |
| `pregenerated_success_rate` | share of requests whose pair was genuinely ready |
| `on_demand_fallback_rate` | share that fell back |
| `completion_rate` | **invariant: must be 1.0 everywhere** |

## Validity checks, to run before interpreting anything

1. Every run's trace SHA-256 matches the source file in the characterization archive.
2. Every run's recorded `total_memories` matches the intended budget.
3. `completion_rate == 1.0` in every run. Fallback is recovery, not failure, but a
   dropped request invalidates the run.
4. GHZ latency is flat across budgets within a mapping seed.
5. The 64-memory QFT arm reproduces the 32-memory arm run for run.
6. The instrumentation patch reproduces the locked validation numbers exactly.

## Known limits, to state in any writeup

1. **ACE serializes to one request per core per batch**
   (`serialize_core_conflicts`). Absolute latencies are dominated by that
   scheduling constraint. Budget comparisons within ACE are valid because every
   arm carries it identically; the absolute milliseconds are not a clean measure
   of congestion alone.
2. **`on-demand` and `dynamic` are not comparable to each other here** —
   on-demand has the whole bank for demand, dynamic has one slot. Only
   within-policy budget sweeps are supported.
3. **ACE milliseconds must never be compared with native SeQUeNCe milliseconds.**
   Compare policies only within a backend.
4. **The structural percentages are not physical results.** The heatmap counts
   structure; this study measures time and fidelity. They must not be merged into
   one table.
5. **Three mapping seeds and three physics seeds per point.** Confidence intervals
   over a larger seed count are not computed.
6. **Graph state has only 6 communication-active layers**, so its structural
   percentage rests on a very small denominator and should be quoted with that
   caveat.

## What this study does NOT claim

- It does not claim congestion-aware routing is implemented or successful.
- It does not claim a latency ordering between pre-generation policies; that needs
  the separate CGP/ACGP/fixed/dynamic comparison at a matched budget.
- It does not revise any historical table. Historical and repaired results stay
  separate.
