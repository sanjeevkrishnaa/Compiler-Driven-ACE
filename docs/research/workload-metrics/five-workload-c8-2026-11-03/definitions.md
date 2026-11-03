# Metric definitions and run profile

4x4 mesh; 14 data slots and eight communication memories per core (22 total
slots/core); T-HQA mapping with OEE initial placement, mapping seed 42; compiler
quota and generation capacity eight. Circuits have 208 logical qubits, leaving
one initial data vacancy per core out of 224 data slots. Physics seed is 60 only.
The study uses MQT Bench 2.3.0/Qiskit 2.3.1 and the pinned SeQUeNCe 0.8.1 engine.

QPE is MQT `qpeexact`; Draper is `draper_qft_adder`. Quantum Volume uses Qiskit's
`quantum_volume(208, depth=208, seed=42)` rather than an MQT factory. Pipeline
normalization/transpilation seed is 42; factories retain their own documented
defaults (QPE exact internally seeds its phase selection with 10). Quantum Volume
is a circuit workload here, not a measurement of a hardware Quantum Volume score.

Each circuit is generated and mapped once. XY and History preserve the same
migration endpoints and complete layer placements. XY is a shortest-path
baseline, not a claim of being the universally worst router. History's overload
threshold is eight memories, not four. Both routes use shortest paths.

Compiler runs use original logical-layer lookback 2-8, planner age limit ten,
all-chain preparation, 5 ms empty-layer gaps, 50 ms compiler reservations,
execution-first ready-first event admission, and native memory handoff. The
additional demand-priority guard is disabled. ODG receives the same eight-memory
bank. No preparation window is subtracted from latency.

- **Latency:** eligibility-to-EPR-delivery in ms per adjacent-hop request,
  including admission, protocol control, generation and retries. The CSV also
  stores latency per complete migration, summing its sequential hop intervals
  once, without adding admission a second time.
- **Fidelity:** mean fidelity of delivered EPR pairs, not circuit output fidelity.
- **Full coverage:** every hop of a migration has its own sufficiently faithful
  compiler pair cached at both endpoints when the logical layer opens.
- **Partial coverage:** at least one hop has a pair, but not every hop.
- **Zero/miss:** none of the migration's hops has a pair at that instant.
  Coverage is sampled before application admission and before launching new
  preparations. Pairs produced later do not retroactively count as ready.
  Percentages use complete migration chains as denominator, not hop requests.
  ODG has no compiler prefetch, hence full/partial/zero = 0/0/100 by definition;
  that is not a delivery failure.
- **Eviction:** a generated compiler pair released for a non-expiry reason;
  exact reasons, including progress releases, are retained in the raw counters.
- **Expiry:** generated pairs lost to reservation timeout or physical coherence,
  including records replaced after expiry.
- **Unused:** generated pairs still remaining at simulation end. The standard
  stop-after-workload cleanup interval is retained.

The three wastage categories are disjoint percentages of generated compiler
pairs. Their sum equals total compiler waste. They exclude failed preparation
attempts that never produced an EPR pair. ODG has no compiler pair inventory, so
these prefetched-pair wastage rates are N/A. `metrics.csv` retains counts and
denominators as well as percentages; `waste_reasons.json` retains release reasons.

The current simulator does not execute local data-qubit gates, teleportation
circuits or destination data-memory occupancy. The 5 ms idle gap remains a
placeholder. These results characterize this EPR-service model and one physics
seed per fixed mapping; they do not establish hardware-calibrated circuit
performance or statistical robustness.
