| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Hop readiness (%) |
| --- | ---: | ---: | ---: | ---: |
| ODG | 1.3373 | 94.981 | 3.4918 | 0.00 |
| ACGP | 0.8752 | 94.311 | 1.9304 | Not measured |
| Compiler quota6 + demand guard | 0.8691 | 93.982 | 2.1941 | 57.30 |

208-qubit QFT, frozen History routing, T-HQA/OEE mapping seed42, 4x4 mesh,
14 data slots/core, eight physical communication memories/core and physics seed60.
All strategies use10ns empty-layer gaps and the same per-qubit event scheduler.
The compiler uses quota6, generation budget8, offline active lookback2-16,
planner age cutoff17, demand guarding, execution-first ready-first admission,
all-chain preparation and native handoff. Release/dependency priority and runtime
planning are disabled. Physical coherence is unchanged; compiler reservations50ms.
ACGP has an explicit six-slot autonomous cache cap and retains native background
generation,200ms protocol period and period-aligned reservation expiries. Compiler
lookback, demand guard and launch budget do not govern ACGP. No ACGP tuning.
The compiler booking-counter check applies only to compiler reservations; generic
autonomous booking IDs are not a validated live-occupancy measurement in this
diagnostic. The ACGP cap reported here is the configured native protocol limit.

Latency is eligibility-to-EPR-delivery per hop, including admission wait. Fidelity
is delivered EPR fidelity, not circuit output fidelity. Makespan uses the same
end_to_end_latency_ms /1000 metric. Compiler hop readiness is the pregenerated-pair
hit fraction at individual hop eligibility. ACGP hop readiness is not measured
by that compiler-specific counter and is deliberately not inferred from protocol
pair totals or chain coverage. ODG readiness is zero by construction. All12784
requests completed in each trial, with clean audits and matching source hashes.
These are single-seed results.

Compiler wastage:21 reservation-expired pairs out of7380 generated (0.28455%);7359 used,0 evictions,0 remaining. ACGP raw protocol counter reports3.85199%, but is not validated pair wastage: its unused counter increments on memory release even when no generated pair exists. It must not be compared directly with compiler lifecycle wastage. ODG has no speculative pair inventory.
