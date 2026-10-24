# ACE correctness, then the congestion study: working plan

**Status: PLAN. Nothing in this document is a measured result.**
Written 2026-10-24. Branch `codex/ace-scheduler-correctness`.

The order is fixed: **ACE correctness is finished first, all the way, and only then do the
experiments run.** The congestion study of 2026-10-23 showed why: ACE's per-core serialization
and its reservation-equality bug stop memory contention from ever occurring, so any experiment
on the current ACE would measure the wrong thing
([report](../reports/ace-congestion-budget-study.md)).

## Part A. ACE correctness

| Gate | What | Exit condition |
| --- | --- | --- |
| 0 | Clean workspace; legacy baseline recorded bit for bit (`tools/ace_correctness/baseline.py`) | tests green; baseline reproduces under a fresh process and a different hash seed; locked and published numbers reproduced |
| 1 | Audit the unknowns; event log and invariant checker | checker flags the known aliasing failure and passes a correct run; hooks leave legacy output identical |
| 2 | Reservation identity: every reservation compares by a unique job id | legacy baseline unchanged where aliasing never occurred; aliasing microcase completes with no retry |
| 3 | Scheduler: per-qubit hop order replaces per-core serialization; generation separated from use | every invariant holds; legacy mode still bit for bit |
| 4 | Verification: microcases, reference-model check, randomized small traces, real-simulator event logs | every mismatch causally explained |
| 5 | Physical parameters made explicit and configurable, defaults unchanged | sourced parameter table |
| 6 | Rerun the budget study under the corrected scheduler as validation | controls pass; effect traceable to measured capacity waiting |

**Decisions already made.** Escape reserve R = 1 memory per core, equal to ACE's existing demand
bank. The mapped trace files are taken as given; routing research is set aside for now.

**Scheduler rules (design, to be proven by Gate 4).**
R1 a hop's pair is admitted only if both endpoints can be reserved at once.
R2 pairs generated before their qubit is ready may hold at most M - R memories at a core.
R3 ready hops are served in the order they became ready.
Generation of a later hop may begin before an earlier hop of the same qubit is delivered; only the
use of the pairs is ordered.

**Still open, needing a decision.** Which physical parameter set the study intends (coherence
time 1 s in ACE against 1 ms in the native backend and the ACGP paper's table; memory efficiency
0.95 against 0.85). Whether the on-demand baseline starts a route's hops just in time or all at
once. Whether pre-generation uses a fixed bank split or a shared pool.

## Part B. Experiments, after Part A

### B1. All ten benchmarks, memory slots per core
Latency and delivered fidelity of every benchmark in the characterization archive, with congestion
measured, repeated at several communication-memory budgets per core. Purpose: see how much
congestion there is, how memory slots change it, and how much a good routing algorithm could help.

* Inputs: exactly the archived traces, checked by SHA-256, with the same mapping and physics seeds
  in every arm.
* On-demand first, to isolate contention; then compiler pre-generation.
* Budgets include low values and a saturated case; anything beyond the modelled physical slots is
  labelled counterfactual.
* Required controls: a zero-congestion workload must not respond to the budget; a saturation check;
  completion 100%.
* Report per-seed values with uncertainty, never only means.

### B2. Own demand against relay demand, per core
Split each core's congestion into the part caused by the core being the **source or destination**
of a move and the part caused by it being a **relay**.

Definitions:

* A *route* is the consecutive hops of one qubit within one layer. Its first source and its final
  destination are the *endpoints*; every core in between is a *relay*.
* For a core and a layer, `D` is the number of hop requests touching the core. `D_end` counts those
  where the core is an endpoint of the route. `D_relay` counts those where it is a relay; a relay
  contributes two, one arriving and one leaving. `D = D_end + D_relay`.
* With capacity `C`, a layer is overloaded for the core when `D > C`. Counterfactually:
  * overloaded by its own demand alone: `D_end > C`;
  * overloaded only because of relay traffic: `D_end <= C < D`.

These two sets are disjoint and together are exactly the overloaded layers, so the percentages add
up to the heatmap's percentage. Also reported: for overloaded layers, the mean share of demand that
is relay, and the same split for the excess `max(0, D - C)`.

How it will be checked: the totals must reproduce the archive's per-core percentages (all 160
heatmap cells), and `sum of D_relay` must reproduce `internal_relay_incidences` in
`all_trials_cores.csv`. The split is computed twice, once counting hops as the archive does and once
counting the qubits that would be in flight at the same time under per-qubit ordering, and each
number says which one it is.

### B3. Other topologies (large, later)
The mapper supports mesh, torus, line, tree and all-to-all. Everything in B1 and B2 repeated per
topology. Scoped separately once B1 and B2 are done.

## Conventions

* Commit message first line: `[abisfa] - <short description>`; one logical piece of work per commit.
* Push only when asked.
* Every claim is checked against source or by running it. What was not read is said so.
* The legacy baseline must pass after every change to ACE; results from the legacy and corrected
  schedulers are never merged into one table.
