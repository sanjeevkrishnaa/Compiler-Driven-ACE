# Execution progress — 2026-10-26

The accepted raw outputs are under
[`raw/base-evaluation`](../../../results/golden_study_2026-10-25/raw/base-evaluation).
The incremental machine-readable aggregation is
[`base-evaluation-progress.csv`](../../../results/golden_study_2026-10-25/summaries/base-evaluation-progress.csv),
and the denominator/progress counters are in
[`base-evaluation-progress.json`](../../../results/golden_study_2026-10-25/validation/base-evaluation-progress.json).

## First accepted slice: zero-cache invariant

GHZ, T-HQA, mesh XY, total communication memories `M=2`, compiler/cache allocation
`C=0`, and evaluation seeds 0--29 are complete. ODG, CGP, ACGP, Dynamic full-chain,
and Dynamic first-hop agree exactly for every seed on request mean and p95 latency,
makespan, admission wait, fidelity, retries, and generated/used/unused pair counts.

| Policy | Seeds | Request latency, mean ± SD | Per-seed p95, mean ± SD | Makespan, mean ± SD |
| --- | ---: | ---: | ---: | ---: |
| ODG | 30 | 1.36684 ± 0.15897 ms | 2.93341 ± 0.61272 ms | 202.80409 ± 3.81518 ms |
| CGP | 30 | 1.36684 ± 0.15897 ms | 2.93341 ± 0.61272 ms | 202.80409 ± 3.81518 ms |
| ACGP | 30 | 1.36684 ± 0.15897 ms | 2.93341 ± 0.61272 ms | 202.80409 ± 3.81518 ms |
| Dynamic full-chain | 30 | 1.36684 ± 0.15897 ms | 2.93341 ± 0.61272 ms | 202.80409 ± 3.81518 ms |
| Dynamic first-hop | 30 | 1.36684 ± 0.15897 ms | 2.93341 ± 0.61272 ms | 202.80409 ± 3.81518 ms |

This is a boundary correctness result, not a performance ranking: at zero cache
capacity every pre-generation policy must fall back to on-demand behavior.

## Launcher incident retained

The first attempt exposed a reproducibility bug: resolving the explicit virtualenv
interpreter path dereferenced it to system Python, losing the installed SeQUeNCe
package. The failure evidence is retained under
[`validation/launcher_failures`](../../../results/golden_study_2026-10-25/validation/launcher_failures).
The launcher now preserves virtualenv identity, and the same job completed and was
subsequently accepted through the resume-validation path.
