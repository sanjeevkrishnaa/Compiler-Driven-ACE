# QAOA same-edge borrowing with immediate replenishment

Branch `codex/l2-borrow-refill`, forked from main `3c16c89`. Both arms use trace-order preparation, exact L-2 on the active-layer axis, 6 compiler memories out of 8 per core, generation capacity 8, 50 ms reservation lifetime, mapping seed 42 and physics seed 60. Frozen QAOA-224 traces have 29,605 transfers. Only borrowing differs between the arms.

| Routing | Baseline mean (ms) | Borrow mean (ms) | Mean reduction | Baseline completion (s) | Borrow completion (s) |
|---|---:|---:|---:|---:|---:|
| xy | 1.269869 | 1.067584 | 15.93% | 6.005260 | 4.438001 |
| history | 1.203605 | 1.060163 | 11.92% | 5.682349 | 4.282488 |

Positive reduction means borrowing improves latency. These are EPR-delivery metrics, not data-qubit teleportation gate timings.

| Routing | Borrowed pairs | Replenishment requests | Immediate attempts | Baseline expiry | Borrow expiry | Baseline waste | Borrow waste |
|---|---:|---:|---:|---:|---:|---:|---:|
| xy | 7089 | 7088 | 7088 | 0.058% | 4.422% | 0.091% | 4.462% |
| history | 7523 | 7516 | 7516 | 0.233% | 5.169% | 0.265% | 5.194% |

## Previous autonomous baselines

These frozen seed-60, eight-memory measurements are reused for context, not rerun. They use the same workload and routing traces.

| Strategy | XY mean (ms) | History mean (ms) | XY completion (s) | History completion (s) |
|---|---:|---:|---:|---:|
| ODG | 1.825247 | 1.815357 | 7.717813 | 7.665711 |
| CGP | 1.161454 | 1.096300 | 5.021932 | 4.662787 |
| ACGP | 1.138424 | 1.093582 | 4.975037 | 4.688228 |
| Old main CD, path priority L-1-equivalent | 1.224372 | 1.173503 | 4.698713 | 4.554407 |

All four runs completed every transfer and passed the physical/order audit. Every recorded borrowed pair was on the same physical edge as the borrower, from a later trace request. Every replenishment request was issued at the consumption timestamp. Replenishment can be blocked by real resources or the demand guard; an immediate attempt does not imply instantaneous successful generation. Targets already in service are not prepared redundantly.

The baseline is rerun on the same implementation rather than borrowing measurements from another branch. Source fingerprints and all parameters except borrowing/output match between arms. The unfinished completion-cleanup implementation is excluded. This is a single matched physics seed, not a statistical claim. Raw command, metadata, timing, pair lifecycle and audit files are retained in each case directory.
