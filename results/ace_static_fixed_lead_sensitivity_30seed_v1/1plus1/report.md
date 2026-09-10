# ACE static 1plus1 fixed-lead sensitivity, audited 30-seed sweep

All cells use immutable contracts, paired seeds 0--29, the locked trace, raw SHA-256 provenance, and a passing completion and request/pair-identity audit.

| Delta | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Fallback | Paired latency minus delta 2 (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.910873 | 22.57% | 0.7861 | 56.63% | 77.43% | -0.002186 |
| 2 | 0.908687 | 22.85% | 0.8267 | 54.58% | 77.12% | 0.000000 |
| 3 | 0.943862 | 18.82% | 0.8390 | 54.85% | 81.15% | -0.035175 |
| 4 | 0.959724 | 16.92% | 0.7699 | 55.57% | 83.08% | -0.051037 |
| 5 | 0.979470 | 14.48% | 0.6890 | 57.87% | 85.52% | -0.070782 |
| 6 | 0.994275 | 12.77% | 0.6390 | 59.89% | 87.22% | -0.085587 |

Raw `runs.json` files remain local and ignored. `provenance.json` binds each raw artifact and immutable contract by SHA-256.
