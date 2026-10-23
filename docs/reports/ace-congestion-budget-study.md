# ACE congestion budget study — results

**Run date:** 2026-10-23 · **Data:** `results/ace_congestion_budget_2026-10-23/`
**Plan:** [`docs/plans/ace-congestion-budget-study.md`](../plans/ace-congestion-budget-study.md)
**Column meanings:** [`docs/reference/metrics-glossary.md`](../reference/metrics-glossary.md)

378 runs, 0 failures, 100% request completion, every trace hash verified.

## Headline: this study does not measure congestion, and the control proves it

**ACE cannot measure communication-memory contention, by construction.** The
result is negative, and it is the most important thing in this document, because
it means the budget-versus-latency numbers below must not be read as a congestion
cost.

Two independent findings establish it.

### 1. On-demand latency is completely insensitive to the memory budget

| Workload | c=2 | c=3 | c=4 | c=32 | Distinct values |
| --- | ---: | ---: | ---: | ---: | ---: |
| QFT | 1.11155810 | 1.11155810 | 1.11155810 | 1.11155810 | **1** |
| QAOA | 1.11323536 | 1.11323536 | 1.11323536 | 1.11323536 | **1** |
| Draper adder | 1.12263505 | 1.12263505 | 1.12263505 | 1.12263505 | **1** |
| Graph state | 1.15836543 | 1.15836543 | 1.15836543 | 1.15836543 | **1** |
| GHZ | 1.17132843 | 1.17132843 | 1.17132843 | 1.17132843 | **1** |

Not approximately equal — identical to every digit. Going from 2 communication
memories to 32 changes nothing at all. If memory were ever contended, it could not
be.

### 2. The zero-congestion control moved, which it must not do

GHZ has **zero overloaded layers at every budget** and a peak core-layer demand of
2. Under `dynamic` its latency nevertheless changes with the budget:

| Mapping seed | c=2 | c=3 | c=4 | c=32 |
| --- | ---: | ---: | ---: | ---: |
| 42 | 0.50834247 | 0.26250066 | 0.26250066 | 0.26250066 |
| 43 | 0.50834264 | 0.26250066 | 0.26250066 | 0.26250066 |
| 44 | 0.51945410 | 0.26250066 | 0.26250066 | 0.26250066 |

A workload that cannot be congested is not allowed to respond to a congestion
knob. It did. **The control failed, so the quantity being measured is not
congestion.**

### Why: ACE serializes the congestion away before the simulator sees it

`ParallelLayerRequestManager.__init__` applies `serialize_core_conflicts`
unconditionally whenever a compiler controller is attached — which is every
strategy in this study, on-demand included. The `serialize_conflicts` argument at
the call site is therefore dead for these runs; setting it to `False` changes
nothing, which was verified directly.

That function rewrites each trace layer into batches in which **no core appears
twice**:

| Workload | Trace layers | ACE batches | Peak core demand per trace layer | Peak core demand per ACE batch |
| --- | ---: | ---: | ---: | ---: |
| QFT | 382 | 2,065 | **24** | **1** |
| QAOA | 367 | 1,996 | 18 | **1** |
| Draper adder | 470 | 1,224 | 10 | **1** |
| Graph state | 25 | 66 | 11 | **1** |
| GHZ | 50 | 59 | 2 | **1** |

A core never serves more than one request at a time, so it never needs more than
one communication memory. A budget of 2 is already surplus; 32 is no different.
The hotspot the characterization found — 24 simultaneous demands on one core — is
flattened to 1 before any physics runs.

## What the budget axis actually controls: planner coverage

Under `dynamic`, latency does move with the budget — but it is tracking how many
preparations the offline planner could schedule, not contention.

| Workload | Budget | Planner coverage | Readiness | Latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| GHZ | 2 | 75.0% | 75.00% | 0.50834 |
| GHZ | 3 | 100.0% | 100.00% | 0.26250 |
| QFT | 2 | 21.1% | 20.88% | 0.92431 |
| QFT | 3 | 39.3% | 39.10% | 0.76669 |
| QFT | 4 | 53.3% | 53.16% | 0.64797 |
| QFT | 32 | 100.0% | 99.91% | 0.25020 |

Across all five workloads and four budgets:

- **correlation(planner coverage, readiness) = +1.0000**
- **correlation(readiness, latency) = −0.9975**

Planner coverage predicts readiness exactly, and readiness predicts latency almost
exactly. The memory budget is acting purely as a cap on how much the planner is
allowed to pre-generate. GHZ fits the same relationship as QFT despite having no
congestion at all, which is what makes the interpretation unambiguous.

## Results, read correctly

With the above understood, the `dynamic` numbers are a **pre-generation coverage
sweep**, and are reported as such.

### Latency (ms), dynamic — effect of pre-generation coverage

| Workload | Peak | c=2 | c=3 | c=4 | c=32 |
| --- | ---: | ---: | ---: | ---: | ---: |
| QFT | 24 | 0.92796 | 0.76805 | 0.65395 | 0.25020 |
| QAOA | 18 | 0.91454 | 0.73649 | 0.60752 | 0.25003 |
| Graph state | 13 | 0.84388 | 0.62501 | 0.48554 | 0.25000 |
| Draper adder | 11 | 0.83620 | 0.59515 | 0.46828 | 0.25008 |
| GHZ (control) | 2 | 0.51205 | 0.26250 | 0.26250 | 0.26250 |

On-demand sits at 1.111–1.171 ms for every workload at every budget. Full
pre-generation coverage reduces request latency to roughly 0.25 ms, a ~4.4x
reduction — and that figure is a **pre-generation** result, not a congestion
result.

### Fidelity, dynamic — the cost of preparing early

| Workload | c=2 | c=3 | c=4 | c=32 |
| --- | ---: | ---: | ---: | ---: |
| QFT | 0.93628 | 0.92243 | 0.91004 | 0.84130 |
| QAOA | 0.93718 | 0.92443 | 0.91242 | 0.86429 |
| Draper adder | 0.93381 | 0.91951 | 0.90941 | 0.88381 |
| Graph state | 0.93455 | 0.92227 | 0.91162 | 0.87363 |
| GHZ (control) | 0.93439 | 0.92545 | 0.92545 | 0.92545 |

On-demand fidelity is **0.94981 in all 189 on-demand runs**, at every budget and
every workload, because nothing is ever stored.

The mechanism is visible directly in the creation-to-utilization gap (QFT):

| Budget | Fidelity at creation | At utilization | Gap | Delivered |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 0.94981 | 0.88649 | 0.06332 | 0.93628 |
| 4 | 0.94981 | 0.87489 | 0.07493 | 0.91004 |
| 32 | 0.94981 | 0.84145 | **0.10836** | 0.84130 |

Every pair is born at the same fidelity. Wider coverage means more pairs are
prepared further ahead, so they sit longer and decohere more. **Pre-generation
buys latency and pays for it in fidelity** — a real trade, and the clearest
physical result in this study.

### Entanglement cost

Pairs generated by `dynamic`:

| Workload | c=2 | c=3 | c=4 | c=32 |
| --- | ---: | ---: | ---: | ---: |
| QFT | 1,069 | 1,999 | 2,658 | 5,020 |
| QAOA | 1,414 | 2,652 | 3,582 | 6,136 |
| Draper adder | 840 | 1,557 | 1,941 | 2,620 |
| Graph state | 48 | 84 | 107 | 152 |
| GHZ | 36 | 48 | 48 | 48 |

`protocol_waste_percentage` is **0.00% in every dynamic run**: every pair the
compiler created was consumed. With the repaired reservation lifecycle and dynamic
choosing the latest feasible layer, nothing is made that goes unused. On-demand
generates 0 pre-generated pairs by construction, in all 189 runs.

## Validity checks

| Check | Result |
| --- | --- |
| Runs completing | 378/378 |
| Trace SHA-256 matches characterization archive | 378/378 |
| `completion_rate == 1.0` | 378/378 |
| Identity: `intended_request_hits == utilized_compiler_pairs` | 189/189 dynamic rows (see Erratum) |
| Memory partition consistent with request | 378/378 |
| On-demand speculative cap == 0 | 189/189 |
| Physics seeds per point | 3 everywhere |
| QFT c=32 vs c=64 saturation | identical run for run, both strategies |
| Zero-congestion control flat | **FAILED under dynamic** (see headline) |

The simulator was confirmed to be executing real physics: 386 photon emissions,
157 BSM herald measurements, 162 detections and 682 decoherence applications in a
single Graph state run; delivered fidelities take 53 distinct values spanning
0.758–0.950; results are stochastic across physics seeds and bit-reproducible
within one. Every code change in this study was regression-checked against the
locked Random-16 and QFT-96 validation numbers, which reproduce to zero
difference.

## What to do about it

Measuring congestion in ACE requires lifting the serialization, so that a core can
hold several concurrent requests and the memory budget can bind. That is a change
to `ParallelLayerRequestManager`, not a parameter, and it would alter the workload
submission schedule that every historical ACE result was produced under. It should
be done as a separate, clearly-labelled arm rather than silently.

Until then, the native SeQUeNCe backend is the only place the budget has been
shown to change on-demand latency (`docs/reports/congestion-memory-sweep.md`:
3.2–11.9% at a four-memory budget, up to 58.4% at two). That is a **conditional,
hop-level** result, not yet a verified execution schedule: the native runs
submitted every hop at its trace-layer time with no conflict serialization and no
same-qubit dependency ordering (`conflict_serialization = None` in all 126 run
records), so a relayed qubit's two sequential hops were demanded concurrently.

The serialization is the leading explanation for why the two backends disagree,
and it is sufficient to explain ACE's flat on-demand curve: with at most one
request per core per batch, no core can need a second memory. It has **not** been
isolated by an A/B in which ACE runs with the serialization lifted. That run is the
direct test of whether ACE's physics is consistent with the native backend's.

## Caveats

1. ACE milliseconds must never be compared with native SeQUeNCe milliseconds.
2. `on-demand` and `dynamic` are not comparable to each other here: on-demand has
   the whole bank for demand, dynamic holds one slot back.
3. Three mapping seeds and three physics seeds per point; no confidence intervals.
4. Graph state has only 6 communication-active layers in the structural study, so
   its characterization percentage rests on a very small denominator.
5. The structural percentages come from the ten-workload study, which simulates no
   physics, and must not be merged into these tables.
6. Generation capacity was scaled with the memory budget. Pinned at 3, the
   unlimited case is not unlimited — QFT reaches only 97.8% planner coverage and
   QAOA 93.1%, limited by generation rather than memory. At c=4 the scaled value
   is 3, so the project's standard configuration is unchanged.

## Erratum (added after an independent review)

Two statements in the first version of this study were wrong.

1. **`intended_request_hit_rate` is not an identity invariant.** The scheduler
   computes it as `intended_request_hits / requests`, so it is a coverage rate and
   is below 1.0 whenever a request falls back. It is 1.0 in only 72 of 189
   dynamic rows and 0.0 in all 189 on-demand rows, as expected. The validity table
   originally read "72/72 compiler runs"; that was a misreading of the generated
   `verification.txt`, which printed `72/378`. The identity check that actually
   tests provenance is `intended_request_hits == utilized_compiler_pairs`, which
   holds in 189 of 189 dynamic rows. The glossary has been corrected.
2. **"The difference is the serialization" was stated as established.** It is the
   leading explanation and is sufficient for the ACE side, but it was not isolated
   by an experiment. See "What to do about it".

Neither error changes the headline: ACE's on-demand latency is identical at every
budget, the zero-congestion control moves under `dynamic`, and the budget axis
tracks planner coverage.
