# QAOA exact lead sweep with borrowing

Best observed initial lead by lowest pooled mean request latency: **L-9**, **0.892407 ms**. XY route winner: L-9; History route winner: L-8.

The primary ranking is transfer-count-weighted mean latency across XY and cumulative History, as requested. Each route has 29,605 transfers. The lowest pooled compiler waste occurs at L-8 (1.3056%). No weighted composite score is used.

| Initial lead | XY mean (ms) | History mean (ms) | Pooled mean (ms) | Mean completion (s) | Delivered fidelity | Pooled waste | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| L-1 | 1.294520 | 1.259035 | 1.276778 | 4.908457 | 0.946105 | 9.4842% | 47.188% |
| L-2 | 1.067584 | 1.060163 | 1.063874 | 4.360245 | 0.944256 | 4.8297% | 55.031% |
| L-3 | 0.996829 | 0.966871 | 0.981850 | 4.044245 | 0.943999 | 3.0612% | 57.685% |
| L-4 | 0.959980 | 0.942847 | 0.951414 | 3.998190 | 0.943425 | 2.4722% | 59.546% |
| L-5 | 0.942484 | 0.910544 | 0.926514 | 3.880089 | 0.943358 | 1.8612% | 60.670% |
| L-6 | 0.926338 | 0.896038 | 0.911188 | 3.882993 | 0.943061 | 1.7026% | 61.512% |
| L-7 | 0.920332 | 0.889069 | 0.904701 | 3.808992 | 0.943174 | 1.4807% | 61.919% |
| L-8 | 0.912708 | 0.874507 | 0.893607 | 3.755089 | 0.943064 | 1.3056% | 62.248% |
| L-9 | 0.901291 | 0.883523 | 0.892407 | 3.722439 | 0.943234 | 1.3235% | 62.040% |

## Protocol and evidence

Same implementation source fingerprints for all 18 cases on codex/l2-borrow-refill. Borrowing and immediate replenishment enabled, trace-order initial preparations, exact lead on communication-active layers, 8 communication memories per core with compiler quota 6, generation capacity 8, 50 ms reservation lifetime, mapping seed 42 and physics seed 60. Initial generation is restricted to the single configured layer; replacements remain immediate exceptions, subject to hardware capacity and demand priority.

All 18 cases completed 29,605 transfers and passed physical/ordering audits. Independently verified: exact initial planner lead, generation/use/expiry/remaining conservation, immediate replacement-request counts, source fingerprint equality, and matching parameters apart from lead and route/output paths.

L-2 and L-3 measurements were reused from the prior audited runs after these checks; the other 14 cases were simulated for this sweep. The 10-layer planner coherence guard admits preparation ages strictly below 10, so this sweep covers L-1 through L-9 without changing that guard.

Fidelity covers delivered EPR pairs, including on-demand fallback. Compiler pair waste is (expired + remaining) / generated. Prepared-pair fidelity is measured only among consumed compiler pairs. Total workload completion is separate from mean request latency. These are EPR-delivery metrics and exclude local data-qubit teleportation gates.

The Excel workbook contains the formula-based ranking, native charts, all route/lead observations, computed utilization/expiry/waste/coverage, and a provenance/protocol sheet. It was recalculated, checked against independent Python aggregation, and rendered for visual review. Native Excel application recalculation was not tested.

This is one fixed mapping and one matched physics seed, so the winner is the best observed setting in this sweep, not a cross-seed statistical conclusion. Strategy defaults were not changed.
