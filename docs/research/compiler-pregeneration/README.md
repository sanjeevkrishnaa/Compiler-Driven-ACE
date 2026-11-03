# Compiler pre-generation studies

## November 3 admission and timing experiments

- [Quota sweep, demand guard, release retries and runtime planning](preparation-policy-2026-11-03/README.md)
- [QFT: quota-six compiler versus ODG and ACGP, including wastage limits](qft-three-strategies-10ns-2026-11-03/README.md)
- [QAOA: CGP and ACGP comparison](cgp-acgp-10ns-2026-11-03/README.md)
- [Active-layer lookback 2-16 with 10 ns empty gaps](active16-10ns-2026-11-03/README.md)
- [BV with active-layer preparation](bv-active16-10ns-2026-11-03/README.md)
- [Five-workload eight-memory study](../workload-metrics/five-workload-c8-2026-11-03/README.md)
- [Verified nonbinding-memory comparison](../workload-metrics/unlimited-memory-2026-11-03/README.md)
- [Preparation admission CLI controls](../../reference/preparation-admission.md)

These are dated experimental profiles, not the permanent architecture defaults.
The eight-memory studies used 208 logical qubits, 14 data slots/core and memory
efficiency 0.95. They precede the separately committed wall-clock study and its
efficiency-0.8 defaults. Their archived commands, configuration and source
snapshots under `results/` preserve the measured setup. Do not reproduce their
numbers using a newer default configuration or compare them directly with a
different architecture profile. Historical ACGP wastage-counter limitations are
recorded with the affected results; they are not corrected retrospectively.

## Earlier lifecycle studies

The compiler reservation lifetime is **50 ms**. See the [window selection and validation](reservation-window-2026-10-29.md).

**Current default:** in-place ownership handoff for EPR delivery, restored after
the user's requested online research. See the [source-backed memory lifecycle
and metric scope](pair-consumption-research-2026-10-28.md). The temporary
[extra-memory comparison](extra-memory-revert-2026-10-28.md) remains available
as a distinct model. These latencies measure entanglement delivery, not full
data teleportation.

Read the current implementation report first. Earlier studies remain available
to explain the timing, allocation and admission issues that led to the fix.

| Order | Study | Status |
| --- | --- | --- |
| 1 | [Compiler memory handoff correction](compiler-memory-handoff-2026-10-28.md) | Earlier opt-in ownership handoff and C=1..4 comparison. |
| 2 | [Ready-pair admission priority](ready-priority-2026-10-28.md) | Verified FIFO issue and ready-first scheduling. Its measurements precede handoff. |
| 3 | [C=1..4 allocation sweep](ready-allocation-2026-10-28.md) | Historical extra-slot consumption; records the C=4 stall before the fix. |
| 4 | [Full-chain policy experiments](full-chain-optimization-2026-10-27.md) | Historical selection/confirmation experiments. |
| 5 | [Latency metric and allocation diagnosis](dynamic-latency-diagnosis-2026-10-27.md) | Historical metric distinction and C=2 baseline. |

`data/` contains immutable derived seed rows, aggregate tables and audit outcomes
for each dated study. Do not reinterpret historical FIFO/swap results as
measurements of the current handoff implementation.

The complete 32-run handoff evidence is committed under
[`results/compiler_memory_handoff_2026-10-28/`](../../../results/compiler_memory_handoff_2026-10-28/README.md).
It contains original command paths and source snapshots; those remain unchanged
after directory cleanup. Current commands live in
[`tools/compiler_study/`](../../../tools/compiler_study/README.md).
