# ACE congestion budget study, rerun under the corrected scheduler (Gate 6)

Same 126 invocations (378 runs) as the published study `results/ace_congestion_budget_2026-10-23`: mapping seeds
42 to 44, physics seeds 0 to 2, 2/3/4/32 communication memories per core (64 on QFT), policies on-demand and dynamic.
Driver: `tools/ace_budget_rerun/run_budget_sweep.py`. Data: `results/ace_budget_rerun_2026-10-24/`.
ACE-internal numbers only; never compare these milliseconds with native SeQUeNCe's.

## The driver reproduces the published study

Run with `--scheduler legacy`, the 378 rows match the published `results.csv` in **every column** (0 differing cells
out of 378 x 58). So the rerun differs from the published study only by the scheduler.

## What changed

Each cell is `legacy → per-qubit`, mean over 9 runs (3 mapping x 3 physics seeds). Latency is the common definition
(`average_eligible_latency_ms`): from the moment a request could first be asked for, so waiting is counted under both.

### Request latency (ms), common definition

| Workload | Policy | 2 mem | 3 mem | 4 mem | 32 mem |
|---|---|---:|---:|---:|---:|
| GHZ (control) | on-demand | 1.17 → 1.17 | 1.17 → 1.17 | 1.17 → 1.17 | 1.17 → 1.17 |
| GHZ (control) | dynamic | 0.51 → 0.51 | 0.26 → 0.26 | 0.26 → 0.26 | 0.26 → 0.26 |
| Graph state | on-demand | 9.98 → 2.72 | 9.98 → 1.53 | 9.98 → 1.24 | 9.98 → 1.18 |
| Graph state | dynamic | 9.05 → 6.36 | 8.42 → 5.01 | 7.91 → 3.23 | 7.28 → 0.25 |
| Draper QFT adder | on-demand | 9.40 → 2.16 | 9.40 → 1.30 | 9.40 → 1.15 | 9.40 → 1.13 |
| Draper QFT adder | dynamic | 8.57 → 4.55 | 7.91 → 3.67 | 7.55 → 2.48 | 7.05 → 0.25 |
| QAOA | on-demand | 13.39 → 3.42 | 13.39 → 1.74 | 13.39 → 1.27 | 13.39 → 1.13 |
| QAOA | dynamic | 12.56 → 6.89 | 11.84 → 5.33 | 11.34 → 3.88 | 10.14 → 0.25 |
| QFT | on-demand | 25.06 → 4.72 | 25.06 → 2.39 | 25.06 → 1.59 | 25.06 → 1.13 |
| QFT | dynamic | 23.95 → 10.06 | 23.03 → 7.49 | 22.30 → 5.57 | 20.28 → 0.25 |

### Makespan (s)

| Workload | Policy | 2 mem | 3 mem | 4 mem | 32 mem |
|---|---|---:|---:|---:|---:|
| GHZ (control) | on-demand | 0.3 → 0.3 | 0.3 → 0.3 | 0.3 → 0.3 | 0.3 → 0.3 |
| GHZ (control) | dynamic | 0.3 → 0.3 | 0.3 → 0.3 | 0.3 → 0.3 | 0.3 → 0.3 |
| Graph state | on-demand | 0.4 → 0.3 | 0.4 → 0.2 | 0.4 → 0.2 | 0.4 → 0.2 |
| Graph state | dynamic | 0.4 → 0.3 | 0.4 → 0.3 | 0.4 → 0.3 | 0.3 → 0.2 |
| Draper QFT adder | on-demand | 7.6 → 5.1 | 7.6 → 4.9 | 7.6 → 4.9 | 7.6 → 4.9 |
| Draper QFT adder | dynamic | 7.4 → 5.9 | 7.1 → 5.5 | 7.0 → 5.0 | 6.7 → 4.4 |
| QAOA | on-demand | 12.8 → 6.6 | 12.8 → 5.7 | 12.8 → 5.5 | 12.8 → 5.4 |
| QAOA | dynamic | 12.4 → 8.5 | 12.0 → 7.4 | 11.7 → 6.6 | 10.8 → 4.7 |
| QFT | on-demand | 13.2 → 5.7 | 13.2 → 4.9 | 13.2 → 4.7 | 13.2 → 4.5 |
| QFT | dynamic | 12.9 → 7.5 | 12.6 → 6.5 | 12.3 → 5.8 | 11.4 → 4.1 |

### Delivered EPR fidelity

| Workload | Policy | 2 mem | 3 mem | 4 mem | 32 mem |
|---|---|---:|---:|---:|---:|
| GHZ (control) | on-demand | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 |
| GHZ (control) | dynamic | 0.9344 → 0.9344 | 0.9254 → 0.9254 | 0.9254 → 0.9254 | 0.9254 → 0.9254 |
| Graph state | on-demand | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 |
| Graph state | dynamic | 0.9346 → 0.9341 | 0.9223 → 0.9236 | 0.9116 → 0.9189 | 0.8736 → 0.9112 |
| Draper QFT adder | on-demand | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 |
| Draper QFT adder | dynamic | 0.9338 → 0.9368 | 0.9195 → 0.9257 | 0.9094 → 0.9218 | 0.8838 → 0.9158 |
| QAOA | on-demand | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 |
| QAOA | dynamic | 0.9372 → 0.9390 | 0.9244 → 0.9298 | 0.9124 → 0.9245 | 0.8643 → 0.9143 |
| QFT | on-demand | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 | 0.9498 → 0.9498 |
| QFT | dynamic | 0.9363 → 0.9386 | 0.9224 → 0.9306 | 0.9100 → 0.9274 | 0.8413 → 0.9202 |

## Reading it

* **The budget now binds.** Under the legacy scheduler on-demand latency is the same at every budget (QFT 25.06 ms at
  2, 3, 4 and 32 memories), the published study's central finding. Under the per-qubit scheduler it falls with the
  budget (QFT 4.72, 2.39, 1.59, 1.13 ms) and reaches its floor at 32. The 64-memory arm on QFT reproduces 32 (1.13 and
  0.25 ms), so 32 is saturated. On-demand fidelity does not move: it is set by generation, not by waiting.
* **The zero-congestion control.** GHZ on-demand latency is 1.17 ms at every budget under both schedulers, as it must be.
  GHZ under dynamic still moves between 2 and 3 memories under both (0.51 to 0.26 ms): the published README attributes
  that to planner coverage (one cached slot at a budget of two), not congestion, and this rerun does not change it.
* **Absolute latency is lower under the new scheduler** because it no longer forces requests that could run together
  to run one after another. That is the effect of removing the serialization, not of anything physical.
* **Dynamic at 32 memories** gives 0.25 ms for every workload (everything is pre-generated), and its fidelity under the
  new scheduler is higher than under the legacy one (QFT 0.9202 against 0.8413). I did not trace why; a shorter run
  means pairs spend less time stored, which fits but is not shown here.
* Rejections under the new scheduler are few (at most 6 per run, mean over seeds, in these cells).

## Limits

* Invariants were checked on the audit matrices (Gate 4), not inside these sweep runs; the sweep records completion
  (all 378 rows complete every request, status ok).
* Physical parameters are ACE's defaults and are undecided (`ace-physical-parameters.md`); changing coherence time
  would change every dynamic-policy fidelity.
* These are structural-plus-physical ACE results from one machine and one parameter set; conclusions about routing
  or mapping need more than this.
