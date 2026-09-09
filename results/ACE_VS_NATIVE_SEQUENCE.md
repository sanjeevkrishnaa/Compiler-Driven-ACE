# ACE versus native SeQUeNCe: 4x4 QFT comparison

## Scope and comparability

Both repositories replay the same compiler trace (SHA-256
`61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`):
16 cores, 96 logical qubits, 766 layers, and 4,954 adjacent-core migrations.
Every reported cell contains ten trials, seeds 0--9, and completed every
request.

The implementations are not interchangeable benchmarks. ACE uses its custom
reservation/cache lifecycle on SeQUeNCe 0.8.1 and reports reservation plus
service latency after removing its configured pre-generation buffer. The
native repository uses its newer physical workload engine, a 100-us logical
layer duration, Barrett--Kok attempts, teleportation and correction stages.
Its compiler modes use a static 3+1 memory partition, whereas ACE uses a shared
four-memory pool with a cap of three compiler reservations. Therefore absolute
latency must not be interpreted as a simulator speed comparison. Within-repo
policy differences and the direction of readiness/fidelity trade-offs are the
valid comparisons.

## Ten-seed results

Values in brackets are two-sided 95% Student-t confidence intervals. ACE fixed
uses delta 2 here to match the native fixed scheduler; the separately retained
ACE delta-6 result is not used in this matched-policy table.

| Implementation | Policy | Latency, ms | Pre-ready | Fidelity at use | Expiry |
|---|---|---:|---:|---:|---:|
| ACE + SeQUeNCe 0.8.1 | ODG | 1.1054 [1.0961, 1.1148] | 0% | 0.9498 overall | 0% |
| ACE + SeQUeNCe 0.8.1 | Fixed delta 2 | 0.9262 [0.9181, 0.9342] | 20.75% [20.23, 21.27] | 0.8141 [0.8124, 0.8158] | 2.11% [1.90, 2.32] |
| ACE + SeQUeNCe 0.8.1 | Dynamic, lead 1 | 0.9223 [0.9149, 0.9297] | 21.43% [21.18, 21.68] | 0.8195 [0.8181, 0.8210] | 2.00% [1.89, 2.12] |
| Native SeQUeNCe | ODG, all four memories | 0.2095 [0.2062, 0.2127] | 0% | 0.9498 | 0% |
| Native SeQUeNCe | Fixed delta 2, static 3+1 | 0.3135 [0.3081, 0.3190] | 42.18% [41.87, 42.50] | 0.8630 [0.8622, 0.8639] | 0% |
| Native SeQUeNCe | Dynamic, static 3+1 | 0.3524 [0.3465, 0.3584] | 30.46% [30.06, 30.87] | 0.9193 [0.9187, 0.9198] | 0% |

ACE dynamic cap 3 reduces latency by 16.56% versus ACE ODG (95% CI
16.07--17.05%). ACE fixed delta 2 reduces it by 16.21% (15.62--16.81%). In a
direct paired-seed comparison, ACE dynamic is 0.41% faster on average than
fixed delta 2, but its 95% interval (-0.03--0.86%) crosses zero. The present
ten-seed experiment therefore does not establish a reliable latency advantage
between those two ACE policies.

Native fixed and dynamic reduce latency by 39.86% and 32.40%, respectively,
against the partition-matched one-memory ODG baseline. They are slower than
ordinary four-memory native ODG because the static 3+1 partition introduces
queueing; the corresponding penalties are 49.70% and 68.27%.

## Why dynamic is worse in the native repository

The offline schedules are not the cause: the analytical planner admits 2,358
fixed and 2,408 dynamic requests. The native physical execution shows that the
later dynamic launches leave less time for failed generation attempts to retry:

- fixed averages 6,748.6 preparation attempts, 4,685.0 failed attempts, and
  2,089.8 pre-ready pairs;
- dynamic averages 5,287.3 attempts, 3,867.2 failures, and 1,509.2 pre-ready
  pairs;
- dynamic readiness is 11.72 percentage points below fixed and latency is
  12.41% higher;
- dynamic pairs are fresher, improving fidelity by 0.0563.

Thus the native result is a retry-time versus freshness trade-off. Dynamic is
not universally worse: in ACE it is slightly better than fixed delta 2 on
latency, readiness, fidelity, and expiry. The different outcome follows from
different physical-generation, memory-partition and application-lifecycle
implementations.

## ACE memory-capacity result

The ten-seed ACE cap-2 profile produces 1.0038 ms mean latency, 11.68%
pre-readiness, 0.8905 compiler-pair fidelity at utilization, and zero expiry.
It improves latency by 9.19% versus ACE ODG (95% CI 8.81--9.57%). Cap 3 offers
more latency reduction and readiness; cap 2 offers the verified zero-waste
profile. Neither is described as universally optimal.

## Validation and provenance

- ACE runtime: official SeQUeNCe v0.8.1, commit
  `cf5283cdfd6692a82a090d15fb09fbc01bd322fc`.
- ACE seed 0 reproduces the previous 1.107035-ms ODG checkpoint exactly.
- A fixed-node-seed defect was corrected: experiment seeds now deterministically
  reseed every router and BSM while preserving seed-zero behavior.
- Communication conflicts are serialized in the theoretical minimum 2,831
  sublayers. Stable greedy order is retained in all already-optimal layers;
  exact bipartite edge colouring is limited to the three layers where it saves
  one sublayer, changing only 12 request positions relative to the old order.
- The ACE audit covers 50 full trials, 247,700 request instances, and 37,189
  compiler-pair records with conserved accounting, target-only consumption,
  bounded fidelities, exact trace hash, and 100% completion.
- Native values come from the audited reference artifact in the native
  repository; its audit covers 40 trials and 198,160 successful requests.

Machine-readable sources are `ace_official_081_qft_10seed_aggregate.csv`,
`ace_official_081_qft_10seed_paired.csv`,
`ace_official_081_qft_10seed_audit.json`, and
`ace_vs_native_sequence_qft_10seed.csv` in this directory.

The raw `runs.json` files remain under `output/` locally because their combined
size is about 91 MB and that directory is intentionally ignored. Recreate the
tracked aggregate and audit after running the documented matrix with:

```bash
python aggregate_compiler_results.py \
  output/final_hybrid_qft_cap3/summary.csv \
  output/final_hybrid_qft_dynamic_cap2/summary.csv \
  output/final_hybrid_qft_fixed_delta2/summary.csv \
  --baseline on-demand \
  --output results/ace_official_081_qft_10seed_aggregate.csv \
  --paired-output results/ace_official_081_qft_10seed_paired.csv

python audit_compiler_results.py \
  output/final_hybrid_qft_cap3/runs.json \
  output/final_hybrid_qft_dynamic_cap2/runs.json \
  output/final_hybrid_qft_fixed_delta2/runs.json \
  --expected-trace-sha256 61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1 \
  --output results/ace_official_081_qft_10seed_audit.json

python compare_repository_results.py \
  --ace-aggregate results/ace_official_081_qft_10seed_aggregate.csv \
  --ace-audit results/ace_official_081_qft_10seed_audit.json \
  --native-reference /path/to/native_compiler_4x4_qft_10seed_summary.json \
  --output results/ace_vs_native_sequence_qft_10seed.csv
```
