> Historical implementation/context record. Current behavior and validated results are documented in [compiler-repair-validation.md](../reports/compiler-repair-validation.md).

# Correctness update: metric version 2

Historical tables in this repository predate this correction and must be
regenerated before making performance claims.

- Communication batches preserve trace order at every core, including all
  hops of a migration. Disjoint independent requests still run in parallel.
- Mean request latency starts at the first submission and excludes only the
  initial configured buffer. Failed attempts and retry buffers remain counted.
- Timing stages are disjoint: retry waiting, setup beyond the final attempt's
  buffer, and physical service. They sum to reported request latency.
- End-to-end latency is actual wall-clock makespan including buffers, idle
  layers and retries, rather than a sum of reconstructed per-layer stages.
- Compiler pre-ready means physical creation strictly before first application
  submission, not before the later generation start after the buffer.

The old seed-0 results and rankings are historical, not validation of this
corrected execution model. Rerun physical comparisons with the compatible
SeQUeNCe fork and report completion, makespan, request latency and fidelity.

## Validation on 2026-10-21

- All 13 compiler tests pass, including the existing physical lifecycle tests
  and six new ordering, retry, timing and readiness regressions.
- Placement replay after batching has zero source mismatches for the original
  4,954-hop QFT and all three small TraceGen traces.
- The five-policy physical seed-0 random16 run completed all 62 requests in
  every policy. Artifacts: output/correctness_v2_random16_seed0/.
- Corrected mean request latency / wall-clock makespan (ms): ODG
  13.7162 / 1207.0021; continuous 52.2161 / 3539.6004;
  adaptive-continuous 54.0532 / 3598.2003; fixed 31.4194 / 2305.3018;
  dynamic 43.7839 / 3071.2016. The simulation horizon was 5 seconds.
- This single-seed smoke check does not establish a general policy ranking.
  The old compiler speedup claim does not hold on this corrected small random
  workload. Full-QFT and multi-seed physical comparisons remain to be rerun.
