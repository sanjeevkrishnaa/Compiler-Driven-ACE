| Configuration | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Chain readiness: full / partial / zero (%) | Hop readiness (%) |
| --- | ---: | ---: | ---: | --- | ---: |
| Original: logical 2-8, 5 ms | 0.7327 | 93.637 | 7.6814 | 72.18 / 11.48 / 16.34 | 77.64 |
| Active 2-16, 10 ns | 1.4285 | 93.403 | 6.4421 | 50.50 / 17.97 / 31.53 | 58.78 |

Same 208-qubit QAOA History trace, 4x4 mesh, T-HQA mapping seed42,
physics seed60, 14 data slots/core, 8 communication memories, compiler quota8,
generation capacity8, execution-first ready-first admission, all-chain hops,
handoff, 50ms reservation lifetime and unchanged physical coherence.

The candidate uses communication-active layers as its planning axis, skips empty
layers when choosing preparation launch layers, and assigns each empty logical
layer 10ns (0.00001ms). Candidate layers are searched nearest first, from two to
sixteen active layers before demand; capacity constraints determine selection.
Planner age cutoff is17 instead of10 to permit a16-layer lead (strict age < cutoff).
This does not change physical coherence or reservation lifetime. Runtime code and
default settings are unchanged; this is a command-line experiment.

Latency is eligibility-to-EPR-delivery per hop, including admission wait. Makespan
uses the same end_to_end_latency_ms metric in both trials. Chain readiness is
sampled at layer opening before admission/preparation. Hop readiness is the
pregenerated hit fraction at individual hop arrival; it uses a different sampling
time and denominator. Fidelity measures delivered EPR pairs, not circuit outputs.
These are single-seed results; the 10ns gap is a timing assumption, not a local
gate simulation. Commands, raw data and source fingerprints are retained.
