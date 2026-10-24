# Memory cut-off time: what ACE already has, what it does, and what it misses

**Question.** A *memory cut-off time* is a threshold after which a stored EPR pair is discarded and a new pair is generated. Is anything like it already in ACE?

**Answer: yes, three timers end the life of a stored pair, and the first is exactly a cut-off.** All of the following was read in the source and, where marked *measured*, run.

| Timer | Where | Default in ACE | What it does |
|---|---|---|---|
| **Memory cut-off** (`cutoff_ratio` x `coherence_time`) | SeQUeNCe `components/memory.py` (`_schedule_expiration`, `expire`), ACE `resource_manager.py:169` | ratio 1, so the cut-off equals the coherence time, 1 s | When a pair is stored, an expiry is scheduled `cutoff_ratio x coherence_time` later. At expiry the memory is reset (unless it is in an application) and returned to the free state; ACE removes the pair from its cache and tells the compiler controller it expired. |
| **Reservation window** | ACE `adaptive_continuous.py:213-224` (compiler pairs), `:166` (autonomous caches) | compiler pairs 1000 ms; caches: to the next 0.2 s period boundary (`node.py:57`, `period=2e11` ps) | A pair's booking ends with its window; an unused pair is released then (reason `reservation_expired`). |
| **Planner lifetime** (`--coherence-time-layers`) | `compiler_trace.plan_preparations` | 10 layers | A *planning assumption* only: how far ahead a pair may be prepared. Nothing ties it to the physical cut-off. |

Separately, the stored state decoheres continuously at rate 1/coherence time (SeQUeNCe `decoherence_rate`); that lowers fidelity but discards nothing.

**The cut-off is configurable but unused.** `cutoff_ratio` is a parameter of SeQUeNCe's `MemoryArray`; ACE's configuration never sets it, so it stays at 1. Measured: a `cutoff_ratio` written into the template reaches every memory (0.5 and 0.01 gave cut-offs of 0.5 s and 0.01 s with a 1 s coherence time). The coherence time itself is 1 s, so by default no pair ever reaches its cut-off in these runs (none expired in any audited run).

## What happens after a discard (measured)

Run with the invariant monitor on GHZ and graph state (compiler pre-generation, 4 memories, per-qubit scheduler, one physics seed), varying the timers
(`results/cutoff_study_2026-10-24/mechanism.csv`, `tools/cutoff_study/mechanism.py`). Every case completes every request with no invariant violated.

| Case | GHZ: pairs consumed / released by window / cut-off resets | Graph state: same |
|---|---|---|
| ACE default (cut-off 1 s, window 1000 ms) | 48 / 0 / 0 | 104 / 0 / 0 |
| window 20 ms only | 36 / 12 / 0 | 48 / 56 / 0 |
| cut-off 20 ms (ratio 0.02), window 1000 ms | 34 / 12 / 12 | 24 / 32 / 32 |
| cut-off 5 ms (ratio 0.005), window 1000 ms | 0 / 34 / 34 | 0 / 34 / 34 |
| cut-off 20 ms and window 20 ms | 36 / 12 / 0 | 48 / 56 / 0 |

* **The earlier timer wins.** With both at 20 ms the window fires first, the memory is released and the pending cut-off is cancelled, so no cut-off reset happens.
* **For compiler pairs a cut-off discards the pair and nothing replaces it.** The controller's handler only marks the pair "expired" in its records (`compiler_scheduler.py:187`); it does not prepare another. The request that wanted the pair
  generates its own on demand, so all requests still complete, but the run gets longer (graph state: 274.5 ms makespan by default, 351.8 ms at a 20 ms cut-off, 347.4 ms at 5 ms).
* **The booking outlives the discarded pair.** In every case the number of releases by window expiry equals the number of cut-off resets, which is what one would see if each discarded pair's booking stays until its window ends (inferred from the counts; not traced event by event). With a 5 ms cut-off no compiler pair survives to be used (consumed 0).
* The compiler bookings rise strongly under a short cut-off (graph state 134 to 339 at 5 ms) without more pairs being delivered; I did not trace why.

## The autonomous caches regenerate (measured)

Random-16 trace, per-qubit scheduler, 4 memories (3 cache), coherence 1 s, continuous cache strategy
(`results/cutoff_study_2026-10-24/cache_strategies_random16.csv`):

| Cut-off | Pairs generated | Pairs used | Reported waste | Real unused share | Latency | Fidelity |
|---|---:|---:|---:|---:|---:|---:|
| ACE default (1 s) | 44,936 | 90 | 99.7% | 99.80% | 5.15 ms | 0.9297 |
| 200 ms (ratio 0.2) | 44,936 | 90 | 99.7% | 99.80% | 5.15 ms | 0.9297 |
| 20 ms (ratio 0.02) | 447,388 | 122 | 10.0% | 99.97% | 4.87 ms | 0.9354 |

* A cut-off of 200 ms changes nothing: the cache's reservation window already ends at the next 0.2 s period boundary, so no pair reaches it. Only a cut-off shorter than the epoch acts.
* At 20 ms the cache **discards and regenerates**: ten times more pairs are generated. The pairs that are used are fresher (fidelity 0.9297 to 0.9354) and latency falls slightly (5.15 to 4.87 ms), because fewer requests wait behind stale pairs; the adaptive-continuous strategy gives the same numbers as continuous here.
* **ACE's waste metric is blind to cut-off discards.** `protocol_unused_pairs` is incremented only when a generation rule expires at the window end (`adaptive_continuous.py:377`); a cut-off discard goes through `note_memory_expiration`, which does not touch it. So the reported waste drops from 99.7% to 10.0% although 99.97% of the generated pairs were never used. Any waste figure measured with a cut-off needs `1 - used / generated` instead.

## What to decide

1. **Semantics.** If "cut-off" should mean *discard and regenerate*, the autonomous caches already do; compiler pre-generation discards and falls back to on-demand, and re-preparing the pair would be a new feature.
2. **Parameter.** Expose the cut-off as a first-class study parameter (milliseconds, converted to the ratio) instead of through the template, and record it in `run_parameters.json`.
3. **Consistency.** Tie the planner's lifetime to the cut-off, and fix the waste counter, before reporting waste under a cut-off.
4. **Value.** With ACE's 1 s coherence the cut-off never acts; with the group's 1 ms coherence a cut-off equal to the coherence time would discard every cached pair before use (as the sensitivity arm of Experiment 1 showed). The choice of coherence time comes first.

Limits: the compiler mechanism was measured on GHZ and graph state with one physics seed; the cache measurement on one trace and one seed; no sweep of cut-off against memory budget was run.
