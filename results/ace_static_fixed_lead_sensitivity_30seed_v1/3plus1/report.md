# ACE static 3plus1 fixed-lead sensitivity, audited 30-seed sweep

All cells use immutable contracts, paired seeds 0--29, the locked trace, raw SHA-256 provenance, and a passing completion and request/pair-identity audit.

| Delta | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Fallback | Paired latency minus delta 2 (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.553104 | 64.38% | 0.8037 | 56.16% | 35.60% | 0.080127 |
| 2 | 0.633231 | 54.91% | 0.7673 | 56.89% | 45.06% | 0.000000 |
| 3 | 0.697352 | 47.19% | 0.7540 | 57.17% | 52.79% | -0.064122 |
| 4 | 0.732664 | 43.29% | 0.7216 | 57.98% | 56.71% | -0.099434 |
| 5 | 0.772076 | 38.67% | 0.6714 | 59.96% | 61.33% | -0.138845 |
| 6 | 0.807971 | 34.57% | 0.6156 | 61.19% | 65.43% | -0.174740 |

Raw `runs.json` files remain local and ignored. `provenance.json` binds each raw artifact and immutable contract by SHA-256.
