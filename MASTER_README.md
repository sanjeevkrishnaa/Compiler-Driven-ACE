# Compiler-Driven EPR Pre-Generation for Quantum Multi-Core Communication

> **Project status:** active research implementation. This document is the
> single narrative for the BTP work from the original ACE handoff through the
> current corrected physical-simulation work. It distinguishes audited results
> from superseded historical development results and pending experiments.

## Repositories and code history

| Repository | Purpose | Link |
|---|---|---|
| Compiler-Driven ACE | ACE/SeQUeNCe 0.8.1 physical compiler scheduler, contracts, audits, documentation | [GitHub](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE) |
| Native SeQUeNCe | Independent physical backend with Barrett--Kok generation, swapping and teleportation | [GitHub](https://github.com/sanjeevkrishnaa/SeQUeNCe) |

Important ACE commits:

| Commit | Contribution |
|---|---|
| [`a7b8bed`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/a7b8bed) | Initial compiler-directed pre-generation implementation |
| [`bab1a14`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/bab1a14) | Physical static-bank scheduler |
| [`1f540e2`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/1f540e2) | Audited 4x4 compiler-scheduler study |
| [`51faf67`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/51faf67) | Consolidated project status and next steps |

Important native SeQUeNCe commits:

| Commit | Contribution |
|---|---|
| [`d3cc4b7`](https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/d3cc4b7) | Early compiler-driven/native entanglement studies |
| [`94f3b49`](https://github.com/sanjeevkrishnaa/SeQUeNCe/commit/94f3b49) | Native physical compiler pre-generation integration |

The current ACE development branch is
[`codex/strict-compiler-4plus0`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/tree/codex/strict-compiler-4plus0).
It is deliberately separate from the earlier audited branch because it adds
strict 4+0 and shared-pool work:

| Commit | Contribution |
|---|---|
| [`8ddd940`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/8ddd940) | Strict compiler-only 4+0, shared-pool contract support, lifecycle repair and regression tests |
| [`102635a`](https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/commit/102635a) | Master BTP narrative, shared-pool design and adaptive-baseline specification |

## Research idea

Distributed quantum programs move logical qubits between quantum cores. A
teleportation transfer needs a high-fidelity EPR pair between the two involved
cores. On-demand generation creates that EPR pair only after the transfer is
requested, adding physical generation and control delay.

The compiler already knows many upcoming transfers. The research question is:

> Can compiler knowledge prepare request-specific EPR pairs early enough to
> reduce communication delay, while respecting finite memories, physical
> generation failures, decoherence, expiry, and competing transfers?

The project studies three broad strategies:

| Strategy | Decision rule |
|---|---|
| ODG | Generate the required EPR pair only when the request arrives. |
| Fixed compiler | Generate the request-specific pair a fixed number of logical sublayers before use. |
| Dynamic compiler | Search a bounded future window and choose the latest planner-feasible preparation. |
| CGP / ACGP (pending controlled baseline) | Generate speculative pairs without compiler foreknowledge; ACGP adapts neighbour selection from observed traffic. |

## Workload and fairness contract

The controlled workload is the supplied 4x4 QFT communication trace:

| Property | Value |
|---|---:|
| Mesh / cores | 4x4 / 16 |
| Logical qubits | 96 |
| Source layers | 766 |
| Adjacent-core transfers | 4,954 |
| Conflict-free serialized sublayers | 2,831 |
| Trace SHA-256 | `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1` |
| Serialization-map SHA-256 | `6b9520823830c50caaefb57baa737c2a8af834ef9474fe628df35def103a235d` |
| Replications | 30 paired seeds, 0–29 |

The source layer may contain many transfers. Transfers sharing an endpoint core
cannot use that core's communication memory simultaneously, so the trace is
deterministically split into conflict-free sublayers. A later sublayer is
released only after the preceding sublayer terminates.

The original static-bank contract is
[`experiments/qft_4x4_comparison_v1.json`](experiments/qft_4x4_comparison_v1.json).
It has an identical native counterpart. The newer shared-pool contract is
[`experiments/qft_4x4_shared_pool_v1.json`](experiments/qft_4x4_shared_pool_v1.json).

## Architecture

```text
QFT compiler trace
      │ parse, validate topology, serialize conflicts
      ▼
Offline fixed/dynamic preparation planner
      │ request ID + preparation layer
      ▼
Physical backend (ACE or native SeQUeNCe)
      │ physical generation failures, memory occupancy, noise, expiry
      ▼
request-specific EPR ready? ── yes → consume for transfer
      │ no
      ▼
on-demand fallback or strict miss, depending on experiment contract
      ▼
per-request latency, readiness, fidelity-at-use, expiry and accounting audit
```

### ACE implementation

The ACE path extends the existing adaptive-continuous SeQUeNCe implementation.
Key code:

- [`compiler_trace.py`](compiler_trace.py): trace parsing, mesh validation and
  fixed/latest-feasible dynamic planning.
- [`compiler_scheduler.py`](compiler_scheduler.py): compiler-to-physical
  reservation bridge, request-specific EPR records and utilization metrics.
- [`adaptive_continuous.py`](adaptive_continuous.py): one-shot compiler
  reservations, exact-pair ownership and physical pair lifecycle hooks.
- [`reservation.py`](reservation.py): static compiler/demand timecard banks
  and reservation release.
- [`parallel_core.py`](parallel_core.py): deterministic layered replay,
  endpoint conflict serialization, retry layers and request metrics.
- [`run_compiler_pregeneration.py`](run_compiler_pregeneration.py):
  contract-controlled physical runner.

### Native SeQUeNCe implementation

The native backend is a distinct physical event-driven model. It includes
Barrett--Kok attempts/failures, memory decoherence/expiry, swapping,
teleportation and receiver correction. Its compiler implementation resides in
the SeQUeNCe repository under:

- `sequence/entanglement_management/generation/sequence_model.py`
- `sequence/entanglement_management/generation/compiler_sequence.py`
- `example/multicore_entanglement/run_native_compiler_trace.py`

Do **not** compare ACE and native absolute milliseconds: their physical
protocol paths and latency endpoints differ. Compare policy direction and
trade-offs within each backend under an identical workload/memory contract.

## Memory models

### Historical static partitions

Each core has four physical communication memories (except the two-total-slot
1+1 profile):

```text
3+1: [ compiler ][ compiler ][ compiler ][ demand ]
2+2: [ compiler ][ compiler ][ demand ][ demand ]
1+1: [ compiler ][ demand ]
```

If the exact compiler pair is absent, on-demand generation can use only its
demand bank. If either endpoint has no eligible free slot, the request waits
and is retried. The completed earlier static study observed no terminal
failures, but not every request was compiler-ready.

### Strict compiler-only 4+0

```text
4+0: [ compiler ][ compiler ][ compiler ][ compiler ]
```

There is no on-demand fallback. At release, an absent exact pair is counted as
a terminal compiler miss. This measures **compiler coverage**, not realistic
end-to-end execution latency.

ACE seed-0 full-trace coverage result:

| Policy | Completed / 4,954 | Strict misses | Coverage |
|---|---:|---:|---:|
| Fixed | 2,793 | 2,161 | 56.38% |
| Dynamic | 3,602 | 1,352 | 72.71% |

This proves that compiler pre-generation alone cannot serve the entire trace;
physical failures, limited capacity and scheduling deadlines still require a
fallback policy for complete execution.

### Shared four-memory pool with compiler cap

The current realistic design has four shared physical slots per core with a
compiler occupancy cap of three:

```text
shared pool: [ slot ][ slot ][ slot ][ slot ]
             compiler may occupy at most three;
             demand may use any free slot.
```

At release, the exact ready compiler pair has priority. Otherwise, on-demand
generation atomically obtains a free slot at both endpoints. If that cannot
happen, the request obtains neither partial allocation and waits. Pending
demand work is admitted before new speculative compiler preparation at the
same simulator instant. See
[`SHARED_POOL_4X4_DESIGN.md`](SHARED_POOL_4X4_DESIGN.md).

## Results and evidence

### Earlier audited static-bank study — historical, not final ACE evidence

The earlier 30-seed study audited 1,486,200 request instances per backend.
Native SeQUeNCe completed every request and passed its pair/memory/timing/
fidelity audit. Its within-backend trends are useful historical evidence.

The earlier ACE table has now been replaced by the corrected rerun. The
complete audited table and confidence intervals are in
[`results/CORRECTED_STATIC_ACE_30SEED.md`](results/CORRECTED_STATIC_ACE_30SEED.md).
Its central results are:

| Static profile | Fixed latency / ready / fidelity | Dynamic latency / ready / fidelity |
|---|---|---|
| 3+1 | 0.805875 ms / 34.65% / 0.7834 | 0.802312 ms / 35.39% / 0.8212 |
| 2+2 | 0.983236 ms / 14.06% / 0.8567 | 0.978956 ms / 14.43% / 0.8798 |
| 1+1 | 1.000413 ms / 12.28% / 0.8551 | 1.009635 ms / 10.97% / 0.8039 |

**Important correction:** ACE previously retained a consumed compiler pair's
long reservation timecard until nominal expiry. The corrected matrix above was
run after immediate release at utilization was implemented and audited. It is
therefore the valid ACE static-bank evidence. It still must not be interpreted
as a raw-millisecond comparison with native SeQUeNCe.

See [`MASTER_PROJECT_STATUS.md`](MASTER_PROJECT_STATUS.md) and
[`results/shared_contract_30seed/RESULTS.md`](results/shared_contract_30seed/RESULTS.md)
for the preserved historical artifacts.

### Interpretation of the 3+1, 2+2 and 1+1 comparison

The memory labels describe a **per-core static partition**, not a network-wide
pool: 3+1 means three compiler-preparation memories plus one on-demand memory
at every participating core; 2+2 means two and two; and 1+1 means two total
communication memories, one in each role.  In every case, a transfer that has
no usable prepared pair must go through the finite on-demand bank and can be
delayed or retried when its endpoint slots are occupied. Thus the profiles are
not merely parameter sweeps: they expose the trade-off between preparing more
pairs early and retaining capacity to recover from a compiler miss or physical
generation failure.

The corrected ACE data show a stronger capacity-dependent result. Dynamic is
12.52% faster than fixed at 3+1 and 9.75% faster at 2+2 on paired mean
latency; both confidence intervals exclude zero. It is 0.21% slower at 1+1,
but that interval includes zero, so no fixed/dynamic winner is established at
the tightest capacity. The useful lesson is not that dynamic universally wins:
under tight memory it can contend with demand work and lose its advantage.
These corrected static-bank results are valid ACE evidence; the pre-fix values
remain historical only.

The audited native SeQUeNCe study provides a clean within-backend contrast.
For its 3+1 and 2+2 static profiles, fixed achieved 0.005028 ms average
request latency, 92.29% prepared-pair readiness and 0.7393 delivered
fidelity; dynamic achieved 0.018990 ms, 69.66% readiness and 0.8660 fidelity.
Here fixed is faster because its earlier launches allow more time for the
physical generation/retry process before each request, whereas dynamic tends
to use fresher, higher-fidelity pairs but has less recovery time. At 1+1,
fixed fell to 51.46% readiness and 0.037042 ms, while dynamic reached 69.66%
and 0.018990 ms; with only one demand memory, avoiding the fixed schedule's
contention becomes more valuable. The identical native 3+1 and 2+2 values are
also informative: for this serialized trace, the third compiler slot was not
the limiting resource in that implementation.

The cross-repository conclusion is therefore methodological rather than a
raw-speed ranking. Both physical implementations demonstrate that the memory
split changes readiness, retry opportunity, latency and fidelity together,
and that fixed versus dynamic is workload- and capacity-dependent. ACE and
native milliseconds must not be compared directly because their generation,
reservation, timing and accounting implementations differ. The valid final
comparison will be made within each backend, under the corrected lifecycle and
one hash-verified memory contract, across ODG, CGP, ACGP, fixed and dynamic.
The corrected ACE 30-seed static rerun and the shared-pool matrices are still
required before claiming an ACE-versus-native performance conclusion.

### Corrected implementation checks

| Check | Outcome |
|---|---|
| Strict 4+0 ACE seed 0 | Fixed 56.38% coverage; dynamic 72.71% coverage |
| Native strict 4+0 first 50 transfers | 47 completed, 3 strict misses |
| Corrected ACE shared-pool 12-transfer prefix | 12/12 completed; 100% ready; 3 genuine retry layers |
| Native shared-pool 12-transfer prefix | 12/12 completed; 11 ready transfers and 1 not-ready transfer with fallback enabled |
| ACE focused tests after lifecycle fix | 11 passed, 1 skipped |
| Native focused tests for shared-pool work | 13 passed, 1 skipped |

These are validation/smoke checks, **not** publication matrices.

## Problems encountered and fixes

### ACE compiler-reservation lifecycle defect (discovered during shared-pool validation)

**What happened.** A compiler-directed EPR pair was generated, held for its
target transfer, and correctly consumed by the application. However, its
compiler reservation timecards and compiler-memory quota remained active until
the reservation's nominal 1,000 ms expiry. The EPR pair was already gone, but
the scheduler continued to treat its compiler capacity as occupied.

```text
Before the fix:
compiler EPR generated → compiler slot reserved → EPR consumed
                                             └→ reservation stayed for 1,000 ms
                                                and blocked later compiler work
```

**Why it matters.** This was not real quantum-memory contention. It could
reject later preparations, reduce readiness, add retry layers and inflate
latency. It therefore risked measuring stale scheduler bookkeeping rather than
finite memory, generation failure, endpoint contention or decoherence. Since
native SeQUeNCe does not use ACE timecards, it also made any final ACE/native
interpretation unsafe.

**How it was found.** The new shared-pool full-trace smoke accumulated an
unexpectedly large number of retry layers. Reviewing the compiler-pair
lifecycle showed that strict 4+0 released its reservation at direct use, while
the ordinary fallback-enabled application utilization path did not.

**Fix.** At compiler-pair utilization, ACE now releases the compiler
reservation/timecard and compiler occupancy quota at both endpoint routers.
The application retains its physical EPR memory through its normal consumption
path; only stale compiler bookkeeping is removed.

```text
After the fix:
compiler EPR generated → compiler slot reserved → EPR consumed
                                             └→ compiler reservation and quota
                                                released immediately
```

**Evidence.** The corrected 12-transfer shared-pool ACE prefix completed
12/12 transfers, improved compiler readiness from 50% before the correction
to 100% afterward, and retained only three genuine finite-capacity retry
layers. A regression test verifies one release at both endpoints on every
compiler-pair utilization. The full corrected 30-seed static-bank rerun has
now passed its audit; its results supersede the old ACE static-bank table.

| Problem | Root cause | Resolution |
|---|---|---|
| Earlier analytical results were not physical results | No physical generation failure/noise lifecycle | Implemented physical ACE and native execution paths |
| ACE/native resources were initially not equivalent | ACE shared pool vs native static 3+1 | Added versioned, hash-verified static and shared-pool contracts |
| Same-layer requests contended at a core | A core cannot use multiple communication memories arbitrarily for overlapping transfers | Deterministic conflict serialization into 2,831 sublayers |
| Dynamic can be worse than fixed in native | Later launches leave less retry time after physical failure | Record readiness/fidelity/attempt trade-off rather than assume dynamic wins |
| Strict 4+0 cannot complete trace | No capacity for fallback when exact pair is absent | Treat as coverage experiment only |
| Potential partial endpoint lock | One EPR needs memory at both endpoints | Atomic endpoint admission; queue without holding a partial slot |
| ACE artificial reservation lock | Consumed compiler pairs retained long compiler timecards | Release compiler timecard and quota at utilization; regression tested |

## Current work and next steps

### In progress

The corrected ACE 30-seed static-bank matrix has completed and passed its
artifact audit. Its local source artifacts are in
`output/qft_static_corrected_30seed/`; its tracked interpretation is
[`results/CORRECTED_STATIC_ACE_30SEED.md`](results/CORRECTED_STATIC_ACE_30SEED.md).

The shared-pool compiler matrix has also completed and passed audit. Dynamic
reduces paired mean latency by 44.22% versus ODG and 6.45% versus fixed under
the four-memory, cap-three policy. See
[`results/SHARED_POOL_COMPILER_30SEED.md`](results/SHARED_POOL_COMPILER_30SEED.md).

### Required sequence

1. Run and audit the implemented trace-driven physical ACE ODG/CGP/ACGP baseline.
2. Run and audit native shared-pool cap-3 matrix.
3. Compare ODG, CGP, ACGP, fixed and dynamic **within each backend**.
4. Publish only audited, complete paired-seed results.

The controlled CGP/ACGP requirements are in
[`ADAPTIVE_BASELINE_SPEC.md`](ADAPTIVE_BASELINE_SPEC.md). Existing random/PIR
CGP/ACGP scripts are not a substitute.

## How to reproduce the corrected ACE static matrix

Run from the ACE repository and use a fresh output directory:

```bash
MPLCONFIGDIR=/private/tmp/ace-mpl .venv/bin/python run_contract_matrix.py \
  --trace '/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/qft_requests.txt' \
  --contract experiments/qft_4x4_comparison_v1.json \
  --output output/qft_static_corrected_30seed
```

The runner executes full ODG, static 3+1, static 2+2 and static 1+1 profiles
over seeds 0–29. Never reuse a non-empty output directory. Once complete, run
the corresponding auditor before creating a table or latency claim.

## Reading order

1. This document.
2. [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md): original ACE handoff and code
   history.
3. [`MASTER_PROJECT_STATUS.md`](MASTER_PROJECT_STATUS.md): detailed current
   status and historical results.
4. [`SHARED_POOL_4X4_DESIGN.md`](SHARED_POOL_4X4_DESIGN.md): current realistic
   memory model.
5. [`ADAPTIVE_BASELINE_SPEC.md`](ADAPTIVE_BASELINE_SPEC.md): controlled CGP /
   ACGP plan.
6. [`COMPILER_DRIVEN_ACE_4X4_REPORT.md`](COMPILER_DRIVEN_ACE_4X4_REPORT.md):
   audited static study details, read with the ACE rerun notice above.
