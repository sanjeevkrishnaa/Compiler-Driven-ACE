# Physical ACE shared-pool compiler matrix — 4x4 QFT, 30 paired seeds

## Audit status

The shared-pool compiler matrix passed its artifact audit on 2026-09-09:

- 90 policy/seed cells: matched ODG, fixed, and dynamic × seeds 0–29;
- 445,860 completed request instances (4,954 × 90);
- 193,741 compiler-pair records;
- no trace mismatch, incomplete cell, pair-accounting mismatch, duplicate pair
  consumption, non-target use, or out-of-range fidelity.

Generated source artifacts are local under
`output/qft_shared_pool_compiler_30seed_v2/` and include `audit.json`,
`summary.csv`, and `runs.json`.

## Shared-pool model

Every core has four physical communication memories. Compiler pre-generation
may occupy at most three, but no memory is statically reserved: demand can use
any free physical slot. At release, an exact ready compiler pair is preferred;
otherwise on-demand generation atomically acquires endpoint slots or waits.
Pending demand admission has priority over a new compiler preparation at the
same simulator time.

## Results

Values are means over 30 paired seeds. Latency excludes the fixed
pre-generation buffer. `Ready` is the request-specific prepared-pair success
rate; `fidelity@use` is compiler-pair fidelity at utilization.

| Policy | Latency (ms) | Ready | Fidelity@use | Expiry | On-demand fallback |
|---|---:|---:|---:|---:|---:|
| Matched ODG | 1.104216 | 0.00% | — | 0.00% | 100.00% |
| Fixed | 0.658471 | 51.92% | 0.7871 | 18.66% | 48.06% |
| Dynamic | 0.615906 | 56.83% | 0.8575 | 14.32% | 43.14% |

| Paired comparison | Mean latency reduction | 95% CI |
|---|---:|---:|
| Fixed vs matched ODG | 40.37% | [40.01, 40.72] |
| Dynamic vs matched ODG | 44.22% | [43.94, 44.50] |
| Dynamic vs fixed | 6.45% | [5.79, 7.10] |

## Interpretation

Dynamic is the clear within-ACE winner for this shared-pool contract: it
reduces latency versus both alternatives, supplies more intended pairs before
release, and uses fresher pairs with lower expiry. On-demand fallback remains
necessary for 43.14% of dynamic transfers because exact future knowledge does
not remove finite-memory, physical-generation, and endpoint-contention limits.

This is a within-backend result only. The next comparison must use the same
shared-pool model for ACE ODG/CGP/ACGP, then compare the same policy directions
in native SeQUeNCe without treating raw ACE and native milliseconds as equal.
