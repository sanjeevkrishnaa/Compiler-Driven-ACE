# Four-memory shared-pool experiment design

## Purpose

This is the realistic successor to the prior static `3+1`, `2+2`, and `1+1`
studies. Every core has four physical entanglement-memory slots. They are not
permanently assigned to compiler work or to on-demand work.

The compiler may occupy at most three slots at a core with request-specific
pre-generated EPR pairs. The fourth slot is not a permanently reserved demand
bank: it is simply capacity left by that compiler cap. Any of the four slots
can serve an on-demand request after a compiler miss.

## Admission rule

For every conflict-free trace sublayer, a request follows this order:

1. Consume its exact, ready compiler EPR pair, if present.
2. Otherwise try on-demand generation from the shared pool.
3. On-demand admission requires one unclaimed slot at **every endpoint**.
   The allocation is atomic: if all endpoints cannot be obtained together,
   the request claims none and remains pending.
4. Pending demand requests are admitted before new compiler preparation at the
   same simulator time. Thus speculation cannot obtain newly freed capacity
   ahead of already waiting communication.
5. When a slot is released, pending work is retried. The trace's conflict
   serialization and layer barriers preserve deterministic ordering.

This prevents partial endpoint allocation deadlock. It does not claim that
waiting is impossible: finite memories and physical generation still create
queueing and serialization.

## What it is not

It is not static `3+1`: no slot is demand-only, and demand may borrow any free
slot. It is not strict `4+0`: demand fallback is enabled. Strict `4+0` is a
separate coverage experiment in
[`experiments/qft_4x4_strict_4plus0_v1.json`](experiments/qft_4x4_strict_4plus0_v1.json).
There, a missing compiler pair is a terminal miss by definition.

## Reproducible contract

The authoritative shared-pool contract is
[`experiments/qft_4x4_shared_pool_v1.json`](experiments/qft_4x4_shared_pool_v1.json).
It is byte-identical to native SeQUeNCe's corresponding contract. It fixes the
supplied QFT trace, deterministic 2,831-sublayer serialization, 30 paired
seeds, a three-slot compiler occupancy cap, and a four-slot shared physical
pool per core.

The contract results must be reported separately from existing static-bank
results. Do not compare raw ACE and native milliseconds; compare policy
directions and trade-offs within each physical backend.

## Current validation status

- Contract loading and byte identity: verified in both repositories.
- ACE focused tests: passed.
- Native focused tests: passed.
- ACE shared-pool physical smoke: completed all 12 requests in the first
  populated prefix; retry layers demonstrated finite-capacity queueing.
- Native shared-pool physical smoke: completed all 12 requests, including one
  compiler-not-ready transfer with fallback enabled.
- ACE compiler-pair utilization now releases the consumed pair's compiler
  reservation/timecard and compiler quota. This was necessary to prevent the
  long nominal reservation window from behaving as an artificial shared-pool
  lock.
- Corrected ACE 12-transfer prefix: all transfers completed; all twelve used
  ready compiler pairs; three transfers entered one retry layer because of
  finite resource contention. This is a smoke result only, not a matrix
  result.

The required publishable result remains a complete 30-seed matrix for matched
ODG, fixed, and dynamic in both backends, followed by the existing auditors.
