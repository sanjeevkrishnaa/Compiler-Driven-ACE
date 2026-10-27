# Compiler pre-generation studies

Read the current implementation report first. Earlier studies remain available
to explain the timing, allocation and admission issues that led to the fix.

| Order | Study | Status |
| --- | --- | --- |
| 1 | [Compiler memory handoff correction](compiler-memory-handoff-2026-10-28.md) | Current ownership fix and C=1..4 comparison. |
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
