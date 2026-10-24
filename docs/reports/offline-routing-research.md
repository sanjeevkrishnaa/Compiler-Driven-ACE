# Can offline routing reduce the congestion?

Mapping held fixed; only the path of each qubit move is re-chosen, per layer, offline (exact optimisation, global knowledge of the layer). *Excess* is the demand above capacity, summed over cores and layers. All numbers pool the ten benchmarks and the three mapping seeds; data in `results/offline_routing_2026-10-24/`, code in `tools/routing_research/`.

**What is proved.** The optimiser is exact (no layer was left unproved), never worse than the mapper's own routes, and bounded below by two valid lower bounds: endpoint demand alone, and total demand minus cores x capacity. No routing can beat the larger of the two.

## Structural result, mesh, route counting (qubits in flight, what the per-qubit scheduler sees)

| Capacity | Extra hops | Excess now | Excess after re-routing | Lower bound | Overloaded layers | Added hops |
|---|---|---|---|---|---|---|
| 1 | 0 | 27043 | 21894 (19.0%) | 18336 | 4110 → 3801 | 0.00% |
| 1 | 2 | 27043 | 21018 (22.3%) | 18336 | 4110 → 3621 | 2.55% |
| 2 | 0 | 10385 | 6771 (34.8%) | 4995 | 1641 → 978 | 0.00% |
| 2 | 2 | 10385 | 6288 (39.5%) | 4995 | 1641 → 840 | 1.48% |
| 3 | 0 | 4774 | 1791 (62.5%) | 846 | 855 → 420 | 0.00% |
| 3 | 2 | 4774 | 1497 (68.6%) | 846 | 855 → 327 | 0.98% |
| 4 | 0 | 2216 | 348 (84.3%) | 78 | 482 → 102 | 0.00% |
| 4 | 2 | 2216 | 237 (89.3%) | 78 | 482 → 48 | 0.36% |

## Structural result, mesh, hop counting (the archive's counting)

| Capacity | Extra hops | Excess now | Excess after re-routing | Lower bound | Overloaded layers | Added hops |
|---|---|---|---|---|---|---|
| 1 | 0 | 62272 | 57123 (8.3%) | 34251 | 7965 → 7965 | 0.00% |
| 1 | 2 | 62272 | 57123 (8.3%) | 34251 | 7965 → 7965 | 0.00% |
| 2 | 0 | 30251 | 20103 (33.5%) | 14181 | 3427 → 2337 | 0.00% |
| 2 | 2 | 30251 | 18714 (38.1%) | 14181 | 3427 → 1974 | 3.21% |
| 3 | 0 | 19118 | 10122 (47.1%) | 6111 | 2660 → 1230 | 0.00% |
| 3 | 2 | 19118 | 9399 (50.8%) | 6111 | 2660 → 993 | 1.94% |
| 4 | 0 | 11327 | 3897 (65.6%) | 1728 | 1304 → 513 | 0.00% |
| 4 | 2 | 11327 | 3411 (69.9%) | 1728 | 1304 → 417 | 1.03% |

## Structural result, torus, route counting (qubits in flight, what the per-qubit scheduler sees)

| Capacity | Extra hops | Excess now | Excess after re-routing | Lower bound | Overloaded layers | Added hops |
|---|---|---|---|---|---|---|
| 1 | 0 | 20202 | 15858 (21.5%) | 14847 | 3826 → 3339 | 0.00% |
| 1 | 2 | 20202 | 15387 (23.8%) | 14847 | 3826 → 3312 | 1.73% |
| 2 | 0 | 6108 | 3351 (45.1%) | 2847 | 1319 → 702 | 0.00% |
| 2 | 2 | 6108 | 3108 (49.1%) | 2847 | 1319 → 630 | 0.93% |
| 3 | 0 | 1852 | 363 (80.4%) | 303 | 562 → 162 | 0.00% |
| 3 | 2 | 1852 | 342 (81.5%) | 303 | 562 → 159 | 0.09% |
| 4 | 0 | 493 | 15 (97.0%) | 6 | 220 → 15 | 0.00% |
| 4 | 2 | 493 | 6 (98.8%) | 6 | 220 → 6 | 0.04% |

## Structural result, torus, hop counting (the archive's counting)

| Capacity | Extra hops | Excess now | Excess after re-routing | Lower bound | Overloaded layers | Added hops |
|---|---|---|---|---|---|---|
| 1 | 0 | 44427 | 40083 (9.8%) | 23442 | 7722 → 7722 | 0.00% |
| 1 | 2 | 44427 | 40083 (9.8%) | 23442 | 7722 → 7722 | 0.00% |
| 2 | 0 | 17486 | 9630 (44.9%) | 7965 | 2728 → 1134 | 0.00% |
| 2 | 2 | 17486 | 8988 (48.6%) | 7965 | 2728 → 963 | 1.80% |
| 3 | 0 | 9250 | 3561 (61.5%) | 2073 | 1875 → 594 | 0.00% |
| 3 | 2 | 9250 | 3383 (63.4%) | 2073 | 1875 → 510 | 0.74% |
| 4 | 0 | 4054 | 375 (90.7%) | 216 | 827 → 87 | 0.00% |
| 4 | 2 | 4054 | 357 (91.2%) | 216 | 827 → 81 | 0.08% |

## Simulated effect on latency, mesh (on-demand, same mapping, endpoints and seeds)

Latency in ms, mean of nine runs. In brackets: paired reduction against the original routes (positive = faster), its standard deviation over the nine pairs, and the number of pairs in which re-routing was faster. Last column: fraction of requests that waited, original → re-routed (no extra hops).

| Workload | Memories | Original routes | Re-routed, shortest paths only | Re-routed, up to +2 hops | Waited |
|---|---|---|---|---|---|
| Graph state | 2 | 2.72 | 1.53 (+42.3% ±9.9; 9/9) | 1.41 (+46.6% ±8.9; 9/9) | 0.281 → 0.086 |
| Graph state | 3 | 1.53 | 1.15 (+22.9% ±11.8; 9/9) | 1.19 (+19.6% ±13.5; 9/9) | 0.121 → 0.000 |
| Graph state | 4 | 1.24 | 1.16 (+6.0% ±7.6; 7/9) | 1.21 (+1.9% ±8.9; 4/9) | 0.029 → 0.000 |
| Draper QFT adder | 2 | 2.16 | 1.69 (+21.1% ±7.9; 9/9) | 1.48 (+31.1% ±6.8; 9/9) | 0.211 → 0.115 |
| Draper QFT adder | 3 | 1.30 | 1.16 (+10.3% ±3.3; 9/9) | 1.16 (+10.5% ±3.7; 9/9) | 0.055 → 0.007 |
| Draper QFT adder | 4 | 1.15 | 1.13 (+1.3% ±1.3; 8/9) | 1.14 (+1.1% ±0.8; 9/9) | 0.008 → 0.000 |
| QAOA | 2 | 3.42 | 2.24 (+34.5% ±2.4; 9/9) | 2.12 (+38.0% ±2.4; 9/9) | 0.376 → 0.206 |
| QAOA | 3 | 1.74 | 1.25 (+28.4% ±2.3; 9/9) | 1.19 (+31.4% ±2.2; 9/9) | 0.172 → 0.037 |
| QAOA | 4 | 1.27 | 1.13 (+10.9% ±1.7; 9/9) | 1.13 (+11.5% ±1.6; 9/9) | 0.058 → 0.003 |
| QFT | 2 | 4.72 | 3.49 (+26.1% ±2.4; 9/9) | 3.03 (+35.9% ±2.1; 9/9) | 0.430 → 0.312 |
| QFT | 3 | 2.39 | 1.53 (+35.9% ±2.2; 9/9) | 1.47 (+38.2% ±2.3; 9/9) | 0.249 → 0.097 |
| QFT | 4 | 1.59 | 1.19 (+25.2% ±2.4; 9/9) | 1.17 (+26.6% ±2.0; 9/9) | 0.130 → 0.018 |
| Random circuit | 2 | 1.27 | 1.13 (+10.6% ±1.3; 9/9) | 1.12 (+11.7% ±1.3; 9/9) | 0.042 → 0.007 |
| Random circuit | 3 | 1.12 | 1.11 (+1.2% ±0.3; 9/9) | 1.11 (+1.3% ±0.3; 9/9) | 0.006 → 0.000 |
| Random circuit | 4 | 1.11 | 1.11 (+0.2% ±0.1; 9/9) | 1.11 (+0.2% ±0.2; 8/9) | 0.001 → 0.000 |

## Simulated effect on latency, torus (on-demand, same mapping, endpoints and seeds)

Latency in ms, mean of nine runs. In brackets: paired reduction against the original routes (positive = faster), its standard deviation over the nine pairs, and the number of pairs in which re-routing was faster. Last column: fraction of requests that waited, original → re-routed (no extra hops).

| Workload | Memories | Original routes | Re-routed, shortest paths only | Re-routed, up to +2 hops | Waited |
|---|---|---|---|---|---|
| Graph state | 2 | 1.86 | 1.27 (+31.2% ±7.2; 9/9) | 1.28 (+31.0% ±6.9; 9/9) | 0.157 → 0.033 |
| Graph state | 3 | 1.25 | 1.10 (+11.0% ±7.4; 8/9) | 1.12 (+10.3% ±8.7; 8/9) | 0.033 → 0.000 |
| Graph state | 4 | 1.11 | 1.12 (-0.4% ±1.7; 1/9) | 1.11 (+0.3% ±3.9; 2/9) | 0.000 → 0.000 |
| Draper QFT adder | 2 | 2.25 | 1.45 (+35.6% ±1.9; 9/9) | 1.26 (+44.0% ±1.4; 9/9) | 0.226 → 0.075 |
| Draper QFT adder | 3 | 1.28 | 1.15 (+10.5% ±1.8; 9/9) | 1.14 (+10.7% ±1.0; 9/9) | 0.053 → 0.007 |
| Draper QFT adder | 4 | 1.13 | 1.11 (+1.8% ±0.6; 9/9) | 1.11 (+1.6% ±0.8; 9/9) | 0.008 → 0.000 |
| QAOA | 2 | 2.47 | 1.66 (+32.3% ±4.7; 9/9) | 1.62 (+34.2% ±4.7; 9/9) | 0.265 → 0.111 |
| QAOA | 3 | 1.40 | 1.15 (+17.6% ±4.6; 9/9) | 1.14 (+18.3% ±4.3; 9/9) | 0.083 → 0.004 |
| QAOA | 4 | 1.17 | 1.13 (+3.2% ±2.8; 9/9) | 1.13 (+3.1% ±2.6; 9/9) | 0.016 → 0.000 |
| QFT | 2 | 2.79 | 2.37 (+14.7% ±7.3; 9/9) | 2.42 (+12.7% ±7.8; 9/9) | 0.303 → 0.221 |
| QFT | 3 | 1.51 | 1.21 (+19.3% ±6.0; 9/9) | 1.24 (+17.3% ±6.1; 9/9) | 0.102 → 0.023 |
| QFT | 4 | 1.21 | 1.13 (+6.8% ±3.2; 9/9) | 1.12 (+7.3% ±3.0; 9/9) | 0.028 → 0.001 |
| Random circuit | 2 | 1.19 | 1.11 (+6.1% ±0.9; 9/9) | 1.11 (+6.3% ±0.9; 9/9) | 0.022 → 0.002 |
| Random circuit | 3 | 1.11 | 1.11 (+0.4% ±0.1; 9/9) | 1.11 (+0.3% ±0.1; 9/9) | 0.001 → 0.000 |
| Random circuit | 4 | 1.11 | 1.11 (-0.0% ±0.1; 1/9) | 1.11 (+0.0% ±0.1; 3/9) | 0.000 → 0.000 |

