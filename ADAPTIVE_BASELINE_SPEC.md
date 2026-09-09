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

## Status

Specification only. Implementation waits for the corrected ACE compiler matrix
to finish, because that rerun freezes the corrected lifecycle and baseline
memory policy.
