# Base execution plan — 2026-10-26

The first final-data phase is now frozen in
[`execution_spec.json`](../../../results/golden_study_2026-10-25/execution_spec.json).
It contains every scientific and runner parameter; the Python planner supplies no
workload, route, memory, seed, or timing default.

## Exact size

The plan contains 150 conceptual T-HQA route aliases: ten workloads, three
mapper/reliability seeds, four mesh routes, and one torus route. Exact SHA-256
deduplication reduces them to 110 physical request traces without discarding an
alias:

| Route family | Conceptual aliases | Distinct trace hashes | Why |
| --- | ---: | ---: | --- |
| Mesh XY | 30 | 10 | Placement and deterministic XY route are identical across the three seeds. |
| Mesh YX | 30 | 10 | Placement and deterministic YX route are identical across the three seeds. |
| Mesh shortest-reliable | 30 | 30 | Reliability maps differ by seed and change route choice/tie-breaking. |
| Mesh maximum-reliability | 30 | 30 | Reliability maps differ by seed and change route choice. |
| Torus Dijkstra | 30 | 30 | Dijkstra uses the seeded weighted/reliability graph. |
| **Total** | **150** | **110** | Only byte-identical request traces are collapsed. |

For each distinct trace the base phase enumerates total communication memories
`2, 3, 4, 6, 8, 16, 32, 64`. ODG is run once per total-memory value. CGP, ACGP,
Dynamic full-chain, and Dynamic first-hop each enumerate every compiler/cache
allocation `C=0..M-1`. With 30 paired physics seeds this produces:

- 30,580 resumable runner jobs;
- 1,808,400 actual policy-seed simulator evaluations.

This supersedes the earlier rough 822,000 estimate, which incorrectly treated all
three reliability-aware route seeds as byte-identical.

## Correctness and resume rules

The compressed job manifest is
[`base-evaluation_jobs.jsonl.gz`](../../../results/golden_study_2026-10-25/manifests/base-evaluation_jobs.jsonl.gz),
with its hash and aggregate counts in
[`base-evaluation_plan.json`](../../../results/golden_study_2026-10-25/manifests/base-evaluation_plan.json).
The launcher requires an explicit Python interpreter and worker count, records the
exact command and Git commit, and writes to a partial directory. It promotes a job
only when every expected strategy/seed row exists and `completion_rate == 1.0`.
An existing `summary.csv` is never enough for resume: the execution-record job hash,
trace hash, config hash, row set, and runner metadata must all match.

The phase also has an immutable
[`source lock`](../../../results/golden_study_2026-10-25/manifests/base-evaluation_source-lock.json).
It hashes the ACE runner, scheduler, compiler controller, physical protocols, metric
code, and supporting invariant/event modules. It also requires the imported
SeQUeNCe checkout to be clean at Git commit `cf5283c`. Existing jobs are checked by
reading these files from their recorded Git commit, so documentation-only commits
may differ without mixing simulator implementations.

`C=0` is a tested boundary. CGP, ACGP, and Dynamic admit no pre-generated pairs and
reduce exactly to ODG rather than crashing or silently borrowing compiler memory.

## Adaptive-congestion phase

Dynamic congestion-adaptive is intentionally not inside this base manifest yet.
Its threshold will be selected using seeds 30--39 only by enumerating every
behaviorally distinct threshold induced by observed per-layer request counts. The
chosen rule and threshold will then be frozen before one evaluation on seeds 0--29.
Evaluation outcomes may not change that choice.
