# QFT-96 timing-model matrix — 2026-10-25 11:41 IST

## Purpose

This experiment isolates two historical choices that otherwise get mixed together:

1. **Release scheduler:** legacy layer/batch serialization versus the corrected
   per-qubit scheduler.  The corrected scheduler preserves hop order for one
   qubit, but releases requests for independent qubits concurrently.
2. **Reservation lead:** the historical fixed 5.3 ms "pre-generation buffer"
   versus corrected physical timing.  Corrected timing uses no arbitrary lead;
   it retains the RSVP round-trip guard derived from the configured classical
   channel delay (about 0.200 ms in this mesh).

The experiment is a QFT-96 communication trace: 16 cores in a 4x4 mesh, 766
layers, 4,954 adjacent-hop requests, four shared communication memories per
core, and a Dynamic compiler cap of three memories per core.  Each cell uses
physics seeds 0 through 29.  Every one of the 240 policy-runs completed every
request.

## Results

Values are mean +/- sample standard deviation over 30 physics seeds.  A
negative Dynamic change means that Dynamic has a shorter makespan.

| Model | Latency metric | ODG | Dynamic | ODG makespan | Dynamic makespan | Dynamic makespan change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Historical legacy scheduler, artificial 5.3 ms lead | Historical local/service metric; subtracts 5.3 ms | 1.110 +/- 0.011 ms | 0.691 +/- 0.008 ms | 32.900 +/- 0.052 s | 30.932 +/- 0.040 s | -5.98% |
| Legacy serialized scheduler, corrected physical timing | Local/service metric; no artificial 5.3 ms | 1.310 +/- 0.011 ms | 0.917 +/- 0.013 ms | 8.950 +/- 0.052 s | 7.106 +/- 0.063 s | -20.60% |
| Correct per-qubit scheduler, artificial 5.3 ms lead retained | Fair arrival-to-completion; includes the 5.3 ms as elapsed time | 7.704 +/- 0.021 ms | 15.660 +/- 0.052 ms | 10.259 +/- 0.028 s | 14.405 +/- 0.032 s | +40.41% |
| Correct per-qubit scheduler, corrected physical timing | Fair arrival-to-completion | 1.526 +/- 0.016 ms | 2.570 +/- 0.096 ms | 4.337 +/- 0.026 s | 4.694 +/- 0.086 s | +8.22% |

The final row is the only cross-policy headline comparison.  With four shared
memories, allowing Dynamic to reserve three for look-ahead preparation reduces
its mean EPR generation/service time but creates more admission waiting than
ODG.  The next research objective is therefore explicit: improve the Dynamic
compiler-driven policy until its fair arrival-to-completion latency is below the
ODG result of 1.526 ms, without degrading completion, fidelity, or makespan.

## Why the historical metric is not comparable

The original legacy manager inserted a fixed 5.3 ms delay before every request
reservation window and reported:

```
completion_time - scheduler_submission_time - 5.3 ms
```

That is a manager-local service-style number, not a client/request latency.  It
hides both the artificial lead and time a request spends before the serialized
manager submits it.  The historical number remains useful solely for
reproducing the mid-term table.

The final request metric is instead:

```
request completion time - request eligibility/arrival time
```

For a first hop, arrival is layer activation.  For a later hop of the same
qubit, arrival is predecessor-hop completion.  It includes RSVP/control delay,
waiting for a shared communication memory, retries, and EPR generation.  It
does not charge a request for compiler EPR storage that occurred before its
arrival.

## Parallel-request reporting rule

Parallelism changes *when requests arrive*, not what latency means.  Independent
qubits released by one active layer have the same layer-activation arrival time;
same-qubit hops remain causally ordered.  The primary metric is the distribution
of per-request arrival-to-delivery latency.  A complete report must additionally
give:

* median and p95/p99 request latency (mean alone can hide queueing tails);
* makespan, from first workload release to last request completion;
* completion rate and throughput; and
* layer completion time when a circuit layer is a real gate barrier.

Makespan or layer completion time must not replace per-request latency: a
pre-generation policy can improve one while harming the other.

## Reproduction

Use the QFT trace
`results/qft96_corrected_scheduler_2026-10-25/qft96_requests.txt`, the 4x4
configuration, total memories 4, compiler memories 3, generation capacity 3,
delta 6, lookahead 8, coherence 10 layers, reservation window 1000 ms, request
duration 50 ms, and seeds `0,1,...,29`.

* The first row must run from archival `origin/codex/ace-scheduler-correctness`
  commit `1cc7eb6` with `--scheduler legacy --pregeneration-buffer-ms 5.3`.
* The second and fourth rows run from this corrected-timing branch with
  `--pregeneration-buffer-ms 0`; use `--scheduler legacy` or
  `--scheduler per-qubit --admission event`, respectively.
* The third row uses the corrected-timing branch with
  `--scheduler per-qubit --admission event --pregeneration-buffer-ms 5.3`.

Raw one-row-per-seed CSVs were produced under ignored `output/` directories;
the exact aggregate values above are the version-controlled experiment record.
