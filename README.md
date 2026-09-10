Paper: [Design and Simulation of the Adaptive Continuous Entanglement Generation Protocol](https://arxiv.org/abs/2502.01964)

Related: [Adaptive, Continuous Entanglement Generation for Quantum Networks](https://ieeexplore.ieee.org/document/9798130)

## Compiler-driven pre-generation

> **Read first:** [`MASTER_README.md`](MASTER_README.md) is the comprehensive
> project narrative and current source of truth. It separates historical
> development results from the completed, audited physical 30-seed studies.

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

The completed shared-pool controlled study uses an identical, hash-verified
4x4 QFT trace and 30 paired seeds in ACE and native SeQUeNCe. Each core has
four shared physical memories; speculative/compiler work is capped at three,
and demand has atomic fallback access to any free endpoint slots. It reports
physical ACE ODG/CGP/ACGP/fixed/dynamic and native matched-ODG/fixed/dynamic.
Read the final audited table and interpretation in
[`results/SHARED_POOL_FINAL_COMPARISON_30SEED.md`](results/SHARED_POOL_FINAL_COMPARISON_30SEED.md).

The earlier matrix is retained as a historical artifact. The corrected ACE
static-bank rerun has passed audit; see
[`results/CORRECTED_STATIC_ACE_30SEED.md`](results/CORRECTED_STATIC_ACE_30SEED.md).

For the full technical narrative—architecture, code-level changes, exact
contract, audited 30-seed results, ACE/native interpretation, limitations, and
reproduction commands—read
[`COMPILER_DRIVEN_ACE_4X4_REPORT.md`](COMPILER_DRIVEN_ACE_4X4_REPORT.md).

For the complete project history, current verified status, distinction between
historical and controlled experiments, pending work, and recommended research
sequence, see [`MASTER_PROJECT_STATUS.md`](MASTER_PROJECT_STATUS.md).

For trace-driven physical ODG/CGP/ACGP, including the ACE 0.8.1 runtime
requirement and shared-pool validation command, see
[`ADAPTIVE_BASELINE_SPEC.md`](ADAPTIVE_BASELINE_SPEC.md).

The reproducible aggregator for the final report is
[`summarize_shared_pool_study.py`](summarize_shared_pool_study.py). It reads
the audited run JSON files, computes only seed-paired effects within one
backend, and intentionally does not produce cross-backend latency claims.
