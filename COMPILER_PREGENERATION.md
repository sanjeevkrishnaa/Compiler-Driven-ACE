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
partition. The runner defaults to four total memories and allows the compiler
to use all four; no memory index is permanently assigned to either strategy.
It applies the total-memory value to an in-memory copy of the selected ACE
configuration and does not rewrite the checked-in topology file. A compiler
cap equal to the total memory count is also supported. In that fully shared
mode, no slot is permanently reserved: an on-demand fallback waits for an ACE
compiler reservation to release and is retried through the existing serialized
retry-layer path.

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
  --total-memories 4 `
  --compiler-memories 4 `
  --generation-capacity 4 `
  --delta-layers 6 `
  --dynamic-lookahead-layers 8 `
  --coherence-time-layers 10 `
  --stop-time-s 200 `
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
| On-demand | 1.1073 ms | — | 0% | — | 0% |
| Fixed, delta=2 | 0.9905 ms | 10.55% | 14.33% | 0.8846 | 69.14% |
| Dynamic, lookahead=8 | 0.9829 ms | 11.23% | 14.31% | 0.8953 | 69.82% |

These are physical ACE results, not an analytical estimate. They use the exact
3+1 maximum allocation and a common 200-second horizon; all strategies complete
100% of the workload. Dynamic generation is later and therefore preserves more
fidelity. Its pre-ready rate is almost identical to fixed in this seed, but the
slightly lower mean latency produces an 11.23% reduction versus on-demand.

The roughly 70% expiry result is also significant: ACE's continuous reservation
keeps attempting generation while a compiler pair waits, and the trace advances
through empty layers in 5 ms steps although memory coherence is 1 ms. The next
scheduler iteration should use physical-time-aware launch windows to avoid
repeatedly regenerating a request-specific pair. A multi-seed study is required
before treating the fixed/dynamic ordering as statistically stable. The complete
seed-0 artifacts are written to
`output/compiler_qft_3plus1_200s_seed0_final/` when the validation command runs.

## Fully shared fixed-delta validation

The requested fixed scheduler now defaults to delta=6 with all four memories
eligible for compiler generation. A full seed-0 execution again completed all
4,954 transfers:

| Configuration | Mean request latency | Reduction vs ODG | Pre-ready success | EPR fidelity at use | Compiler expiry |
|---|---:|---:|---:|---:|---:|
| ODG, 4 memories | 1.1073 ms | — | 0% | — | 0% |
| Fixed delta=2, compiler cap 3 | 0.9905 ms | 10.55% | 14.33% | 0.8846 | 69.14% |
| Fixed delta=6, compiler cap 4 | 0.9726 ms | 12.17% | 14.37% | 0.8844 | 65.35% |

Compared with the earlier fixed 3+1 run, the fully shared result lowers mean
latency by 1.80% and expiry by 3.79 percentage points. It does not reserve an
on-demand memory: a fallback that cannot immediately obtain capacity is placed
on ACE's existing retry path, where each failed request becomes a separate
retry layer. These figures are single-seed physical simulation results, so they
demonstrate integration behavior rather than a statistically averaged claim.
Artifacts are in `output/compiler_qft_delta6_all4_seed0/`.
