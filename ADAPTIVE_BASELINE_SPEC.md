# Trace-driven CGP/ACGP baseline: required experiment specification

## Why an additional runner is required

Existing ACE CGP/ACGP scripts, including `run_pir_experiments_event.py`, are
useful protocol demonstrations but are not valid comparison baselines for the
compiler-driven 4x4 QFT study. They generate random/PIR traffic, do not use
the supplied QFT request trace, and do not enforce the trace's deterministic
conflict-layer barriers or 30 paired seeds.

They must not be compared directly with compiler-driven results.

## Baseline to implement after corrected compiler matrices

The physical CGP and ACGP baseline must use all of the following:

| Item | Required rule |
|---|---|
| Workload | Supplied `qft_requests.txt`, SHA-256 locked in the experiment contract |
| Topology | 4x4 mesh, 16 cores, neighbour-only requests |
| Request ordering | Same deterministic 2,831 conflict-free sublayers |
| Progression | Barrier: next sublayer releases only after current one terminates |
| Physical memory | Same selected policy: static bank or shared four-memory pool; never a hidden fifth slot |
| Seeds | 0–29, paired across ODG, CGP, ACGP, fixed, and dynamic |
| CGP | Uniform feasible-neighbour continuous generation |
| ACGP | Existing adaptive probability update, with its update parameters frozen and recorded |
| Demand | On a missing pair, use the same atomic endpoint allocation and pending/retry semantics |
| Measurements | Completion, request latency, pending/retry delay, EPR fidelity at use, expiry, generated/used/wasted pairs |
| Audit | Per-request accounting, trace hash, memory bounds, no duplicate pair consumption, paired-seed completeness |

## Required ACE runtime

This ACE repository targets the SeQUeNCe **0.8.1** reservation API, pinned at
commit `cf5283cdfd6692a82a090d15fb09fbc01bd322fc`. The newer BTP
`SeQUeNCe/` checkout is the separate native-comparison backend and has an
incompatible reservation API; do not install it into ACE's environment.

The compatible checkout is therefore kept separately as
`../SeQUeNCe-0.8.1/`. Create the ACE-local environment from the ACE directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ../SeQUeNCe-0.8.1
```

## Comparison logic

Within a backend and one memory policy, compare:

1. Matched ODG: no speculative generation.
2. CGP: uninformed speculative generation.
3. ACGP: adaptive speculative generation based on previous traffic.
4. Fixed compiler pre-generation.
5. Dynamic compiler pre-generation.

The thesis question is then well-defined: does ahead-of-time compiler
information outperform an online adaptive policy under the same finite memory,
physical generation, and request trace?

## Explicit non-claims

- Do not compare raw ACE and native milliseconds.
- Do not compare old analytical CGP/ACGP results with physical results.
- Do not call an adaptive policy equivalent to shared-pool compiler scheduling
  until both follow the same memory/admission contract.
- Do not publish a latency reduction when any trial is incomplete.

## Implemented trace runner

`run_trace_adaptive_baseline.py` implements the physical ACE replay without
attaching `CompilerPreGenerationController`. It reuses the same
`ParallelLayerRequestManager`, trace parser, conflict serialization, request
duration and barrier progression as the compiler-driven runner.

For the shared-pool comparison, all policies have four physical communication
memories per core. CGP and ACGP have an autonomous speculative-occupancy cap
of three; ODG has cap zero. This is an occupancy cap, not a static bank:
on-demand work remains eligible to use any free one of the four physical
memories through ACE's normal reservation/retry mechanism.

| Policy | Autonomous cap | Neighbour selection |
|---|---:|---|
| ODG | 0 | no autonomous generation |
| CGP | 3 | ACE fixed/uniform probability table |
| ACGP | 3 | ACE usage-updated probability table |

Validate the full, hash-locked QFT workload before running a matrix:

```bash
MPLCONFIGDIR=/private/tmp/ace-mpl .venv/bin/python run_trace_adaptive_baseline.py \
  --trace '/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/qft_requests.txt' \
  --contract experiments/qft_4x4_shared_pool_v1.json --validate-only
```

The runner has completed a non-empty six-transfer physical ODG smoke replay
(6/6 completed) and a six-transfer physical CGP lifecycle smoke replay
(6/6 completed). The latter exported generated, used, expired, remaining,
expiry, waste, fidelity-at-use and storage-time fields. These smoke checks
confirm integration only; they are not performance results. The full 30
paired-seed ODG/CGP/ACGP matrix must use the frozen shared-pool contract.

After a matrix completes, audit both application completion and every adaptive
pair lifecycle record before interpreting a result:

```bash
MPLCONFIGDIR=/private/tmp/ace-mpl .venv/bin/python audit_adaptive_baseline_results.py \
  output/qft_shared_pool_adaptive_30seed/runs.json \
  --expected-trace-sha256 61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1 \
  --output output/qft_shared_pool_adaptive_30seed/audit.json
```

The auditor verifies complete request delivery, trace identity, unique
policy/seed cells, pair-lifecycle conservation, one adaptive pair per
application request, timestamp ordering, fidelity range, and agreement between
the pair trace and all reported lifecycle counters.

## Completed shared-pool ACE baseline matrix

The full physical matrix completed on 2026-09-10 and passed the command above:

- 90 strategy/seed cells (ODG, CGP and ACGP × seeds 0–29);
- 445,860 completed request instances; and
- 21,226 audited adaptive-pair lifecycle records with no audit errors.

The corresponding ACE compiler and native SeQUeNCe shared-pool studies also
completed and passed their independent audits. The consolidated result table,
paired confidence intervals and interpretation are in
[`results/SHARED_POOL_FINAL_COMPARISON_30SEED.md`](results/SHARED_POOL_FINAL_COMPARISON_30SEED.md).

The final report is generated—not hand assembled—by:

```bash
MPLCONFIGDIR=/private/tmp/ace-mpl .venv/bin/python summarize_shared_pool_study.py \
  --ace-adaptive output/qft_shared_pool_adaptive_30seed/runs.json \
  --ace-compiler output/qft_shared_pool_compiler_30seed_v2/shared-pool-4-cap3/runs.json \
  --native-study '../SeQUeNCe/output/qft_shared_pool_native_30seed/shared-pool-4-cap3/study.json' \
  --output results/SHARED_POOL_FINAL_COMPARISON_30SEED.md
```
