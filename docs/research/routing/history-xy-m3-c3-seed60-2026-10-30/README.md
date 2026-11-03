# XY versus History with three communication memories, 2026-10-30

M=3 physical communication memories/core, C=3 compiler quota, generation
capacity=3; 4x4 mesh; same 96-qubit T-HQA/OEE seed-42 placements and routed
traces as the earlier comparison. Physics seed 60 only, compiler dynamic,
all-chain preparation, two-layer lead, ready-first admission, native handoff,
50 ms reservation cap. Data slots remain unchanged; this experiment reduces
the physical communication bank, not just a logical compiler quota.

All six trials completed and passed order/ownership audits. Runtime metadata
explicitly records all three capacity parameters as 3. This is a single-seed
comparison and provides no estimate of physics-seed variation.

| Workload | Route | Hop latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| qft | xy | 0.8507 | 3.4612 | 93.782 | 70.49 |
| qft | history | 0.7863 | 3.4023 | 93.725 | 73.60 |
| qaoa | xy | 1.5991 | 4.4065 | 94.020 | 47.69 |
| qaoa | history | 1.3858 | 4.1849 | 93.980 | 50.70 |
| bv | xy | 0.4458 | 1.5857 | 93.265 | 100.00 |
| bv | history | 0.4458 | 1.5857 | 93.265 | 100.00 |

History versus XY:

- qft: latency -7.57%; makespan -1.70%; readiness +3.10 percentage points.
- qaoa: latency -13.34%; makespan -5.03%; readiness +3.01 percentage points.
- bv: latency +0.00%; makespan +0.00%; readiness +0.00 percentage points.

Readiness counts hop requests consuming a pair generated before their first
application submission, not necessarily before eligibility. Fidelity is delivered
EPR fidelity, not circuit fidelity. The simulated makespan includes the existing
5 ms empty-layer gaps (about 1.58 s on BV); no preparation window is subtracted.
Data teleportation and local gate execution are not simulated. Congestion demand
thresholds in the earlier four-slot plots do not represent this three-slot bank.

## Matched M=4/C=4 reference (seed 60 only)

Do not compare a new single seed directly to the previous four-seed means.
The following uses the exact same seed 60 and source fingerprints:

| Workload | Route | M3/C3 latency (ms) | M4/C4 latency (ms) | M3/C3 makespan (s) | M4/C4 makespan (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| qft | xy | 0.8507 | 0.6403 | 3.4612 | 3.2788 |
| qft | history | 0.7863 | 0.5892 | 3.4023 | 3.2226 |
| qaoa | xy | 1.5991 | 1.1276 | 4.4065 | 3.8536 |
| qaoa | history | 1.3858 | 1.0044 | 4.1849 | 3.7064 |
| bv | xy | 0.4458 | 0.4458 | 1.5857 | 1.5857 |
| bv | history | 0.4458 | 0.4458 | 1.5857 | 1.5857 |

Raw commands, traces, metadata, timing records, pair readiness and audits are retained in the dated results archive.
