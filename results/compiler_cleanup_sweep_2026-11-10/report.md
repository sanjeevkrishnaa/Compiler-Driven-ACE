# QAOA lead sweep after completion cleanup

Best observed lead by lowest pooled mean request latency: **L-2**, **0.797110 ms**. XY winner: L-2; cumulative History winner: L-2.

Compared with the same lead before cleanup, mean latency changed by -25.075%, delivered fidelity by 0.027408 percentage points, and total compiler waste by -3.1890 percentage points.

| Lead | Before mean (ms) | After mean (ms) | Change | Fidelity | Waste | Mean makespan (s) |
|---|---:|---:|---:|---:|---:|---:|
| L-1 | 1.276778 | 0.880155 | -31.064% | 0.946348 | 4.7635% | 3.410778 |
| L-2 | 1.063874 | 0.797110 | -25.075% | 0.944530 | 1.6408% | 3.239875 |
| L-3 | 0.981850 | 0.814294 | -17.065% | 0.944118 | 1.0487% | 3.329729 |
| L-4 | 0.951414 | 0.804246 | -15.468% | 0.943592 | 0.8131% | 3.348830 |
| L-5 | 0.926514 | 0.819977 | -11.499% | 0.943425 | 0.5681% | 3.418631 |
| L-6 | 0.911188 | 0.817415 | -10.291% | 0.943085 | 0.4504% | 3.451684 |
| L-7 | 0.904701 | 0.815111 | -9.903% | 0.943233 | 0.4694% | 3.435633 |
| L-8 | 0.893607 | 0.816110 | -8.672% | 0.943113 | 0.4350% | 3.419732 |
| L-9 | 0.892407 | 0.819179 | -8.206% | 0.943324 | 0.4085% | 3.380482 |

## Controls and validation

All 18 post-cleanup cases were freshly simulated at implementation commit 38aad24, with identical source fingerprints. Each case completed 29,605 requests and passed physical and ordering audits. Compiler tests: 187 passed. The earlier preliminary cleanup sweep was discarded and is not included.

Matched to the archived pre-cleanup sweep: mapping seed 42, physics seed 60, XY and cumulative all-past-layer History routing, exact L-1 through L-9 initial generation on communication-active layers, trace order, borrowing and immediate refill, 8 memories with compiler quota 6 and generation capacity 8. The 10-layer coherence planner guard is unchanged. Refill remains an immediate scheduling exception subject to demand and hardware constraints. Default lead remains L-2.

Collection independently validates unchanged per-case runtime parameters except output location, the expected cleanup-only source changes, exact planned lead, completed request counts, no audit violations, immediate replacement counts, and generated = used + expired + cancelled + remaining.

Waste includes (expired + cancelled + remaining) / generated. Cancellation is therefore counted as wasted generation, not hidden as a successful cleanup. The legacy expired category also includes rejected and failed-handoff releases; actual reservation-timeout counts are reported separately in the Runs sheet. Fidelity includes all delivered EPR pairs, including fallback. Makespan is total workload completion; the pooled makespan column is the arithmetic mean of both routes.

Completion diagnostics compare pair generation timestamps against the target request completion time. In-flight work may complete within the one-way classical cancellation delay; the cleanup prevents continued obsolete preparation beyond that delay. Per-case timings and reasons are stored in completion_diagnostics.json.

Across the sweep, generated-after-completion records fell from 7,614 to 584. Maximum delay fell from 9.400173 ms to 0.100000248 ms. Every post-cleanup case is within 0.100001 ms.

The new workbook preserves the old workbook and adds a BeforeAfter sheet, all three latency/fidelity/waste charts, route-level results, cancellation and actual-timeout counts, formula-based rankings, and protocol/source evidence. Formula recalculation and cached XLSX values are checked against independent aggregation, with visual inspection of rendered sheets. Native Microsoft Excel recalculation was not tested.

These results use one fixed mapping and physics seed. They identify the best observed lead for this matched sweep, not a cross-seed statistical winner. No scheduling strategy or default lead was changed after fixing cleanup.
