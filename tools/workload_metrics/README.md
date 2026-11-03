# Five-workload metrics profile

The dated study uses a 4x4 mesh, 14 data slots plus eight communication memories
per core, T-HQA/OEE seed-42 placement, 208 logical qubits (one initial data vacancy
per core), compiler quota/generation capacity eight, and physics seed 60.
XY and History use identical mapping transitions. History's routing threshold
is eight, rather than the four-slot threshold used by earlier routing studies.

Generate the inputs with the study environment and `mapper` on PYTHONPATH:

```text
python -B tools/congestion_study/run_study.py --mapper-dir mapper --workloads qft qpeexact qaoa draper_qft_adder quantum_volume --logical-qubits 208 --total-qubits 352 --memory-slots 8 --on-demand-reserve 0 --placer T-HQA --seeds 42 --mapping-only --output output/five-workload-c8-2026-11-03/inputs
```

The evidence archive retains the exact routing and simulation driver, commands,
and source snapshots. Its driver calls `heavy_routing.build(..., capacity=8)`;
the physical CLI receives `--total-memories 8 --compiler-memories 8
--generation-capacity 8 --record-chain-coverage`. Ordinary four-slot routing
presets are not a substitute for these settings.

Compile the finished results:

```text
python -B tools/workload_metrics/report.py --study output/five-workload-c8-2026-11-03 --output docs/research/workload-metrics/five-workload-c8-2026-11-03
```

The report refuses incomplete trials or inconsistent engine-facing source
fingerprints. Latency is per-hop eligibility-to-EPR-delivery; metrics.csv also
retains whole-migration latency. Fidelity is delivered EPR fidelity.

Coverage is sampled before layer admission or preparation: full means every hop
in a migration has a request-specific, sufficiently faithful pair cached at both
endpoints; partial means some; zero/miss means none. The denominator is complete
migration chains, not hop requests. ODG necessarily has zero compiler prefetch.

Waste percentages use generated compiler pairs as denominator, with disjoint
categories: eviction (non-expiry release), expiry (reservation/coherence expiry,
including replacement after expiry), and unused (remaining at simulation end).
Raw reasons are retained. Their sum equals total compiler waste. ODG has no
compiler pair inventory, so those rates are N/A.

All runs use execution-first ready-first admission, original logical 2-8
lookback, 5 ms empty gaps, 50 ms reservations, and native handoff. The additional
demand-first guard is disabled. This is EPR-service simulation, not local-gate
execution or data teleportation. It does not measure a Quantum Volume score.

For the compiler-only XY/History memory-capacity comparison, use:

```powershell
python -B tools/workload_metrics/report_unlimited.py --baseline docs/research/workload-metrics/five-workload-c8-2026-11-03/metrics.csv --study output/unlimited-memory-2026-11-03 --output docs/research/workload-metrics/unlimited-memory-2026-11-03
```

This report requires ten completed capacity-verified trials, matching reference
node seeds, fixed generation capacity eight, and planner equivalence to
unconstrained storage. See the report's definitions.md for the finite-pool proof
and the limits of this single-seed comparison.

The quota/admission study uses the same frozen QAOA History trace, eight physical
memories and generation budget eight, with10ns empty gaps and active lookback2-16:

```powershell
python -B tools/workload_metrics/report_preparation_policy.py
```

It compares compiler quotas4-7, demand guarding, release/dependency priority and
runtime planning against a freshly rerun ODG control. Its report uses hop readiness.
See `docs/reference/preparation-admission.md` for the individual CLI switches.
