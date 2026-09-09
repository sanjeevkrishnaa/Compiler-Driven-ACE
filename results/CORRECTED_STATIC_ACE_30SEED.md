# Corrected physical ACE static-bank matrix — 4x4 QFT, 30 paired seeds

## Status

This is the completed rerun after the ACE compiler-reservation lifecycle fix.
It supersedes the earlier ACE static-bank numbers for interpretation. The
artifacts were audited successfully on 2026-09-09:

- four artifacts, 300 configuration/strategy/seed cells;
- 1,486,200 request instances (4,954 requests × 30 seeds × 10 policy cells);
- 100% completion in every cell;
- no trace-hash mismatch, compiler pair-accounting mismatch, duplicate pair
  consumption, non-target pair use, or out-of-range recorded fidelity.

Raw files are kept locally under `output/qft_static_corrected_30seed/`,
including `audit.json`, per-profile `summary.csv`, and per-run utilization
traces in `runs.json`. They are not committed because they are generated.

## Controlled setup

The input is the supplied `qft_requests.txt` (SHA-256
`61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`), a
4x4 mesh, 4,954 neighbour transfers, and the deterministic 2,831-sublayer
conflict serialization. Each profile has a matched on-demand row plus fixed
and dynamic compiler pre-generation, with seeds 0–29 paired within the
profile. Static memory is a per-core partition.

## Results

Means are across the 30 paired seeds. `Ready` is the proportion of application
transfers that used their intended prepared compiler pair; `fidelity@use` is
the compiler-pair fidelity at utilization. Latency excludes the fixed
pre-generation buffer consistently across rows.

| Profile | Policy | Latency (ms) | Ready | Fidelity@use | Expiry | Paired latency reduction vs matched ODG (95% CI) |
|---|---|---:|---:|---:|---:|---:|
| 3+1 | Matched ODG | 1.104216 | 0.00% | — | 0.00% | — |
| 3+1 | Fixed | 0.658419 | 51.87% | 0.7682 | 18.29% | 40.37% [40.00, 40.74] |
| 3+1 | Dynamic | 0.575869 | 61.59% | 0.8039 | 15.74% | 47.85% [47.54, 48.15] |
| 2+2 | Matched ODG | 1.104216 | 0.00% | — | 0.00% | — |
| 2+2 | Fixed | 0.821357 | 32.97% | 0.8496 | 14.41% | 25.62% [25.30, 25.94] |
| 2+2 | Dynamic | 0.741142 | 42.13% | 0.8738 | 11.77% | 32.88% [32.52, 33.25] |
| 1+1 | Matched ODG | 1.104216 | 0.00% | — | 0.00% | — |
| 1+1 | Fixed | 0.908687 | 22.85% | 0.8267 | 9.17% | 17.71% [17.55, 17.86] |
| 1+1 | Dynamic | 0.910578 | 22.57% | 0.7861 | 13.27% | 17.54% [17.37, 17.71] |

## Fixed versus dynamic

Dynamic lowers paired mean latency by **12.52%** versus fixed at 3+1 (95% CI
[11.80, 13.24]) and **9.75%** at 2+2 ([9.11, 10.40]). It is **0.21% slower**
at 1+1 ([-0.49, 0.07]); the interval includes zero, so this run does not show
a reliable fixed/dynamic latency winner at the tightest profile. Dynamic's
benefit at 3+1 and 2+2 is accompanied by higher readiness, fresher compiler
pairs, and lower expiry; at 1+1, reduced preparation opportunity and capacity
contention remove that advantage.

## Scope and limitation

This establishes the corrected ACE static-bank result. It does not establish
an ACE-versus-native speed winner: raw milliseconds differ by backend
implementation. The next valid comparisons are ACE shared-pool ODG/CGP/ACGP/
fixed/dynamic and native shared-pool under the same contract, followed by
within-backend paired comparisons.
