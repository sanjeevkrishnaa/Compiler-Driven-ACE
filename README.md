Paper: [Design and Simulation of the Adaptive Continuous Entanglement Generation Protocol](https://arxiv.org/abs/2502.01964)

Related: [Adaptive, Continuous Entanglement Generation for Quantum Networks](https://ieeexplore.ieee.org/document/9798130)

## Compiler-driven pre-generation

The ACE physical pre-generation/cache path now also supports offline compiler
traces.  Both fixed-delta and resource-aware dynamic scheduling are available,
with on-demand fallback plus pair creation/utilization fidelity, pre-ready
success, expiry, and wastage metrics.  See
[COMPILER_PREGENERATION.md](COMPILER_PREGENERATION.md) for the model and command.

The research runner also supports measured physical-time lead calibration and
paired multi-seed 95% confidence intervals. The original single-seed table is a
validation checkpoint, not a statistical conclusion.

The corrected ten-seed ACE results and the controlled comparison with the
native SeQUeNCe repository are reported in
[`results/ACE_VS_NATIVE_SEQUENCE.md`](results/ACE_VS_NATIVE_SEQUENCE.md).

Current audited 4x4 QFT result (4,954 requests, seeds 0--9): dynamic cap 3
reduces mean latency by 16.56% versus ACE ODG, while matched fixed delta 2
reduces it by 16.21%. Dynamic is only 0.41% faster than fixed on paired seeds,
and the 95% interval crosses zero, so the experiment does not establish a
reliable latency winner between them. Dynamic cap 2 eliminates expiry, at the
cost of lower readiness and a smaller 9.19% latency reduction. The native
implementation instead favors fixed because its earlier launches permit more
physical generation retries; the report explains why absolute values across
the two execution frameworks are not directly comparable.

Communication conflicts are scheduled in 2,831 sublayers, the bipartite lower
bound. Trace order is preserved whenever greedy batching is already optimal;
exact edge colouring is applied only to the three layers where it removes one
unnecessary sublayer.
