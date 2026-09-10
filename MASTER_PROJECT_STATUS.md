# Compiler-Driven ACE / SeQUeNCe: master project status and handoff

## Read this first

This is the consolidated status document for the BTP project: compiler-driven
EPR pre-generation for inter-core quantum communication. It combines the
original ACE handoff with the work completed afterward, including the controlled
physical ACE/native-SeQUeNCe comparison.

The current source of truth is the completed shared-pool 30-seed experiment,
its audit artifacts and its generated report:

- [`experiments/qft_4x4_shared_pool_v1.json`](experiments/qft_4x4_shared_pool_v1.json)
- [`results/SHARED_POOL_FINAL_COMPARISON_30SEED.md`](results/SHARED_POOL_FINAL_COMPARISON_30SEED.md)
- [`MASTER_README.md`](MASTER_README.md)

Older single-seed, ten-seed and calibrated-dynamic results remain useful
development history. They are not replacements for either audited 30-seed
matrix because their memory allocation and/or schedule timing differ. See
[`COMPILER_PREGENERATION.md`](COMPILER_PREGENERATION.md) and
[`results/ACE_VS_NATIVE_SEQUENCE.md`](results/ACE_VS_NATIVE_SEQUENCE.md) as
historical context only.

The shared-pool design is documented in
[`SHARED_POOL_4X4_DESIGN.md`](SHARED_POOL_4X4_DESIGN.md) and is reported
separately from the earlier static-bank matrix.

The required physical ACE CGP/ACGP comparison is specified in
[`ADAPTIVE_BASELINE_SPEC.md`](ADAPTIVE_BASELINE_SPEC.md) and is now complete;
existing PIR/random-traffic scripts remain explicitly outside this baseline.

## 1. Research question

When a quantum compiler knows that a logical qubit will move from one core to
an adjacent core in the future, can the network prepare the required EPR pair
early enough to reduce communication latency? The answer must account for
finite entanglement memories, physical generation failures, contention,
decoherence, pair expiry, and an on-demand fallback when preparation is not
ready.

The project compares three policies:

| Policy | Decision |
|---|---|
| ODG | Generate only when the communication request arrives. |
| Fixed | Attempt a request-specific pair exactly a fixed number of logical sublayers before use. |
| Dynamic | Search a bounded lookahead window and choose the latest planner-feasible launch. |

This is not an analytical-only cache model. Both ACE and native SeQUeNCe execute
physical discrete-event simulation paths. The two backends differ in their
protocol mechanics and latency boundaries, so their raw milliseconds are not
treated as an absolute simulator-speed comparison.

## 2. Original handoff: what existed at the start

The original handoff described a physical ACE extension that already:

- parsed and validated the complete compiler trace, including evolving qubit
  placement and adjacent mesh-hop checks;
- converted core identifiers into ACE routers and serialized same-core
  communication conflicts;
- implemented fixed and latest-feasible dynamic offline preparation planners;
- injected directed, one-shot compiler reservations into ACE's RSVP, timecard,
  single-heralded generation, cache adoption, memory-decay, and expiry path;
- protected an EPR pair for the request it was generated to serve;
- fell back to ordinary on-demand generation when a pair was absent;
- recorded request completion/latency, readiness, fidelity at creation and
  use, storage time, expiry, waste, and intended-request utilization; and
- completed preliminary seed-0 and ten-seed studies.

That work fixed an important early lifecycle bug: compiler generation was
changed from continuous regeneration to one-shot request-specific generation.
It also established that compiler knowledge cannot remove finite-memory and
generation-capacity limits.

## 3. Gap identified after the handoff

The earlier ACE and native studies did **not** yet constitute a fair physical
cross-repository comparison. In particular, they used different memory models:
ACE used a shared four-memory pool with a compiler cap, whereas native used a
static 3+1 compiler/on-demand partition. Labels such as “3+1” therefore did
not mean the same physical resource allocation in both repositories.

The work carried forward in this session was to remove that ambiguity and test
the question under one frozen, reproducible experiment definition.

## 4. Work completed in this session

### 4.1 Shared contract and workload equivalence

An identical contract was added to ACE and native SeQUeNCe. It freezes:

- the exact supplied QFT trace: 16 cores, 96 logical qubits, 766 source
  layers, 4,954 transfers, SHA-256
  `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`;
- stable deterministic conflict serialization into 2,831 sublayers, with map
  SHA-256 `6b9520823830c50caaefb57baa737c2a8af834ef9474fe628df35def103a235d`;
- 30 paired seeds (0–29), fixed lead of two sublayers, dynamic lookahead of
  eight sublayers, dynamic minimum lead of one sublayer, ten-sublayer
  coherence horizon, and 100 µs logical sublayer duration;
- four exact memory profiles: full ODG with four demand memories, static 3+1,
  static 2+2, and two-total-memory static 1+1; and
- allowed comparison rules: paired policy effects only within a backend and
  memory profile; cross-backend comparisons describe direction and trade-offs,
  not absolute latency.

### 4.2 ACE implementation

ACE now has real static memory banks. Compiler/adaptive reservations use the
compiler bank and application/on-demand RSVP reservations use the separate
demand bank. The old shared-pool behavior remains available for legacy work.

The ACE runner now supports contract/profile execution, complete provenance,
strict rejection of conflicting CLI overrides, exact serialized scheduling,
full ODG with zero compiler capacity, matched ODG using only the demand bank,
validation-only runs, and explicitly marked limited smoke runs. The matrix
runner rejects non-empty output directories so a result cannot be accidentally
overwritten.

### 4.3 Native SeQUeNCe implementation

Native SeQUeNCe received the same contract loader, profile runner, deterministic
serialization, dynamic minimum-lead parameter, provenance, matrix runner, and
stronger invariant auditor. Its physical model includes generation failures,
retry timing, memory noise/expiry, teleportation, and correction stages.

### 4.4 Verification and documentation

- ACE: 22/22 tests pass against the exact QFT trace.
- Native: 20 relevant contract/compiler tests pass.
- ACE audit: 1,486,200 completed request instances and 407,712 compiler-pair
  records passed accounting, uniqueness, target, expiry, and fidelity checks.
- Native audit: 1,486,200 completed request instances and zero failures;
  compressed per-request traces passed pair accounting, memory-bound, timing,
  uniqueness, and fidelity checks.
- ACE includes a matrix summarizer, machine-readable aggregate/paired CSVs,
  the detailed technical report, and this master status document.

## 5. Current controlled result

> **Status update (September 2026):** the ACE compiler-pair utilization path
> was found to retain a consumed pair's nominal compiler reservation until its
> long reservation expiry. The lifecycle fix releases that bookkeeping at
> utilization. The corrected 30-seed ACE static-bank rerun is now complete and
> audited; it supersedes the pre-fix ACE values below. Native remains an
> independently audited within-backend baseline.

All results below use the exact shared contract. “Pre-ready” means a
compiler-generated pair was available before the associated transfer; fidelity
is measured when that pair is used.

### ACE

| Profile | Fixed: latency / ready / fidelity | Dynamic: latency / ready / fidelity | Dynamic vs fixed |
|---|---|---|---|
| 3+1 | 0.658419 ms / 51.87% / 0.7682 | 0.575869 ms / 61.59% / 0.8039 | 12.52% faster, 95% CI [11.80, 13.24]% |
| 2+2 | 0.821357 ms / 32.97% / 0.8496 | 0.741142 ms / 42.13% / 0.8738 | 9.75% faster, [9.11, 10.40]% |
| 1+1 | 0.908687 ms / 22.85% / 0.8267 | 0.910578 ms / 22.57% / 0.7861 | 0.21% slower, [−0.49, 0.07]% |

Against the matched on-demand baseline (1.104216 ms), every ACE compiler mode
reduces mean latency. At 3+1 and 2+2, dynamic is reliably better than fixed,
with higher readiness, fresher pairs and lower expiry. At 1+1, the dynamic
mean is slightly worse and its paired interval includes zero: finite capacity
removes its scheduling advantage. See
[`results/CORRECTED_STATIC_ACE_30SEED.md`](results/CORRECTED_STATIC_ACE_30SEED.md)
for the full corrected table and audit scope.

### Native SeQUeNCe

| Profile | Fixed: latency / ready / fidelity | Dynamic: latency / ready / fidelity | Dynamic vs fixed |
|---|---|---|---|
| 3+1 | 0.005028 ms / 92.29% / 0.7393 | 0.018990 ms / 69.66% / 0.8660 | 279.64% slower |
| 2+2 | 0.005028 ms / 92.29% / 0.7393 | 0.018990 ms / 69.66% / 0.8660 | 279.64% slower |
| 1+1 | 0.037042 ms / 51.46% / 0.6671 | 0.018990 ms / 69.66% / 0.8660 | 48.75% faster |

Native fixed has more time for physical generation retries at 3+1 and 2+2,
so it produces more ready pairs but uses older, lower-fidelity pairs. Dynamic
uses fresher pairs but has fewer retry opportunities. Under 1+1, dynamic can
spread work across its window and wins; fixed's rigid lead causes much more
contention. The 3+1 and 2+2 native cells are identical because the serialized
workload never makes a third compiler memory useful in this configuration.

## 6. What is complete, and what is not

| Item | Status | Evidence / action |
|---|---|---|
| ACE physical compiler integration | Complete | Committed and pushed on `codex/ace-physical-time-scheduler`. |
| Fair static-bank ACE matrix | Complete | Four profiles × policies × 30 seeds; audited. |
| Native physical comparison matrix | Complete | Same contract, profiles and seeds; audited. No rerun is currently justified. |
| Cross-repository statistical report | Complete | `results/shared_contract_30seed/`. |
| Native shared-pool compiler implementation | Complete locally | Native source is committed as `0aad0d9f`; the ignored raw full-matrix output passed its independent audit. |
| Physical trace-driven ACE CGP/ACGP baseline | Complete and audited | `run_trace_adaptive_baseline.py` replayed the QFT trace with the same serialization and shared four-memory policy for 30 seeds. The audit covered 445,860 completed requests and 21,226 adaptive-pair records. |
| Reservation-aware ACE dynamic policy | Pending research improvement | The current 1+1 result identifies the target; do not tune it into this baseline. |
| Sensitivity analysis | Pending research extension | Vary lookahead, minimum lead, coherence, generation parameters, and workload/topology in a new contract. |

## 7. Decision on rerunning native SeQUeNCe

No full rerun is needed now. The native matrix already has all expected cells,
complete seed sets, the same trace and contract hashes as ACE, and successful
invariant audits. A rerun would be necessary only if the native source changes,
the contract changes, an audit fails, or the raw output is lost before the
native commit/provenance has been preserved.

The native implementation is committed locally. The raw output remains ignored
due to size; reproducibility comes from the committed contract and code, the
command, provenance embedded in `study.json`, and the audit procedure.

## 8. Recommended next sequence of work

1. Preserve the current shared 30-seed results as baselines; do not overwrite
   its output directory.
2. Define a new versioned contract for an ACE reservation-aware dynamic policy.
   It should use physical acceptance/admission information, not only offline
   layer capacity, and test whether it resolves the ACE 1+1 regression.
3. If CGP/ACGP is part of the next static-bank thesis comparison, define their
   static-bank allocation and rerun under a new, versioned contract. The
   completed CGP/ACGP evidence here applies to the shared pool only.
4. Perform a pre-registered sensitivity study over the parameters above and at
   least one additional workload/topology before making a general claim beyond
   this QFT 4×4 trace.
5. Turn the locked baseline and follow-up experiments into thesis/paper figures:
   paired latency effect with confidence intervals, readiness-versus-fidelity
   scatter, and memory-profile comparison. Clearly label ACE/native values as
   within-backend results.
