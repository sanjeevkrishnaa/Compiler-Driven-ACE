# ACE fixed-lead sensitivity, corrected 30-seed sweep

All cells use the locked trace, paired seeds 0–29, the listed immutable contracts, and a passing completion and request/pair identity audit.

| Delta | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Fallback | Paired latency − delta 2 (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.598283 | 59.17% | 0.8584 | 55.32% | 40.80% | 0.036904 |
| 2 | 0.635186 | 54.72% | 0.7856 | 57.18% | 45.26% | 0.000000 |
| 3 | 0.726038 | 44.15% | 0.7732 | 58.68% | 55.82% | -0.090852 |
| 4 | 0.746164 | 41.91% | 0.7344 | 59.64% | 58.09% | -0.110978 |
| 5 | 0.784498 | 37.25% | 0.7035 | 61.44% | 62.75% | -0.149312 |
| 6 | 0.818597 | 33.56% | 0.6530 | 62.66% | 66.44% | -0.183411 |

Raw `runs.json` files are ignored locally; `provenance.json` records their SHA-256 values and contract bindings.

The historical ACE cap-three implementation is retained for this fixed-lead sweep. It must not be used as a capacity-only comparator for the new cap-four atomic-admission control until a matched cap-three atomic control is run.
