# ACE static 2plus2 fixed-lead sensitivity, audited 30-seed sweep

All cells use immutable contracts, paired seeds 0--29, the locked trace, raw SHA-256 provenance, and a passing completion and request/pair-identity audit.

| Delta | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Fallback | Paired latency minus delta 2 (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.720845 | 44.61% | 0.8741 | 54.17% | 55.37% | 0.084833 |
| 2 | 0.805677 | 34.77% | 0.8496 | 55.17% | 65.21% | 0.000000 |
| 3 | 0.846865 | 29.85% | 0.8459 | 55.26% | 70.13% | -0.041187 |
| 4 | 0.865266 | 27.80% | 0.8399 | 55.47% | 72.20% | -0.059588 |
| 5 | 0.890028 | 24.92% | 0.7873 | 57.57% | 75.08% | -0.084350 |
| 6 | 0.919232 | 21.54% | 0.7504 | 58.82% | 78.46% | -0.113554 |

Raw `runs.json` files remain local and ignored. `provenance.json` binds each raw artifact and immutable contract by SHA-256.
