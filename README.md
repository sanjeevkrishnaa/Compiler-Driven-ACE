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
