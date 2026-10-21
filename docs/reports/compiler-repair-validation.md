# Compiler repair validation — 2026-10-21

The repaired compiler policies beat the corrected ODG baseline on every tested
seed of the original QFT-96 and the small random workload. Both baselines and
compiler modes use the same completion-release semantics, four physical
memories, request windows, buffers, workload order, and independently seeded
physical nodes. Compiler capacity remains three; no hardware advantage was
added. These measurements describe ACE entanglement-service replay, not full
quantum-state execution of the circuit.

## Changes

- Application completion releases its memory timecards immediately.
- Compiler adoption releases its original memory lease and quota after the
  local swap has finished. Lease release is local to an endpoint and idempotent.
- Each owned lease tracks and cancels its timeout, rule-load and application-map
  events. An old timeout cannot reset a reassigned memory or remove its map.
- Concurrent compiler reservations distinguish target request IDs in equality
  and hashing, avoiding aliasing of timecards and generation protocols.
- Definitive application rejection uses a 1 ms admission backoff. It no longer
  waits for the 50 ms physical-service timeout. Stale attempt callbacks are
  ignored, and all retry waiting remains included in latency.
- Rejected compiler jobs retry admission every 1 ms until acceptance or first
  application submission. Accepted jobs retain one-shot generation semantics.
- Each physical node is reseeded deterministically from the trial seed.
  Previously the CLI seed changed the timeline RNG but left node RNGs fixed.
- Exported full-trace records include per-request timing, node seeds, compiler
  pair provenance, source hashes and the implementation version.

The earlier dependency-preserving batching and retry-inclusive timing fixes
remain active. The latency definition is unchanged from metric version 2.

## Results

Values are mean request latency; reductions are paired by seed. Standard
deviations and exact aggregate values are in
`results/compiler_repaired_validation.csv`.

| Workload | Seeds | ODG ms | Fixed ms | Dynamic ms | Fixed reduction | Dynamic reduction | Dynamic makespan reduction |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original QFT-96, 4,954 hops | 3 | 1.0976 | 0.8607 | 0.6858 | 21.58% | 37.52% | 5.90% |
| Random-16, 62 hops | 10 | 1.1126 | 0.8668 | 0.4929 | 22.19% | 55.70% | 8.74% |

All 46,446 request records across these 39 trials completed. Compiler-pair
expiry is zero in both studies. QFT dynamic readiness is 48.56%; random dynamic
readiness is 71.94%. QFT dynamic has zero request retries in all three seeds.
Fixed had one prompt retry in each of QFT seeds 0 and 2, counted in latency.

Storage still costs fidelity. Mean delivered QFT fidelity is 0.9498 for ODG,
0.8604 for fixed, and 0.9003 for dynamic. Random dynamic delivers 0.9262.
Request latency gains must not be presented as identical end-to-end speedups:
the configured 5.3 ms buffers and empty-layer delays remain in makespan.
The workload/seed coverage here does not establish universal dominance.

## Verification

All 22 compiler tests pass, including physical integration, idempotent local
release, stale expiry, target identity, prompt rejection, admission cancellation,
independent node seeding, dependency ordering and timing regressions.

An audit of all nine full-QFT trials checked 44,586 completed request records
and 11,310 compiler pair records: timing stages sum to request latency, stages
are nonnegative, consumed pairs match their intended request, physical creation
precedes consumption, readiness uses strict first-submission timing, pair IDs
are unique per trial, and utilization fidelities stay within [0, 1].

The final compatibility smoke also exercises ODG, continuous,
adaptive-continuous, fixed and dynamic together.

## Reproduction

From the ACE checkout, with its compatible fork on PYTHONPATH:

```powershell
$env:PYTHONPATH = 'C:/Users/sanje/Desktop/BTP/repo/qnoc-stress-testing/SeQUeNCe'
python -B -m unittest discover -s test -p 'test_compiler*.py' -v

python -B run_compiler_pregeneration.py --trace C:/Users/sanje/Downloads/qft_requests.txt --strategies on-demand,fixed,dynamic --seeds 0,1,2 --total-memories 4 --compiler-memories 3 --generation-capacity 3 --delta-layers 6 --dynamic-lookahead-layers 8 --coherence-time-layers 10 --compiler-reservation-ms 1000 --stop-time-s 300 --output output/compiler_repaired_qft96_3seed

python -B run_trace_comparison.py --trace data/tracegen/random16_d80_seed303.txt --strategies on-demand,fixed,dynamic --seeds 0,1,2,3,4,5,6,7,8,9 --stop-time-s 5 --output output/compiler_repaired_random16_10seed
```

Full QFT raw records: `output/compiler_repaired_qft96_3seed/runs.json`.
Random trial summaries: `output/compiler_repaired_random16_10seed/summary.csv`.
Generated output remains ignored by Git; the compact aggregate CSV is available
under results for retaining the measured results with the code.
