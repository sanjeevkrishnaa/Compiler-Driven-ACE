# Compiler-Driven Quantum Communication BTP — Session Handoff

## 1. Research objective

The project asks whether a compiler that knows the future inter-core quantum
communication trace can schedule physical EPR-pair generation more effectively
than reactive or speculative approaches. The workload is a supplied 4x4 QFT
communication trace. The study uses two distinct physical backends:

1. **ACE** (`Compiler-Driven-ACE`): an adaptive continuous entanglement model.
2. **Native SeQUeNCe** (`SeQUeNCe`): the native protocol stack, including
   Barrett-Kok generation/retries, memory decoherence, teleportation, swapping,
   and receiver correction.

Never rank ACE and native SeQUeNCe by their raw millisecond values: their
latency end-points and physical/control implementations differ. Compare policy
directions and trade-offs *within* each backend.

## 2. Canonical local repositories and remotes

| Repository | Local path | Branch | Canonical remote |
|---|---|---|---|
| ACE | `/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE` | `codex/strict-compiler-4plus0` | `https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE.git` |
| Native SeQUeNCe | `/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/SeQUeNCe` | `codex/native-compiler-4x4-physical` | `https://github.com/sanjeevkrishnaa/SeQUeNCe.git` |

Do all work under the `Sem 7/BTP` paths, not the `Documents/ChatGPT` mirror.
The agent machine cannot authenticate GitHub pushes; the user has successfully
pushed manually. Commit clean, scoped changes and ask the user to run the
appropriate `git push origin <branch>` command.

## 3. Locked workload and common experiment rules

| Item | Value |
|---|---|
| Trace | `qft_requests.txt` supplied by user |
| Trace SHA-256 | `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1` |
| Topology | 4x4 mesh, 16 cores, 96 logical qubits |
| Workload size | 766 logical layers; 4,954 transfers; 2,831 conflict-free serialized sublayers |
| Replications | paired seeds 0–29 |
| Static profiles | 3+1, 2+2, 1+1 compiler/demand partition |
| Shared-pool baseline | four physical EPR memories/core; compiler occupancy cap 3; demand may use any free slot |
| Shared-pool demand rule | use exact ready compiler pair first; otherwise atomically obtain all endpoint slots or wait; never hold a partial endpoint allocation |

Every publishable run needs: immutable contract, raw `runs.json`, `summary.csv`,
trace SHA check, 30 seeds, completion check, and request/pair identity audit.
Seed-zero runs are smoke tests only.

## 4. Policies and terminology

* **ODG / matched ODG:** no compiler pre-generation; demand generates at request
  time. Matched ODG uses the same memory profile as compiler policies.
* **Fixed:** prepare a request-specific pair exactly \(\Delta\) trace layers
  before its request.
* **Dynamic:** chooses compiler work with future-trace awareness and available
  scheduling opportunity; it is not a generic speculative cache.
* **CGP / ACGP:** ACE's generic / adaptive speculative generation baselines.
  They lack request identity, can obtain low latency by opportunistic stock, but
  exhibit high expiry/waste in this study.
* **Pre-ready / exact hit:** the intended compiler EPR pair physically exists
  before that request begins demand generation/release.
* **Fallback:** no exact ready pair exists, therefore demand generation is used.
* **Expiry/waste:** a compiler-created pair is not used before it becomes stale
  or remains unused at completion. It is a cost, not merely a failure rate.

## 5. Critical engineering correction

Commit `53b5429` fixed an ACE provenance/lifecycle bug. ACE identifies a pair
by the endpoint memory-slot names, which are reusable. An ordinary later pair
could therefore be misattributed to an earlier compiler record. Also, endpoint
local metadata could disagree. The fix:

* closes a stale compiler record on physical-slot reuse;
* uses the controller's canonical pair-target map at both endpoints; and
* keeps the compiler reservation available for correct release at utilization.

All 28 ACE tests pass (one deliberately skipped). Do **not** combine
pre-correction values with corrected values. Re-run and audit any comparison
that must be final after this fix.

## 6. Validated historical Week 4 results

### ACE corrected static matrix (30 seeds)

| Profile | Fixed latency ms | Dynamic latency ms | Fixed ready | Dynamic ready | Fixed expiry | Dynamic expiry | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| 3+1 | 0.658419 | 0.575869 | 51.87% | 61.59% | 18.29% | 15.74% | dynamic faster and more ready |
| 2+2 | 0.821357 | 0.741142 | 32.97% | 42.13% | 14.41% | 11.77% | dynamic faster and more ready |
| 1+1 | 0.908687 | 0.910578 | 22.85% | 22.57% | 9.17% | 13.27% | no clear dynamic advantage |

### ACE shared pool, cap three (30 seeds)

| Policy | Latency ms | Ready | Delivered fidelity | Compiler fidelity at use | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|---:|
| ODG | 1.104216 | 0% | 0.9498 | — | 0% | 100% |
| Fixed | 0.658471 | 51.92% | 0.8653 | 0.7871 | 18.66% | 48.06% |
| Dynamic | 0.615906 | 56.83% | 0.8972 | 0.8575 | 14.32% | 43.14% |

### ACE adaptive baseline comparison (30 seeds, shared cap three)

| Policy | Latency ms | Delivered fidelity | Expiry |
|---|---:|---:|---:|
| ODG | 1.104216 | 0.9498 | 0% |
| CGP | 0.547729 | 0.8623 | 74.27% |
| ACGP | 0.476298 | 0.8507 | 74.01% |
| Fixed | 0.658471 | 0.8653 | 18.66% |
| Dynamic | 0.615906 | 0.8972 | 14.32% |

Conclusion: ACGP currently has the best **ACE latency**, while compiler dynamic
is the lower-expiry, higher-delivered-fidelity trade-off. Do not frame the work
as forcing a latency win against ACGP; seek a fair Pareto improvement later.

### Native SeQUeNCe shared pool, cap three (30 seeds)

| Policy | Latency ms | Ready | Delivered fidelity | Expiry | Fallback |
|---|---:|---:|---:|---:|---:|
| matched ODG | 0.076451 | 0% | 0.9498 | 0% | 100% |
| Fixed | 0.005092 | 92.23% | 0.7486 | 0% | 4.26% |
| Dynamic | 0.019885 | 68.95% | 0.8838 | 0% | 17.44% |

### Native adaptive baseline (30 seeds; audited but documentation pending)

| Policy | Latency ms | Ready | Delivered fidelity | Background expiry |
|---|---:|---:|---:|---:|
| ODG | 0.076451 | 0% | 0.9498 | 0% |
| CGP | 0.036444 | 53.96% opportunistic | 0.7517 | 59.93% |
| ACGP | 0.033323 | 57.94% opportunistic | 0.7452 | 57.55% |

Native adaptive raw outputs are currently untracked under the native `output/`
directory. Audit passed: 90 trials, 445,860 requests, zero failures.

## 7. Active fixed-lead sensitivity study — highest priority

Question: how does fixed lead \(\Delta\in\{1,2,3,4,5,6\}\) affect latency,
request-specific readiness, fidelity, expiry/waste, fallback, and rejection
pressure under identical physical resources?

Current configuration: ACE shared four-slot pool, compiler cap three, demand
recovery fallback, fixed policy only, same trace, same serialization, 30 seeds.

| Delta | Status | Mean latency ms | Pre-ready | Compiler fidelity at use | Expiry | Audit |
|---:|---|---:|---:|---:|---:|---|
| 1 | pending | — | — | — | — | — |
| 2 | baseline exists but must be re-run after identity correction | — | — | — | — | — |
| 3 | complete | 0.726038 | 44.15% | 0.7732 | 58.68% | passed, 148,620 requests |
| 4 | complete | 0.746164 | 41.91% | 0.7344 | 59.64% | passed, 148,620 requests |
| 5 | pending | — | — | — | — | — |
| 6 | pending | — | — | — | — | — |

Contracts and commits:

* `experiments/qft_4x4_shared_pool_fixed_delta3_v1.json`, commit `87b8d25`.
* `experiments/qft_4x4_shared_pool_fixed_delta4_v1.json`, commit `e45e0df`.
* `ACTIVE_RESEARCH_HANDOFF.md`, commit `ac48108`.

Raw files are ignored by `.gitignore` under `output/`; preserve them locally,
then decide explicitly whether to unignore selected CSV/provenance files or
publish their hash-backed tables in a tracked `results/` report. Never claim
the earlier un-audited delta-four output.

## 8. Parallel next control: cap-four wait-on-demand

This is approved to begin while the remaining fixed-lead runs proceed. It is
**not** strict compiler-only 4+0 and not a static 4+0 partition:

```text
four shared slots/core; compiler cap = 4; no protected demand slot.
If an exact ready pair is absent, demand waits until one slot is free at every
endpoint. Slot allocation is atomic; demand never locks only one endpoint.
```

Implement first in both ACE and native only after agreeing the same semantics.
Run matched ODG, fixed delta 1–6, and dynamic; compare within backend against
shared cap three. Core question: is the protected recovery slot worth its loss
of compiler capacity?

## 9. Explicitly deferred work

Do not start retry-aware/runtime-aware compiler improvements versus ACGP until
the fixed-delta and cap-four controls are audited. Afterwards, candidate work:

1. retry-probability-aware lead selection;
2. runtime occupancy/pending-demand/in-flight-aware launch decisions;
3. utility score = expected latency benefit + fidelity − expiry − demand-block
   risk; and
4. fair shared-capacity, paired-seed, same-trace comparison against ACGP.

## 10. Remaining execution order

1. Finish corrected ACE delta 1, 2, 5, 6; audit each 30-seed artifact.
2. Write an audited ACE delta-sweep report/table/graphs; only then update
   `MASTER_README.md` and Notion.
3. Implement and validate cap-four wait-on-demand, then run its matrix.
4. Repeat fixed delta sweeps for ACE static 3+1, 2+2, 1+1.
5. Repeat fixed delta sweeps in native SeQUeNCe for static profiles and shared
   cap three/cap four. Compare trends, never raw backend latency.
6. Commit/push source contracts, code, tracked summaries and documentation in
   small semantic commits. Preserve ignored raw outputs and record hashes.
7. Consolidate `BTP_REPORT_SOURCE.tex` from audited result tables only.
8. Create the graph-led 10–12 slide PPT after the report. Do not organize the
   presentation by weeks; use one research narrative.

## 11. Documentation locations

| Need | File |
|---|---|
| Week 4 source of truth (user has an uncommitted edit) | `MASTER_README.md` |
| Active work snapshot | `ACTIVE_RESEARCH_HANDOFF.md` |
| Full context for a new agent/session | `SESSION_CONTEXT_HANDOFF.md` |
| Shared pool semantics | `SHARED_POOL_4X4_DESIGN.md` |
| ACE compiler method | `COMPILER_PREGENERATION.md` |
| Adaptive baseline protocol | `ADAPTIVE_BASELINE_SPEC.md` |
| Initial consolidated LaTeX source | `BTP_REPORT_SOURCE.tex` |

## 12. Immediate new-session prompt

> Read `SESSION_CONTEXT_HANDOFF.md` completely before acting. Work only in the
> canonical `Sem 7/BTP` ACE and SeQUeNCe repositories. Preserve the user's
> uncommitted `MASTER_README.md`. First audit/finish the fixed-lead sensitivity
> matrix; in parallel, specify and implement cap-four wait-on-demand with
> atomic endpoint allocation. Do not start ACGP-improvement work. Every final
> numerical result must have an immutable contract, 30 paired seeds, trace
> hash, raw provenance, and an identity audit. Commit changes in small,
> meaningful commits; ask the user to push if authentication is unavailable.
