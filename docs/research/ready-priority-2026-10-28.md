# Ready compiler pairs before ODG — 28 October 2026

## Verified issue

The old event scheduler ordered waiting requests by eligibility time and trace
position, without consulting cached-pair readiness. A non-ready request could
claim an application memory while a ready request sharing its core could fit.
This extends ready-pair storage and keeps its compiler memory occupied.

A concrete XY/seed-6 example occurs in original layer 92 at 440.301289013 ms:
request 235 (qubit 89, core 5 to 1, no ready pair) was admitted while request
228 (qubit 74, core 5 to 4, ready pair) was eligible and could fit. FIFO records
350 and 341 such non-ready admission decisions on XY seeds 6 and 7 at C=2.
These count non-ready admissions bypassing ready requests, not necessarily
physical ODG fallbacks: a non-ready compiler attempt can finish later.

## Runtime service order after the correction

At layer activation, release only the first hop of each independent qubit.
Later hops become eligible only after their predecessor completes. On each
admission pass:

1. Inspect the eligible waiting requests. A ready compiler pair must be
   request-specific, present in both endpoint caches, and have valid quantum
   state with fidelity meeting the request threshold. Checking does not consume
   or credit a pair. Fidelity inspection applies the existing elapsed-time noise.
2. Order ready requests first; within each class retain oldest eligibility and
   trace order. Admit every ready request fitting both endpoints' memory windows.
3. Admit as many non-ready/ODG requests as the remaining endpoint memories allow.
   Multiple ODG requests may use one core concurrently. They need not wait for
   the admitted ready requests to complete if capacity remains.
4. A blocked ready request protects the free endpoint memory it needs; unrelated
   ODG remains admissible. The existing starvation guard continues within the
   non-ready class. Work already admitted is not preempted.
5. Reconsider admission after a booking release, a dependent hop becoming eligible,
   or a compiler pair becoming ready. Pair notifications wake admission 1 ps
   later, and readiness is rechecked at both endpoints. This avoids dependence
   on the order of same-instant endpoint callbacks.

There is no new batch barrier. The existing whole-layer barrier remains. The
priority does not allow a cached later hop to run before its data qubit arrives.
The existing centralized controller assumption permits immediate cache/table
inspection; physical reservation and consumption/control delays remain included.
This change targets compiler-directed caches; experimental pair borrowing is off
in the verified comparisons.

## Matched full-trace verification

Both policies use the same trace, M=4, minimum lead=2, all-hop preparation,
hardware, event admission, and physics seeds. XY uses seeds 6 through 9; YX uses
6 and 7. Means below are across run means.

| Route | Compiler cap | FIFO mean latency ms | Ready-first mean latency ms |
| --- | ---: | ---: | ---: |
| XY | 2 | 1.013505 | **0.984647** |
| XY | 3 | 1.180886 | **0.960416** |
| YX | 2 | 1.008196 | **0.968115** |
| YX | 3 | 1.102092 | **0.959351** |

Ready-first produces **zero fitting-ready bypass decisions in every verified
run**. All 28 complete policy/seed runs (108,528 transfer observations) complete
100% with zero memory-ownership, credit/completion, hop-order or layer-barrier
violations. FIFO XY averages 345.25 bypass decisions/run at C=2 and 444.25 at C=3.

The correction helps C=3 particularly strongly. Earlier statements that C=2
beat C=3 describe the FIFO scheduler; admission order is a substantial part of
that result. C=3 still has less application headroom, but clearing its ready
pairs promptly changes the latency tradeoff. The C=2 reproduction preset keeps
its explicit allocation; this patch changes priority, not memory hardware.

On XY, C=2 average admission wait falls from 0.143875 to 0.111960 ms; C=3 falls
from 0.469176 to 0.246932 ms. C=3 makespan improves from 3.650566 to 3.576115 s.
C=2 makespan is nearly unchanged (3.674120 versus 3.675670 s), so the mean-latency
improvement is not a claim of improvement in every system metric. Delivered
fidelity slightly improves under priority: C=2 0.940605 to 0.940704; C=3 0.937043
to 0.937614. C=3 retains lower fidelity than C=2 due to additional stored pairs.

## Changes and reproduction

- `request_scheduler.py`: default `ready-first` event admission, per-pass readiness
  snapshot, capacity-aware ready-then-ODG admission, and decision logging.
- `adaptive_continuous.py`: non-consuming bilateral request-specific readiness query.
- `compiler_scheduler.py`: pair-ready notification and query bridge.
- `run_trace_comparison.py`: `--admission-priority fifo|ready-first`; audit output
  records which fitting ready requests were bypassed and rejects such bypasses
  under ready-first. Quiet logging streams to the null sink rather than keeping
  all diagnostics in memory.
- `tools/run_full_chain_latency.py`: explicitly selects ready-first. The research
  comparison tool explicitly defaults old variants to FIFO and overrides it for
  the new ready variants, preserving historical reproduction.

Polling submits requests immediately without a shared admission queue; it keeps
FIFO behavior. Ready-first is implemented for the current per-qubit/event path.
The legacy batch scheduler is unchanged.

All **152 compiler tests pass**, including regressions for the original FIFO
bypass, ready-first correction, concurrent same-core ODG, independent ODG during
blocked ready service, readiness wakeup, and bilateral/fidelity/non-consuming
readiness checks. Two parallel verification attempts failed (Python MemoryError
and a native process exit). Their partial outputs are excluded; affected C=3
cases were rerun serially and passed. Only directories with complete summaries,
metadata, admission logs and clean audits contribute to the tables.

Evidence: [all seed observations](data/ready-priority-2026-10-28/all_seeds.csv),
[aggregate metrics and bypass counts](data/ready-priority-2026-10-28/aggregate.csv).
The physical dependency and timing assumptions are unchanged from the
[full-chain study](full-chain-optimization-2026-10-27.md).
