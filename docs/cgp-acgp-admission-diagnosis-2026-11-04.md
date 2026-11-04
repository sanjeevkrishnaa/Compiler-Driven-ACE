# CGP/ACGP admission diagnosis

The initial 224-qubit matrix contained 80 autonomous-policy cases. Eighteen
had worse mean hop latency than matching ODG; every loss was in the four-memory
configuration. Every eight-memory case improved over ODG. A mean-hop loss is
not necessarily a makespan loss: Graph State/XY/CGP-4 had slightly worse mean
latency but shorter workload completion time.

## Findings

1. The initial study retained a fixed autonomous cache limit of three for
   both physical memory counts. In four memories, three speculative bookings
   leave just one application slot; the original physical adoption path swaps
   from cached memory into a separately booked application memory. This is
   genuine contention from the chosen split, not a claim that CGP always wins.
2. Event-driven ready-first admission used only
   `compiler_controller.request_has_ready_pair`. CGP/ACGP have no compiler
   controller, so every autonomous request was incorrectly classified not-ready
   by that scheduler. Autonomous pair creation also did not wake admission.
3. The hop latency definition includes admission waiting for every strategy.
   Removing that waiting would conceal the problem, not fix it.

Full QAOA/XY/CGP-4: mean latency approximately 4.45 ms versus ODG 2.08 ms; mean admission
waiting approximately 3.501 ms. These are the original uncorrected matrix values.

## Repairs and validation

- Add non-consuming bilateral generic-cache readiness with fidelity checks;
  exclude request-targeted compiler pairs from generic availability.
- Use this readiness for autonomous admission and chain snapshots. Wake
  waiting admission one picosecond after a cached pair is added.
- Keep the existing physical swap/adoption protocol. No instant handoff or
  free memory is introduced for autonomous policies.
- Revise the *study configuration*, explicitly: autonomous cache limit two
  for four physical memories; three for eight. This is not silently presented
  as the original three-of-four configuration. CD remains three-of-four and
  six-of-eight, guarded, longest-chain-priority, now with 1-8 lookback.

On the same initial 100 QAOA layers (448 hops), ODG mean latency was 1.81835 ms.
The old cache-three CGP/ACGP prefix measured approximately 2.24 ms. With the
readiness repair and cache-two setting, CGP and ACGP measured 1.42310 ms,
100% completion and no physical audit violations. This is a screening prefix,
not a full-workload result. Full validation and a fresh 180-case matrix are
required before delivering the revised workbook. Original results are retained.

Run `tools/benchmark_corrected_matrix.py` for the fresh sequential matrix.
Its outputs are isolated in `output/benchmark-matrix-224-readyfix-lookback1-2026-11-04`.
All 180 runs use common simulator source hashes, rather than mixing old/new
autonomous implementations or selecting the faster result per workload.
