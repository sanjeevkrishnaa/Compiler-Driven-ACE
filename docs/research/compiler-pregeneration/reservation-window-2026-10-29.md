# Compiler reservation window, 2026-10-29

The compiler reservation default is now **50 ms**, reduced from 1000 ms. This
bounds an unsuccessful or unused compiler booking without changing physical
memory coherence, preparation lead, compiler quota or the latency clock.
It is a practical default for the tested workloads, not a universal optimum.

A compiler reservation starts at current simulation time plus the topology's
round-trip control delay; its end is start + configured lifetime. Generation can
finish earlier and a ready pair can be consumed immediately. On application
handoff, the compiler lease is replaced and its timeout is cancelled; the same
physical state's age and physical expiry remain intact. An unconsumed compiler
booking reaches its deadline and releases resources. Requests can use the
existing retry/ODG path. There is no added 50 ms delay or latency subtraction.
Application reservations retain their separate settings.

The shared constant is in [`ace/compiler/settings.py`](../../../ace/compiler/settings.py).
Both compiler CLIs, the protocol fallback, full-chain launchers and heavy routing
launcher use it. Override with `--compiler-reservation-ms` for other hardware,
lookahead or workloads. Routing cache reuse rejects a mismatched window.
Metadata fingerprints the settings file.

## Measurement and choice

Complete 96-qubit QFT, Draper QFT adder and QAOA traces ran on a 4x4 mesh with
four communication memories per core, frozen T-HQA mapping seed 42 and XY
routing. Every comparison keeps handoff, all-chain preparation, two-layer lead,
ready-first event admission and zero artificial preparation buffer fixed.
SeQUeNCe is pinned to 0.8.1, commit
`cf5283cdfd6692a82a090d15fb09fbc01bd322fc`.

Profiling consumed pairs in the prior routing evidence (seeds 60–63) found
maximum post-generation ages of 19.60 ms for QFT, 15.10 ms for Draper and 45.00 ms
for QAOA. This profile is conditional on consumption, so it cannot alone prove
that a shorter cap is safe. We replayed workloads at each cap.

Selection: C=4, physics seeds 60 and 61, 30 complete trials. Each row gives the
equal-weight mean of two seeds; deadline expiry pools their pair counts.

| Workload | Window (ms) | Mean latency (ms) | Mean p95 (ms) | Deadline expiry (%) |
| --- | ---: | ---: | ---: | ---: |
| draper_qft_adder | 10 | 0.8665 | 2.400 | 42.976 |
| draper_qft_adder | 20 | 0.5151 | 0.700 | 0.000 |
| draper_qft_adder | 50 | 0.5151 | 0.700 | 0.000 |
| draper_qft_adder | 100 | 0.5151 | 0.700 | 0.000 |
| draper_qft_adder | 1000 | 0.5151 | 0.700 | 0.000 |
| qaoa | 10 | 1.4230 | 4.000 | 54.920 |
| qaoa | 20 | 1.1214 | 3.600 | 5.029 |
| qaoa | 50 | 1.1122 | 3.650 | 0.227 |
| qaoa | 100 | 1.1093 | 3.600 | 0.010 |
| qaoa | 1000 | 1.3765 | 5.200 | 0.091 |
| qft | 10 | 0.9690 | 2.650 | 39.872 |
| qft | 20 | 0.6353 | 1.750 | 0.000 |
| qft | 50 | 0.6353 | 1.750 | 0.000 |
| qft | 100 | 0.6353 | 1.750 | 0.000 |
| qft | 1000 | 0.6353 | 1.750 | 0.000 |

10 ms discards many useful preparations. 20 ms covers QFT/Draper in selection,
but expires about 5% of QAOA pairs. 50 ms reduces QAOA deadline expiry to 0.227%
and closely matches the latency at 100 ms. The maximum reservation-start-to-use
time among consumed pairs in the 1000 ms selection runs was 46.4 ms. A 50 ms cap
covers that observed range while bounding unused leases 20 times sooner.
Exceptionally delayed useful pairs can still expire; the choice is workload-dependent.

`reservation_expired` is separate from the existing `demand_progress` guard,
which evicts future-only pairs to unblock current work. General compiler
expiry/waste includes both. For example, QAOA at 50 ms has 3.519% total expiry in
selection, but only 0.227% deadline expiry. Reservation-start-to-use includes the
application control phase after handoff cancels the compiler timeout, so a used
row may slightly exceed its old compiler lifetime. Pair-ready age and original
booking endpoints are retained in the evidence.

## Fresh-seed confirmation

Seeds 64 and 65 were held out from the choice, comparing 50 and 1000 ms at C=4
and C=3: 24 additional complete trials. C=4:

| Workload | Window (ms) | Mean latency (ms) | Mean p95 (ms) | Deadline expiry (%) |
| --- | ---: | ---: | ---: | ---: |
| draper_qft_adder | 50 | 0.5121 | 0.700 | 0.020 |
| draper_qft_adder | 1000 | 0.5142 | 0.700 | 0.000 |
| qaoa | 50 | 1.0992 | 3.600 | 0.000 |
| qaoa | 1000 | 1.0946 | 3.500 | 0.000 |
| qft | 50 | 0.6407 | 1.750 | 0.016 |
| qft | 1000 | 0.6473 | 1.800 | 0.016 |

C=3:

| Workload | Window (ms) | Mean latency (ms) | Mean p95 (ms) | Deadline expiry (%) |
| --- | ---: | ---: | ---: | ---: |
| draper_qft_adder | 50 | 0.6071 | 1.550 | 0.000 |
| draper_qft_adder | 1000 | 0.6071 | 1.550 | 0.000 |
| qaoa | 50 | 1.0495 | 3.200 | 0.000 |
| qaoa | 1000 | 1.0490 | 3.200 | 0.000 |
| qft | 50 | 0.7462 | 2.200 | 0.019 |
| qft | 1000 | 0.7511 | 2.200 | 0.000 |

QFT and Draper means are unchanged or slightly faster at 50 ms. QAOA's C=4 mean
is 1.0992 versus 1.0946 ms (about 0.42% higher), and its C=3 difference is about
0.05%. These two-seed results support the shorter cap without a material latency
regression; they do not establish statistical equivalence or universal improvement.
Other placements and routing policies were not tested here.

After activating the default, QFT96 seed 6 ran through the full-chain launcher
without a reservation override. Metadata records 50 ms: compiler **0.658701 ms**,
ODG **1.334449 ms**, with 3876/3876 requests complete per strategy. Latency measures
eligibility to EPR delivery; data teleportation is not simulated.

## Verification and reproduction

All **54 window trials plus two default smoke trials** completed and passed
runtime order/ownership audits. All **190 simulator tests** and **19 routing tests**
passed. New regressions check early consumption and release of a blocking unused
compiler booking at its deadline. Coherence time and memory counts did not change.

```powershell
python -B tools/compiler_study/study_reservation_window.py --study output/window-reproduction --phase selection --windows 10,20,50,100,1000 --seeds 60,61 --compiler-memories 4
python -B tools/compiler_study/study_reservation_window.py --study output/window-reproduction --phase validation-c4 --windows 50,1000 --seeds 64,65 --compiler-memories 4
python -B tools/compiler_study/study_reservation_window.py --study output/window-reproduction --phase validation-c3 --windows 50,1000 --seeds 64,65 --compiler-memories 3
python -B tools/compiler_study/summarize_reservation_window.py --study output/window-reproduction
```

Use the pinned dependency on PYTHONPATH and a writable temporary directory. The
runner restores exact XY inputs from frozen routing evidence and checks hashes.
Command files retain the originating machine's paths; regenerate them using the
commands above in a fresh directory.

[Derived rows, aggregates, hold profiles and audits](data/reservation-window-2026-10-29/)
and [raw evidence and sources](../../../results/reservation_window_2026-10-29/README.md)
retain the measurements. The 54 trials used explicit windows and a pre-default
source snapshot; the two final smoke trials verify the activated shared default.
Historical reports used 1000 ms and retain explicit reproduction overrides.
