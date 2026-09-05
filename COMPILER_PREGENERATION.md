# Compiler-driven entanglement pre-generation on ACE

This extension consumes the complete inter-core movement trace emitted by a
compiler. It uses that advance knowledge to launch directed EPR generation on
the exact physical neighbor link that a future transfer will use.

The implementation does **not** replace ACE with an analytical latency model.
Every planned preparation follows ACE's existing path: adaptive reservation
handshake, RSVP timecards, resource-manager rules, single-heralded physical
generation and BSM events, quantum memories, decoherence, and cached-memory
adoption by the later application reservation.

## Scheduling strategies

- `on-demand`: no compiler preparations; all requests use ACE's ordinary
  demand-generation path.
- `fixed`: a transfer in layer `L` is planned at layer `L - delta`.
- `dynamic`: searches backwards from `L - 1` within the configured lookahead
  and chooses the latest layer satisfying per-core generation and held-memory
  limits. Requests that cannot be scheduled fall back to on-demand generation.

The compiler memory value is a maximum shared quota, not a permanently indexed
partition. With ACE's current eight-memory topology and
`--compiler-memories 3`, at most three memories per router may be occupied by
compiler preparations; at least five remain available to demand reservations.
The runner rejects a quota that leaves no on-demand memory.

## Metrics

`summary.csv` records, per strategy and seed:

- request completion rate and ACE request latency;
- `pregenerated_success_rate`: fraction of all trace requests that consumed a
  physical compiler-generated EPR pair created no later than that request's
  scheduled inter-core start time;
- requests served late by a compiler pair, true on-demand fallbacks, and
  planner/runtime preparation failures;
- EPR fidelity when generated and again at utilization;
- generated, utilized, expired, and remaining compiler pairs;
- `compiler_expiry_percentage = expired / generated * 100`;
- `compiler_waste_percentage = (expired + remaining) / generated * 100`.

`runs.json` contains the offline schedule, rejection reasons, and one row for
every generated compiler pair. Its per-pair trace includes intended and actual
request IDs, qubit and link, generation/target layers, physical timestamps,
creation/utilization fidelity, pre-ready status, and expiry reason.

ACE still defines request completion as delivery of the requested end-to-end
entanglement to the application. It does not execute a data-qubit teleportation
or receiver correction.

## Running the supplied 4x4 QFT trace

The original ACE repository expects its SeQUeNCe fork to be installed in the
active environment. From the `ACE` directory:

```powershell
python run_compiler_pregeneration.py `
  --trace "C:\Users\sanje\Downloads\qft_requests.txt" `
  --config config\final_config\grid_4x4_ace_3.json `
  --mesh 4x4 `
  --strategies on-demand,fixed,dynamic `
  --compiler-memories 3 `
  --generation-capacity 3 `
  --delta-layers 2 `
  --dynamic-lookahead-layers 8 `
  --coherence-time-layers 10 `
  --seeds 0,1,2,3,4,5,6,7,8,9 `
  --output output\compiler_qft_10seed
```

Use `--max-layers 40` for a short integration smoke test and `--verbose` to
show ACE's event-level request output.

Empty compiler layers are retained. Core identifiers are converted to ACE's
row-major router names (`core 15` on a 4x4 mesh becomes `router_3_3`), and each
trace transfer must be an adjacent physical mesh hop. The parser also verifies
every migration against the evolving qubit placement.

## Initial physical validation

One full seed-0 execution of the supplied trace completed all 4,954 transfers:

| Strategy | Mean request latency | Reduction vs ODG | Pre-ready success | EPR fidelity at use | Compiler expiry |
|---|---:|---:|---:|---:|---:|
| On-demand | 1.1078 ms | — | 0% | — | 0% |
| Fixed, delta=2 | 0.7346 ms | 33.68% | 38.15% | 0.8993 | 47.84% |
| Dynamic, lookahead=8 | 0.7499 ms | 32.30% | 36.66% | 0.9063 | 49.04% |

These are physical ACE results, not an analytical estimate. Dynamic generation
is later and therefore preserves more fidelity, but in this seed it encounters
more runtime timecard contention and has a slightly lower pre-ready rate than
fixed scheduling. A multi-seed study is required before treating that ordering
as statistically stable. The complete seed-0 artifacts are written to
`output/compiler_qft_seed0_final/` when the validation command is run.
