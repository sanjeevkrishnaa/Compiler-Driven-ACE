# Shared ACE/native 4x4 QFT experiment contract

## Purpose

`experiments/qft_4x4_comparison_v1.json` is the authoritative configuration for
the next comparison. The identical file is stored in the native repository.
Its SHA-256 must match in both checkouts. The contract prevents a label such as
"2+2" from silently referring to different memory or scheduler behavior.

This is a policy comparison, not an absolute simulator-latency benchmark. ACE
and native SeQUeNCe deliberately retain different physical protocol stacks.
The contract records those differences and permits only within-repository,
paired-seed latency claims. Cross-repository comparisons are limited to policy
direction, readiness/fidelity/expiry trade-offs, and failure mechanisms.

## Frozen workload and schedule

- Exact trace SHA-256:
  `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`.
- 4x4 mesh, 16 cores, 96 logical qubits, 766 source layers, 4,954 transfers.
- Same-core conflicts are transformed before planning in both repositories.
- The resulting 2,831 sublayers have request-layer-map SHA-256
  `6b9520823830c50caaefb57baa737c2a8af834ef9474fe628df35def103a235d`.
- Fixed delta is two sublayers. Dynamic lookahead is eight sublayers with a
  one-sublayer minimum lead. Generation capacity equals compiler-bank size.
- Publication runs use paired seeds 0--29.

## Memory profiles

| Profile | Total entanglement memories/core | Compiler bank | On-demand bank | Policies |
|---|---:|---:|---:|---|
| `full-odg-4` | 4 | 0 | 4 | full ODG |
| `static-3plus1` | 4 | 3 | 1 | matched ODG, fixed, dynamic |
| `static-2plus2` | 4 | 2 | 2 | matched ODG, fixed, dynamic |
| `static-1plus1` | 2 | 1 | 1 | matched ODG, fixed, dynamic |

"Two memories" means two communication/entanglement memories at each core, not
two logical data qubits. Each elementary EPR consumes one memory at each
endpoint. Matched ODG intentionally leaves the compiler bank unused and uses
only the on-demand bank, providing the correct baseline for a static split.

ACE's historical shared-pool results remain valid for that model, but they are
not substituted for these new static-bank cells.

## Validation and execution

Validate one profile without simulation:

```bash
python run_compiler_pregeneration.py \
  --trace /absolute/path/qft_requests.txt \
  --contract experiments/qft_4x4_comparison_v1.json \
  --profile static-2plus2 --validate-only
```

Run a one-seed, non-publishable physical validation:

```bash
python run_compiler_pregeneration.py \
  --trace /absolute/path/qft_requests.txt \
  --contract experiments/qft_4x4_comparison_v1.json \
  --profile static-2plus2 --contract-seed-limit 1 \
  --output output/contract_smoke_static_2plus2
```

Run all four 30-seed publication profiles:

```bash
python run_contract_matrix.py \
  --trace /absolute/path/qft_requests.txt \
  --output output/qft_contract_v1
```

The matrix runner refuses nonempty profile directories. Use a new output root
instead of overwriting an earlier experiment. Contract-controlled CLI options
are rejected. Every artifact records the contract hash, profile, memory banks,
serialization hash, seed status, and complete runtime parameters.

## Validation and result status

All four ACE profiles completed the full 30-seed matrix. Every request
completed, and the lifecycle audit verified request uniqueness, generated-pair
accounting, target-specific utilization, expiry states, and fidelity bounds.
The paired aggregate tables and the deliberately limited cross-backend
interpretation are in
[`results/shared_contract_30seed/RESULTS.md`](results/shared_contract_30seed/RESULTS.md).
