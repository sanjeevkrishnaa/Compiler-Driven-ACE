Paper: [Design and Simulation of the Adaptive Continuous Entanglement Generation Protocol](https://arxiv.org/abs/2502.01964)

Related: [Adaptive, Continuous Entanglement Generation for Quantum Networks](https://ieeexplore.ieee.org/document/9798130)

## Compiler-driven pre-generation

> **Read first:** [`MASTER_README.md`](MASTER_README.md) is the comprehensive
> project narrative and the current source of truth. It records which results
> are audited historical artifacts, which ACE results require rerunning after
> the reservation-lifecycle correction, and what is currently in progress.

The ACE physical pre-generation/cache path now also supports offline compiler
traces.  Both fixed-delta and resource-aware dynamic scheduling are available,
with on-demand fallback plus pair creation/utilization fidelity, pre-ready
success, expiry, and wastage metrics.  See
[COMPILER_PREGENERATION.md](COMPILER_PREGENERATION.md) for the model and command.

The research runner also supports measured physical-time lead calibration and
paired multi-seed 95% confidence intervals. The original single-seed table is a
validation checkpoint, not a statistical conclusion.

The earlier ten-seed ACE/native comparison is retained as historical context
in [`results/ACE_VS_NATIVE_SEQUENCE.md`](results/ACE_VS_NATIVE_SEQUENCE.md).
It must not be used for final ACE conclusions until the corrected ACE matrix
is rerun and audited.

Historical 4x4 QFT result (4,954 requests, seeds 0--9): dynamic cap 3
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

The next controlled study uses an identical, hash-verified experiment contract
in ACE and native SeQUeNCe. It adds real static `3+1`, `2+2`, and two-total
memory `1+1` banks, a partition-matched ODG baseline, 30 paired seeds, and
identical serialized request deadlines. See
[SHARED_EXPERIMENT_CONTRACT.md](SHARED_EXPERIMENT_CONTRACT.md).

That matrix is retained as a historical audited artifact. The ACE portion is
being rerun after the lifecycle correction; see the 30-seed aggregate and
paired effects in
[`results/shared_contract_30seed/RESULTS.md`](results/shared_contract_30seed/RESULTS.md).

For the full technical narrative—architecture, code-level changes, exact
contract, audited 30-seed results, ACE/native interpretation, limitations, and
reproduction commands—read
[`COMPILER_DRIVEN_ACE_4X4_REPORT.md`](COMPILER_DRIVEN_ACE_4X4_REPORT.md).

For the complete project history, current verified status, distinction between
historical and controlled experiments, pending work, and recommended research
sequence, see [`MASTER_PROJECT_STATUS.md`](MASTER_PROJECT_STATUS.md).
