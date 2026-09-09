# Compiler-driven EPR pre-generation in ACE

## Deliverable

This branch integrates compiler-informed EPR pre-generation into ACE's physical
execution path and evaluates it using the supplied 4×4 QFT communication trace.
The compiler supplies future inter-core transfers; ACE still performs physical
reservation, generation, storage noise, pair consumption, and on-demand
fallback. A compiler schedule is therefore an intent, not a guarantee that a
pair is available.

The experiment is paired with native SeQUeNCe. Both implementations use the
same trace, deterministic conflict serialization, memory profiles, scheduler
parameters, and seeds. They have different protocol stacks and latency scopes,
so raw milliseconds are never compared across backends. Performance claims are
made only within one backend and memory profile.

## Frozen experiment

| Item | Value |
|---|---|
| Workload | Supplied `qft_requests.txt`, 4×4 mesh / 16 cores |
| Trace SHA-256 | `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1` |
| Logical workload | 96 qubits, 766 source layers, 4,954 transfers |
| Executed schedule | 2,831 conflict-free sublayers |
| Serialization SHA-256 | `6b9520823830c50caaefb57baa737c2a8af834ef9474fe628df35def103a235d` |
| Seeds | 0–29, paired across policies |
| Fixed | two-sublayer lead |
| Dynamic | eight-sublayer lookahead, one-sublayer minimum lead |
| Coherence horizon | ten sublayers |
| Logical sublayer duration | 100 µs |

The authoritative definition is
[`experiments/qft_4x4_comparison_v1.json`](experiments/qft_4x4_comparison_v1.json).
Its native counterpart is byte-identical (contract SHA-256
`3b40ca19b24da57df9bbc6291c1161908facc267617a733cd118627554fb8e95`).

## Fair memory profiles

| Profile | Total memories/core | Compiler bank | On-demand bank | Policies |
|---|---:|---:|---:|---|
| `full-odg-4` | 4 | 0 | 4 | Full ODG |
| `static-3plus1` | 4 | 3 | 1 | Matched ODG, fixed, dynamic |
| `static-2plus2` | 4 | 2 | 2 | Matched ODG, fixed, dynamic |
| `static-1plus1` | 2 | 1 | 1 | Matched ODG, fixed, dynamic |

“1+1” means two communication/entanglement memories per core, not two logical
data qubits. Static modes use disjoint banks. Matched ODG uses only the
on-demand bank, which prevents it from receiving the compiler's memories.

## Code changes

| Area | Files | Change |
|---|---|---|
| Contract | `experiment_contract.py`, `experiments/qft_4x4_comparison_v1.json` | Strict profile/trace validation and deterministic conflict serialization. |
| Physical partition | `reservation.py`, `parallel_core.py` | Compiler/adaptive reservations and application RSVP reservations use disjoint banks; old shared-pool behavior remains unchanged by default. |
| Scheduling | `compiler_trace.py`, `run_compiler_pregeneration.py` | Full ODG, matched ODG, static allocation, fixed/dynamic options, exact serialized scheduling, and contract-controlled CLI validation. |
| Timing | `parallel_core.py` | Contract runs enforce a 100 µs minimum logical sublayer; legacy behavior remains unchanged otherwise. |
| Reproduction | `run_contract_matrix.py`, `audit_compiler_results.py` | Refuse non-empty outputs; record hashes, seeds, banks, schedules and per-pair utilization. |
| Analysis | `summarize_contract_comparison.py` | Verify full paired matrices and write means, 95% t intervals and paired effects. |
| Tests | `test/test_experiment_contract.py`, `test/test_compiler_one_shot.py` | Cover contract fingerprints, scheduling, static banks and compatibility paths. |

## Reproduction

```bash
# Contract-only validation.
.venv/bin/python run_compiler_pregeneration.py \
  --trace /absolute/path/qft_requests.txt \
  --contract experiments/qft_4x4_comparison_v1.json \
  --profile static-2plus2 --validate-only

# Complete ACE 30-seed matrix.
.venv/bin/python run_contract_matrix.py \
  --trace /absolute/path/qft_requests.txt \
  --output output/qft_contract_v1_30seed

# Generate the paired ACE/native analysis after both matrices complete.
.venv/bin/python summarize_contract_comparison.py \
  --contract experiments/qft_4x4_comparison_v1.json \
  --ace-root output/qft_contract_v1_30seed \
  --native-root /absolute/path/SeQUeNCe-compiler-native/output/qft_contract_v1_30seed \
  --output-dir results/shared_contract_30seed
```

## Audited results

All 1,486,200 ACE request instances completed. The lifecycle audit verified
181,228 compiler-pair records: generated/used/expired accounting, single use,
target-specific utilization, and fidelity bounds. Native SeQUeNCe completed
the same number of request instances with zero failures; its audit additionally
checked compressed traces, memory bounds and stage timing.

| ACE profile | Policy | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Paired change vs matched ODG |
|---|---|---:|---:|---:|---:|---:|
| 3+1 | Fixed | 0.805875 | 34.65% | 0.7834 | 0.060% | 27.02% faster |
| 3+1 | Dynamic | 0.802312 | 35.39% | 0.8212 | 0.055% | 27.34% faster |
| 2+2 | Fixed | 0.983236 | 14.06% | 0.8567 | 0.062% | 10.96% faster |
| 2+2 | Dynamic | 0.978956 | 14.43% | 0.8798 | 0.047% | 11.34% faster |
| 1+1 | Fixed | 1.000413 | 12.28% | 0.8551 | 0.098% | 9.40% faster |
| 1+1 | Dynamic | 1.009635 | 10.97% | 0.8039 | 0.043% | 8.56% faster |

Full and matched ACE ODG average 1.104216 ms. Complete 95% confidence
intervals and trial aggregates are in
[`results/shared_contract_30seed/RESULTS.md`](results/shared_contract_30seed/RESULTS.md),
[`aggregates.csv`](results/shared_contract_30seed/aggregates.csv), and
[`paired_effects.csv`](results/shared_contract_30seed/paired_effects.csv).

## Interpretation

Dynamic is a statistically positive ACE improvement over fixed at 3+1 (0.437%,
95% CI 0.121%–0.754%) and 2+2 (0.433%, 0.202%–0.665%), and it uses fresher,
higher-fidelity pairs. At 1+1 it is 0.923% slower (95% CI −1.117% to −0.728%).
Here fixed plans about 2,673 feasible preparations and ACE accepts about 610
per seed; dynamic proposes all 4,954 but ACE accepts only about 544. Accepted
dynamic pairs wait about 90.5 ms on average versus 62.8 ms for fixed, reducing
readiness and increasing decoherence. This exposes a planner-versus-physical
reservation mismatch under severe memory pressure.

Native SeQUeNCe has a different physical response. At 3+1 and 2+2, fixed has
92.29% pre-ready transfers and 0.005028 ms latency, while dynamic has 69.66%
and 0.018990 ms: fixed's earlier lead gives more physical-generation retries.
At 1+1, fixed drops to 51.46% readiness and 0.037042 ms while dynamic remains
at 69.66% and 0.018990 ms, because its window can spread launches. Native 3+1
and 2+2 are identical: after serialization a third compiler memory is never
needed by this workload. This is a workload property, not missing data.

## Scope and next step

ACE and native SeQUeNCe are not an absolute-latency benchmark. The valid result
is their within-backend policy direction and resource trade-off. The next
experiment should add ACE reservation-aware admission control to the dynamic
planner, then run a new versioned contract rather than overwrite this baseline.
