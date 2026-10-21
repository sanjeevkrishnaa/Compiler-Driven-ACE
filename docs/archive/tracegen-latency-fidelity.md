> Historical implementation/context record. Current behavior and validated results are documented in [compiler-repair-validation.md](../reports/compiler-repair-validation.md).

# ACE trace-generation study: latency and fidelity report

## Scope

This report summarizes the seed-0 physical ACE simulations produced from the
TraceGen (QM2026) workload suite. Every result uses the same 4x4 mesh, four
physical memories per core, common request windows, and conflict-free batching
of requests sharing a core. The compared policies are:

- **On-demand:** create EPRs only when an application request arrives.
- **Continuous:** ACE's autonomous continuous cache with a fixed neighbor
  selection policy.
- **Adaptive-continuous:** ACE's autonomous cache with feedback-adaptive
  neighbor selection.
- **Fixed compiler:** one-shot preparation at a fixed six-layer offset.
- **Dynamic compiler:** one-shot preparation in the latest feasible compiler
  layer within an eight-layer lookahead window.

Latency is mean application-request latency; fidelity is the mean fidelity of
the EPR delivered to the application. Lower latency and higher fidelity are
both preferable.

## Results

### QFT smoke workload

This run covers the first 15 QFT layers, containing four hop requests. It is a
pipeline smoke test rather than a full-QFT conclusion.

| Strategy | Completed | Mean latency (ms) | Latency change vs on-demand | Delivered fidelity | Fidelity change vs on-demand |
| --- | ---: | ---: | ---: | ---: | ---: |
| On-demand | 4/4 | 1.5000 | — | 0.9498 | — |
| Continuous | 4/4 | 0.3000 | -80.00% | 0.8161 | -14.08% |
| Adaptive-continuous | 4/4 | 0.3500 | -76.67% | 0.8345 | -12.14% |
| Fixed compiler | 4/4 | 0.9750 | -35.00% | 0.8371 | -11.87% |
| Dynamic compiler | 4/4 | 1.1500 | -23.33% | 0.9386 | -1.18% |

The dynamic compiler policy makes the smallest latency improvement in this
very short burst, but it preserves almost all of on-demand fidelity. Continuous
generation is fastest, at a roughly 0.13 fidelity penalty.

### Cuccaro arithmetic workload

The full generated Cuccaro trace has 218 layers and nine hop requests.

| Strategy | Completed | Mean latency (ms) | Latency change vs on-demand | Delivered fidelity | Fidelity change vs on-demand |
| --- | ---: | ---: | ---: | ---: | ---: |
| On-demand | 9/9 | 0.8778 | — | 0.9498 | — |
| Continuous | 9/9 | 0.6889 | -21.52% | 0.8457 | -10.96% |
| Adaptive-continuous | 9/9 | 0.7667 | -12.66% | 0.8511 | -10.40% |
| Fixed compiler | 9/9 | 0.7667 | -12.66% | 0.9185 | -3.29% |
| Dynamic compiler | 9/9 | 0.7667 | -12.66% | 0.9325 | -1.83% |

All pre-generation policies lower latency. At the same measured latency as the
fixed policy, dynamic scheduling raises delivered fidelity from 0.9185 to
0.9325, making it the best compiler choice in this workload.

### Random-circuit workload

The full random trace contains 33 layers and 62 hop requests, making it the
most active workload in this initial suite.

| Strategy | Completed | Mean latency (ms) | Latency change vs on-demand | Delivered fidelity | Fidelity change vs on-demand |
| --- | ---: | ---: | ---: | ---: | ---: |
| On-demand | 62/62 | 1.2291 | — | 0.9498 | — |
| Continuous | 62/62 | 0.2887 | -76.51% | 0.8351 | -12.07% |
| Adaptive-continuous | 62/62 | 0.3887 | -68.37% | 0.8510 | -10.41% |
| Fixed compiler | 62/62 | 1.1371 | -7.48% | 0.9058 | -4.63% |
| Dynamic compiler | 62/62 | 1.0597 | -13.78% | 0.9239 | -2.73% |

Continuous caching has the lowest latency, but its fidelity loss is more than
four times the dynamic compiler policy's loss. Dynamic compiler preparation is
the best latency/fidelity compromise among the compiler methods: it improves
latency by 13.78% while keeping fidelity within 0.0259 of on-demand.

## Cross-workload interpretation

The latency/fidelity frontier is consistent across the three workloads:

| Objective | Best initial policy | Trade-off |
| --- | --- | --- |
| Lowest latency | Continuous | Fastest, but incurs a 10.96–14.08% relative fidelity reduction. |
| Lowest latency with autonomous adaptation | Adaptive-continuous | Usually higher fidelity than continuous, but also higher latency. |
| Best compiler-driven fidelity | Dynamic compiler | Preserves fidelity better than fixed compiler scheduling by generating closer to demand. |
| Highest fidelity | On-demand | Avoids storage decoherence, but pays full generation latency. |

Dynamic compiler scheduling is the recommended default where application
fidelity matters: it consistently improves over on-demand latency and avoids
the substantial decoherence cost of speculative continuous caches. Continuous
generation is appropriate only when latency is the overriding objective and
the lower delivered fidelity is acceptable.

## Limitations and next experiment

These are single-seed results and should not be used for statistical claims.
The next run should use seeds `0` through `9` for every workload and report
mean, standard deviation, and confidence intervals for latency and fidelity.
The raw source files are:

- `output/tracegen/qft16_seed101_fair_smoke/summary.csv`
- `output/tracegen/cuccaro16_seed202/summary.csv`
- `output/tracegen/random16_d80_seed303/summary.csv`
