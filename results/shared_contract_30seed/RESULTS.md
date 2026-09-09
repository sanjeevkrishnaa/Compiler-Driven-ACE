# Shared QFT 4×4 contract: 30-seed results

Contract: `qft-4x4-cross-repository-v1`. All rows contain 30 paired seeds and 4,954 requests per seed.

> Absolute latency is not comparable across backends: ACE and native SeQUeNCe implement different physical protocols and latency boundaries. Compare policy effects within a backend/profile only.

## Aggregate results

| Backend | Memory profile | Policy | Latency (ms, mean [95% CI]) | Pre-ready | Fidelity at use | Expiry | Fallback |
|---|---|---:|---:|---:|---:|---:|---:|
| ACE | full-odg-4 | odg | 1.104216 [1.100372, 1.108059] | 0.0000 | — | 0.0000% | 1.0000 |
| ACE | static-1plus1 | dynamic | 1.009635 [1.006245, 1.013025] | 0.1097 | 0.8039 | 0.0429% | 0.8903 |
| ACE | static-1plus1 | fixed | 1.000413 [0.997311, 1.003515] | 0.1228 | 0.8551 | 0.0984% | 0.8770 |
| ACE | static-1plus1 | matched-on-demand | 1.104216 [1.100372, 1.108059] | 0.0000 | — | 0.0000% | 1.0000 |
| ACE | static-2plus2 | dynamic | 0.978956 [0.975026, 0.982887] | 0.1443 | 0.8798 | 0.0467% | 0.8556 |
| ACE | static-2plus2 | fixed | 0.983236 [0.979288, 0.987184] | 0.1406 | 0.8567 | 0.0619% | 0.8593 |
| ACE | static-2plus2 | matched-on-demand | 1.104216 [1.100372, 1.108059] | 0.0000 | — | 0.0000% | 1.0000 |
| ACE | static-3plus1 | dynamic | 0.802312 [0.799402, 0.805221] | 0.3539 | 0.8212 | 0.0550% | 0.6459 |
| ACE | static-3plus1 | fixed | 0.805875 [0.802593, 0.809156] | 0.3465 | 0.7834 | 0.0601% | 0.6533 |
| ACE | static-3plus1 | matched-on-demand | 1.104216 [1.100372, 1.108059] | 0.0000 | — | 0.0000% | 1.0000 |
| native-SeQUeNCe | full-odg-4 | odg | 0.076451 [0.075992, 0.076910] | 0.0000 | — | 0.0000% | 0.0000 |
| native-SeQUeNCe | static-1plus1 | dynamic | 0.018990 [0.018682, 0.019298] | 0.6966 | 0.8660 | 0.0000% | 0.1714 |
| native-SeQUeNCe | static-1plus1 | fixed | 0.037042 [0.036735, 0.037348] | 0.5146 | 0.6671 | 0.0027% | 0.4730 |
| native-SeQUeNCe | static-1plus1 | matched-on-demand | 0.076451 [0.075992, 0.076910] | 0.0000 | — | 0.0000% | 1.0000 |
| native-SeQUeNCe | static-2plus2 | dynamic | 0.018990 [0.018682, 0.019298] | 0.6966 | 0.8660 | 0.0000% | 0.1714 |
| native-SeQUeNCe | static-2plus2 | fixed | 0.005028 [0.004854, 0.005201] | 0.9229 | 0.7393 | 0.0000% | 0.0419 |
| native-SeQUeNCe | static-2plus2 | matched-on-demand | 0.076451 [0.075992, 0.076910] | 0.0000 | — | 0.0000% | 1.0000 |
| native-SeQUeNCe | static-3plus1 | dynamic | 0.018990 [0.018682, 0.019298] | 0.6966 | 0.8660 | 0.0000% | 0.1714 |
| native-SeQUeNCe | static-3plus1 | fixed | 0.005028 [0.004854, 0.005201] | 0.9229 | 0.7393 | 0.0000% | 0.0419 |
| native-SeQUeNCe | static-3plus1 | matched-on-demand | 0.076451 [0.075992, 0.076910] | 0.0000 | — | 0.0000% | 1.0000 |

## Paired latency effects

Positive reduction means the candidate is faster than the baseline.

| Backend | Profile | Candidate vs baseline | Mean reduction | 95% CI |
|---|---|---|---:|---:|
| ACE | static-3plus1 | fixed vs matched-on-demand | 27.017% | [26.802, 27.233]% |
| ACE | static-3plus1 | dynamic vs matched-on-demand | 27.339% | [27.135, 27.544]% |
| ACE | static-3plus1 | dynamic vs fixed | 0.437% | [0.121, 0.754]% |
| ACE | static-2plus2 | fixed vs matched-on-demand | 10.956% | [10.777, 11.135]% |
| ACE | static-2plus2 | dynamic vs matched-on-demand | 11.343% | [11.138, 11.548]% |
| ACE | static-2plus2 | dynamic vs fixed | 0.433% | [0.202, 0.665]% |
| ACE | static-1plus1 | fixed vs matched-on-demand | 9.399% | [9.256, 9.542]% |
| ACE | static-1plus1 | dynamic vs matched-on-demand | 8.564% | [8.414, 8.715]% |
| ACE | static-1plus1 | dynamic vs fixed | -0.923% | [-1.117, -0.728]% |
| native-SeQUeNCe | static-3plus1 | fixed vs matched-on-demand | 93.429% | [93.227, 93.630]% |
| native-SeQUeNCe | static-3plus1 | dynamic vs matched-on-demand | 75.171% | [74.904, 75.438]% |
| native-SeQUeNCe | static-3plus1 | dynamic vs fixed | -279.638% | [-288.542, -270.735]% |
| native-SeQUeNCe | static-2plus2 | fixed vs matched-on-demand | 93.429% | [93.227, 93.630]% |
| native-SeQUeNCe | static-2plus2 | dynamic vs matched-on-demand | 75.171% | [74.904, 75.438]% |
| native-SeQUeNCe | static-2plus2 | dynamic vs fixed | -279.638% | [-288.542, -270.735]% |
| native-SeQUeNCe | static-1plus1 | fixed vs matched-on-demand | 51.547% | [51.249, 51.846]% |
| native-SeQUeNCe | static-1plus1 | dynamic vs matched-on-demand | 75.171% | [74.904, 75.438]% |
| native-SeQUeNCe | static-1plus1 | dynamic vs fixed | 48.747% | [48.167, 49.326]% |

## Interpretation rule

The shared trace, seeds, memory budgets, scheduling parameters, and deterministic conflict serialization are identical. Protocol semantics are not identical; therefore this is a reproducible cross-implementation consistency study, not a claim that one simulator is faster than the other.
