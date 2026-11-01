# EPR generation time: study plan

Written and committed before any workload sweep of this study ran. Only the link-level checks of
Phase 0 and one reproduction case had been seen. Deviations from this plan are listed at the end of
the report, not silently absorbed.

## Question

What is the EPR generation time in ACE, which parameters change it, and under which conditions
does compiler-directed pre-generation (Dynamic) gain from a slower generation time?

The motivating idea: ODG pays the generation time inside request latency and Dynamic pays it
earlier, so a larger generation time should favour Dynamic. A sweep on 2026-11-01 supported this
only partly and left the cause of the drop at slow generation unmeasured.

## Verified before planning (Phase 0)

Measured on the real stack, not derived:

- An attempt takes exactly 4 classical delays when the hop source has the lower core number and
  exactly 5 when it has the higher one (600 samples each on eight directed links; minimum and maximum
  per-attempt time are equal). Every failed attempt repeats the pairing handshake. The earlier
  statement of "0.4 ms per attempt" was therefore true for only one direction of each link.
- A cache hit takes 2 delays after the window opens, or 3 in the reverse direction.
- `EMPTY_LAYER_GAP_MS = 5` is commented as preserved from the legacy manager. It is not a physical
  value. QFT has 537 empty layers of 766 and QAOA 405 of 733.
- In the QFT base case (M=4, C=3) all 2822 planned pairs were ready in time and all 1011 misses were
  blocked by the planner's memory limit. Preparation took 1.13 ms on average, and the pair then sat
  in memory for 9.10 ms, because a two-layer lead spans two 5 ms gaps.
- `RETRY_PERIOD` and the compiler retry are 1 ms and the compiler and request windows are 50 ms.
  These absolute constants do not scale with the classical delay.

## Hypotheses and how each could fail

| ID | Hypothesis | Falsified if |
| --- | --- | --- |
| H1 | Mean generation time is `(4 or 5) x delay / p`, with `p = rate x (eta_mem x eta_det x fibre)^2`. | Any tested setting differs from the prediction by more than its 95% interval plus 2%. |
| H2 | Only the classical delay and the factors of `p` change generation time. Frequency, coherence, fidelity, dark counts and the gap do not, within the tested ranges. | A knob outside that set moves generation time by more than its interval. Each exception is reported. |
| H3 | Equal `p` from different physical causes gives the same workload result. | Latency or hit rate differs by more than two standard errors between causes. |
| H4 | Hit rate is limited by two separate mechanisms: planner memory at fast generation, and preparation time against slack at slow generation. The second appears when generation time approaches the time from launch to request. | Hit rate at slow generation does not respond to the gap, or misses at fast generation are not planner-blocked. |
| H5 | Absolute saving per hop grows with generation time, and the relative latency gain has an interior maximum. | The relative gain is monotonic across the efficiency grid. |
| H6 | Dynamic's advantage depends on the empty-layer gap: with a short gap, hits and gain fall. | Hit rate and gain are unchanged across the gap grid. |
| H7 | Only ratios of time constants matter: scaling the delay, the gap and the windows together scales latency and leaves hit rate unchanged. | Hit rate moves by more than two standard errors, or latency does not scale within 2%. |
| H8 | A shorter lead shortens storage and lets the planner accept more preparations at fast generation, while a longer lead helps at slow generation. | The best lead does not depend on generation time. |
| H9 | Shorter coherence reduces delivered fidelity and, once it nears the storage time, causes expiries that remove Dynamic's gain. | Fidelity and expiry counts are insensitive to the coherence time. |
| H10 | The gain of `history` over XY grows with generation time. | The gain is flat or shrinking. `history` is the project's chosen route, and greedy and `minhop` are included as a check of that choice. |

## Experiments

Definitions are in `tools/generation_time_study/experiments.py`. Base case: fixed mapping, `history`
route, C = M - 1, lead 2, ready-first, handoff, 50 ms compiler reservation, no extra buffer.

| Name | Varies | Answers |
| --- | --- | --- |
| link | every physical knob, one at a time, 3000 to 9000 samples | H1, H2 |
| efficiency | memory efficiency 1.0 to 0.3 on XY and `history` | H1, H4, H5, H10 |
| delay | classical delay x0.1 to x8 on XY and `history` | H1, H4, H5, H10 |
| equivalence | three causes of one `p` | H3 |
| gap | empty-layer gap 0 to 20 ms against three efficiencies | H4, H6 |
| scale | all time constants together, x0.01 to x2 | H7 |
| chip | fast control with short gaps | H6 and the chip-scale regime |
| memory | M = 2 to 8 with C = M - 1 | memory as a knob |
| lead_gap | lead 1 to 12 against gap and efficiency | H8 |
| tuning | one Dynamic option at a time, 30 options, 12 contexts | which knobs help |
| validation | the best tuning choices on unseen seeds | guards against tuning to noise |
| coherence | coherence 1 s to 1 ms | H9 |
| routes | XY, greedy, `history`, `minhop` | H10 and the route choice |
| workloads | Draper-96, and CDKM-48 and random-48 as different layer structures | generality |

## Statistical rules

- Primary seeds are 60 to 69. Experiments marked in `experiments.py` use 60 to 65.
- Options are chosen on seeds 60 to 63 only. Reported performance of a chosen option comes from
  seeds 100 to 109, which tuning never sees.
- Intervals are 95% Student t over seeds. Seeds measure simulator randomness, not mapping or circuit
  variation; only `workloads` addresses generality, and only weakly.
- Every trial must complete every request and pass the physical audit. A failing case is reported
  as a result and is never dropped.
- Absolute latency constants rest on the 100 us delay and the 5 ms gap, neither of which is a
  chip-scale hardware value, so conclusions are stated in terms of ratios wherever possible.

## Deviations

Recorded when made, before the affected results existed.

1. **Reduced matrix, 2026-11-01 15:45.** The planned 912 cases assumed about 3 minutes per case. On
   this machine (Apple M2, 8 GB, swapping, with the laptop lid sometimes closed) the plan needed 15
   hours or more, so grids and seeds were reduced. No hypothesis was dropped. At that point 45
   cases were finished, all from the efficiency grid at 0.7 or above, and no gap, lead, tuning,
   coherence, route or workload result had been seen. Seed noise on the gains so far was about
   0.4 percentage points, which is why fewer seeds were accepted.

   | Experiment | Planned | Run |
   | --- | --- | --- |
   | efficiency | 10 seeds | 10 seeds at 0.7 and above, 6 seeds below |
   | delay | x0.1, 0.25, 0.5, 2, 3, 5, 8, 10 seeds | x0.1, 0.5, 2, 5, 6 seeds |
   | gap | 8 gaps, both memory sizes, 6 seeds | 7 gaps at M=4, 3 gaps at M=3, 4 seeds |
   | scale | 4 scales, 10 seeds | 3 scales, 4 seeds |
   | chip | 5 gaps, both memory sizes, 6 seeds | 4 gaps, M=4, 4 seeds |
   | memory | M = 2, 3, 4, 5, 6, 8, three efficiencies, 6 seeds | M = 2, 3, 4, 6, 8, two efficiencies, 4 seeds |
   | lead_gap | leads to 12, gaps 0, 0.5, 5 | leads to 8, gaps 0, 5 |
   | tuning | 12 contexts, 30 options | 8 contexts (efficiency 0.95 and 0.4), 27 options |
   | coherence, routes | both memory sizes, 6 seeds | M=4, 4 seeds |
   | workloads | three efficiencies, both memory sizes, 6 seeds | two efficiencies, M=4, 4 seeds |
   | validation | seeds 100 to 109 | seeds 100 to 105 |

2. **Run order changed** to put the decisive experiments first: gap, efficiency, lead_gap, tuning,
   delay, then the rest.

3. **Three link probes stopped early.** Dark counts of 1e6 and 1e8 per second and coherence 0.1 ms
   ran for 15 minutes without finishing 3000 samples. They are rerun with few samples and a time limit.

## Not addressed

Data teleportation, local gate time, and circuit fidelity are not simulated. Delivered EPR fidelity
is reported but no fidelity threshold rejects a pair (the trace default is 0.01), so a pair that
would be useless on hardware still counts as delivered here.
