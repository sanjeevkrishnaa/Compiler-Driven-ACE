# Active Research Handoff — Fixed-Lead and Cap-Four Studies

## Purpose

This is the operational handoff for the next controlled experiments. It does
not replace `MASTER_README.md`; it records only active, reproducible work and
the order in which conclusions may be made.

## Locked experimental conditions

| Item | Value |
|---|---|
| Workload | supplied 4x4 QFT trace, 4,954 requests, 2,831 serialized sublayers |
| Trace SHA-256 | `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1` |
| Backend | ACE physical simulation for the current sweep |
| Pool | four physical entanglement-memory slots per core; shared allocation |
| Compiler limit | at most three compiler-reserved slots per core |
| Demand semantics | exact ready compiler pair first; otherwise demand may atomically acquire free endpoint slots; no partial lock |
| Replications | 30 paired seeds, 0 through 29 |
| Policy under sweep | fixed compiler lead only |

## Critical correction already applied

Commit [`53b5429`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/53b5429)
prevents an ordinary pair in reused physical memory slots from being attributed
to an earlier compiler pair, and makes the controller's canonical pair target
authoritative across both endpoint-local views. All 28 ACE tests pass (one is
intentionally skipped). Results produced before this correction must not be
combined with corrected results without rerunning and auditing them.

## Fixed-lead sensitivity study

The independent variable is the fixed lead, \(\Delta\), in trace layers: a
preparation for a request in layer \(L\) is attempted at \(L-\Delta\).

| Delta | Contract | Status | Mean latency (ms) | Ready | Expiry | Audit |
|---:|---|---|---:|---:|---:|---|
| 1 | to be committed | pending | — | — | — | — |
| 2 | historical baseline; rerun required after correction | pending rerun | — | — | — | — |
| 3 | `experiments/qft_4x4_shared_pool_fixed_delta3_v1.json` | complete | 0.726038 | 44.15% | 58.68% | passed: 148,620 requests |
| 4 | `experiments/qft_4x4_shared_pool_fixed_delta4_v1.json` | complete | 0.746164 | 41.91% | 59.64% | passed: 148,620 requests |
| 5 | to be committed | pending | — | — | — | — |
| 6 | to be committed | pending | — | — | — | — |

For every completed delta, preserve `summary.csv`, `runs.json`, the audit JSON,
and the command/contract SHA. The final report must also show paired effects
against the corrected \(\Delta=2\) baseline, fidelity at compiler-pair use,
delivered fidelity, fallback, generation attempts, rejections, completion, and
expiry/waste. Seed-zero smoke runs are never final evidence.

Raw corrected artifacts currently live under:

```
output/fixed_delta_sensitivity_30seed/delta-3-corrected/
output/fixed_delta_sensitivity_30seed/delta-4-corrected/
```

## Next controlled experiment: cap-four wait-on-demand

Do **not** begin the ACGP-improvement work yet. In parallel with the remaining
fixed-delta runs, implement and test this distinct policy:

```text
four shared slots per core
compiler occupancy cap = 4
demand has no protected slot
on an exact-pair miss: demand waits until it can atomically obtain a free slot
at every endpoint; it never holds one endpoint while waiting
```

This is neither static 4+0 nor strict compiler-only 4+0. Demand generation is
permitted after waiting. Compare matched ODG, fixed \(\Delta=1\ldots6\), and
dynamic against the cap-three shared pool using the same trace, physical
parameters, seeds, and audit rules. The question is whether preserving one
demand-recovery slot is worth the lost compiler capacity.

## Deferred work

1. Static 3+1, 2+2, and 1+1 fixed-delta sweeps.
2. Native SeQUeNCe fixed-delta sweeps for static profiles and shared cap three.
3. Retry-aware / runtime-aware compiler scheduling versus ACGP. This remains
   deferred until the cap-four control is audited.
4. Consolidated LaTeX report and graph-led presentation, created only from
   final audited tables and figures.

## Repository and Git handoff

Branch: `codex/strict-compiler-4plus0` in the canonical ACE repository.

Recent commits:

* `53b5429` — preserve compiler-pair identity across endpoints.
* `e45e0df` — immutable audited delta-four contract.
* `87b8d25` — immutable audited delta-three contract.

The current machine cannot authenticate a Git push. Push manually with:

```bash
cd '/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE'
git push origin codex/strict-compiler-4plus0
```

Keep the user's uncommitted `MASTER_README.md` edit separate until the complete
sensitivity matrix is audited and ready to integrate.
