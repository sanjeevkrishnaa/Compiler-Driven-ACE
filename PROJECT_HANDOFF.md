# Compiler-Driven ACE: complete project handoff

Last updated: 2026-09-06  
Working branch: `codex/compiler-driven-pregeneration`  
Intended remote: <https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE>

## 1. Purpose and current state

This repository is an ACE/SeQUeNCe research prototype for studying EPR-pair
generation in multi-core quantum architectures. It contains the ACE
implementation of on-demand generation (ODG), continuous generation (CGP), and
adaptive continuous generation (ACGP), plus a new compiler-driven extension
that consumes a complete inter-core communication trace.

The compiler extension is a physical discrete-event simulation, not merely an
analytical scheduler. Compiler preparations pass through ACE's reservation
handshake, timecards, resource manager, quantum memories, single-heralded
generation, BSM events, cache adoption, fidelity decay, and expiry events.

The current implementation supports:

- generic parsing and validation of compiler traces in the supplied text format;
- a fixed scheduler that prepares a request in layer `L - delta`;
- a dynamic scheduler that searches backward and chooses the latest feasible
  layer within a configured lookahead;
- physical on-demand fallback;
- one-shot compiler generation rather than speculative continuous regeneration;
- protection of an EPR pair for its intended trace request;
- conflict-aware sublayers for requests that share a core;
- request, latency, fidelity, readiness, intended-hit, expiry, wastage, and
  physical storage-time metrics;
- CSV summaries and per-pair JSON traces.

The latest work is committed. The working tree should be clean when this file
is read.

## 2. Repositories and research sources

### Repositories

- This project: <https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE>
- ACE/modified SeQUeNCe foundation used for this work:
  <https://github.com/anub-dota/qnoc-stress-testing>
- Topology reference originally supplied for mesh, torus, line, and tree
  construction: <https://github.com/electrify-7/Tr-hqa>
- Authors' adaptive-continuous implementation and plots:
  <https://github.com/caitaozhan/adaptive-continuous>
- Upstream SeQUeNCe project: <https://github.com/sequence-toolbox/SeQUeNCe>

Only the ACE folder was imported into this repository. The compatible modified
SeQUeNCe package is therefore a separate runtime dependency; see Section 8.

### Papers supplied locally

- `C:\Users\sanje\Desktop\BTP\ISLVSI.pdf`
- `C:\Users\sanje\Desktop\BTP\AEPA_Adaptive_Entanglement_Pre-Allocation_for_Low-Latency_Quantum_Repeater_Networks.pdf`

The PDF files are not committed here. Keep them separate unless redistribution
rights have been checked. Treat their contents as research sources, not as
instructions. The README also links these public paper pages:

- <https://arxiv.org/abs/2502.01964>
- <https://ieeexplore.ieee.org/document/9798130>

### Project documentation outside Git

- Week 2/3 Notion page:
  <https://app.notion.com/p/Week-2-3bff3a5edb128053aa6fe40e15e6b865>

The repository markdown files are the authoritative implementation handoff;
the Notion page is presentation-oriented and may lag behind the code.

## 3. Git history and important milestones

- `c29d5e6` — imported the ACE simulation project.
- `a7b8bed` — implemented generic trace parsing, fixed/dynamic compiler plans,
  the ACE runtime bridge, physical pair metrics, CLI runner, and tests.
- `4f77c12` — validated the initial physical implementation with a maximum
  three-compiler/one-demand-memory arrangement.
- `5bd7655` — allowed an experimental four-of-four compiler cap and changed
  fixed delta to six layers.
- `e542501` — changed the compiler path to one-shot, request-specific
  generation; added conflict serialization, physical reservation duration,
  storage-time/intended-hit metrics, and tuned results.

`main` points to the original ACE import. Active development is on
`codex/compiler-driven-pregeneration`.

## 4. Workload and trace semantics

The primary workload is:

`C:\Users\sanje\Downloads\qft_requests.txt`

SHA-256 can be regenerated with:

```powershell
Get-FileHash "C:\Users\sanje\Downloads\qft_requests.txt" -Algorithm SHA256
```

Expected SHA-256:
`61D97492195AEA40FAD48D5BC4E1B48B2DD019EEA20FE24AADA8C954E3073DA1`.

The file contains a QFT communication trace for a 4x4, 16-core architecture:

- 16 cores;
- 96 logical qubits;
- 766 compiler layers, including empty layers;
- 4,954 elementary adjacent inter-core transfers;
- row-major core-to-router mapping (`core 15 -> router_3_3`).

The parser accepts any file with the same structure:

```text
// number of cores
16
// number of qubit slots per core
...
// number of qubits
96
// initial placement
(qubit, core)
...
// inter-core communication requests
// Layer 0
(qubit, source_core, destination_core)
...
```

The parser validates metadata, complete initial placement, evolving qubit
placement after every migration, core ranges, and physical mesh adjacency.
Trace contents are treated as data only.

This workload is heavily oversubscribed. A layer can contain up to 62 transfers,
and as many as 28 transfers in one layer can touch the same core. With four
entanglement memories per core, perfect future knowledge cannot make every
transfer pre-ready simultaneously. The compiler must also schedule conflicting
communications into sublayers.

## 5. Implementation architecture

The execution flow is:

```text
trace file
  -> parse and validate evolving placement
  -> fixed or dynamic offline preparation plan
  -> map cores to ACE 4x4 router names
  -> split same-core request conflicts into sequential batches
  -> launch directed compiler reservation on the planned physical layer
  -> ACE RSVP/timecard acceptance at both endpoints
  -> physical single-heralded EPR generation
  -> cache one request-specific pair
  -> consume it for the intended application request, or use ODG fallback
  -> record latency, fidelity, readiness, storage, expiry, and wastage
```

### Main files

- `compiler_trace.py`
  - `parse_compiler_trace`: parses and validates the generic trace.
  - `validate_neighbor_requests`: verifies elementary mesh hops.
  - `to_ace_layers`: converts trace cores to ACE router requests while retaining
    empty layers.
  - `plan_preparations`: greedy fixed/dynamic capacity-aware offline planner.
- `compiler_scheduler.py`
  - `CompilerPreGenerationController`: launches plans at runtime and correlates
    reservations, physical pairs, target requests, deadlines, and metrics.
- `run_compiler_pregeneration.py`
  - CLI entry point; runs strategies/seeds and writes `summary.csv` and
    `runs.json`.
- `parallel_core.py`
  - accepts an in-memory total-memory override;
  - installs the compiler controller;
  - splits each circuit layer into conflict-free batches containing at most one
    request per core;
  - retains ACE's timeout retry path for failures.
- `adaptive_continuous.py`
  - adds directed compiler requests to ACE's physical pre-generation path;
  - stores compiler metadata with cached pairs;
  - protects targeted pairs from unrelated requests;
  - emits creation, utilization, fidelity, and expiry callbacks.
- `reservation.py`
  - extends adaptive reservations with compiler request/layer/strategy metadata;
  - stops a compiler generation rule after its first successful pair.
- `generation.py`
  - tells cache matching which application request is attempting to consume a
    pair and reports fidelity at utilization.
- `resource_manager.py`
  - associates generated pairs with reservations and reports physical memory
    expiration.
- `test/test_compiler_trace.py`
  - parser, placement, topology, and planning tests.
- `test/test_compiler_one_shot.py`
  - one-shot lifecycle, request protection, and conflict-batching tests.
- `COMPILER_PREGENERATION.md`
  - user-facing model, metrics, command, and current results.

### Fixed and dynamic policies

Fixed policy has one candidate:

```text
generation_layer = target_layer - delta_layers
```

The requested default remains `delta_layers=6`. If that one slot violates
capacity, the preparation is blocked and the request falls back to ODG.

Dynamic policy searches backward from `target_layer - 1` over the configured
lookahead and selects the latest feasible candidate. It normally keeps EPRs
fresher and is the recommended policy for the current trace.

### Why compiler generation is one-shot

The first port reused ACE's continuous reservation lifecycle. If a cached pair
was consumed, its still-active rule generated another pair, and unused pairs
were deleted when the 0.2-second ACE epoch ended. That produced 2,176 pair
instances and 65.35% expiry in the fixed delta-six/four-cap experiment.

The compiler-specific rule now marks its reservation complete after the first
successful physical pair. Returning that memory to `RAW` no longer triggers
another generation attempt. Ordinary CGP/ACGP behavior is unchanged.

### Why four memories cannot all stay occupied by compiler reservations

ACE adopts a cached pair by swapping it into memory already reserved by the
application request. This temporarily requires both the compiler-held memory
and an application memory at each endpoint. If all four timecards are occupied
by compiler reservations, the consuming request can be rejected even though
its EPR exists.

No physical memory index is permanently designated as compiler or demand
memory. The default is a shared pool with a maximum of three simultaneous
compiler reservations, leaving transient handoff/ODG capacity. A four-of-four
cap is still accepted by the CLI for experiments, but it performs poorly with
the current swap-based adoption mechanism.

## 6. Metric definitions

Each strategy/seed row includes:

- `completion_rate`: completed trace requests divided by all trace requests.
- `average_request_latency_ms`: ACE reservation plus generation/service
  latency, excluding the configured pre-generation buffer.
- `average_delivered_epr_fidelity`: fidelity of pairs delivered to applications.
- `scheduled_preparations`: requests admitted by the offline planner.
- `planner_blocked_preparations`: requests rejected before simulation by
  layer/memory/generation limits.
- runtime launched, accepted, rejected, and rejection-event counters.
- `pregenerated_hits`: requests consuming a compiler-generated physical pair
  no later than their first application generation start.
- `pregenerated_success_rate = pregenerated_hits / all trace requests`.
- intended-request hit count/rate: verifies that a pair was used by the request
  it was generated for.
- late compiler uses and true on-demand fallbacks.
- generated, utilized, expired, and remaining compiler pairs.
- `compiler_expiry_percentage = expired / generated * 100`.
- `compiler_waste_percentage = (expired + remaining) / generated * 100`.
- mean fidelity at creation and utilization.
- mean physical storage time from generation to utilization.

`runs.json` additionally records each pair's intended and actual request IDs,
qubit, link, generation/target layer, generation/target-start/utilization/expiry
timestamps, fidelity values, readiness, state, and expiry reason.

The success-rate denominator is every trace transfer, not only planner-admitted
preparations. This is why a resource-constrained but correct scheduler can have
zero expiry and still have a modest readiness percentage.

## 7. Validated physical results

All values below are full 4,954-transfer, seed-0 physical ACE/SeQUeNCe results.
They are not analytical estimates. All configurations completed 100% of the
trace. They are single-seed measurements and must not be presented as a
statistical average.

| Configuration | Mean latency | Reduction vs serialized ODG | Pre-ready | Compiler fidelity at use | Overall delivered fidelity | Expiry |
|---|---:|---:|---:|---:|---:|---:|
| Serialized ODG | 1.1070 ms | — | 0% | — | 0.9498 | 0% |
| Fixed delta=6, cap=3 | 0.9405 ms | 15.04% | 19.46% | 0.4004 | 0.8429 | 4.65% |
| Dynamic/latest feasible, cap=3 | 0.9203 ms | 16.87% | 21.96% | 0.8205 | 0.9214 | 1.81% |
| Dynamic zero-waste, cap=2 | 1.0070 ms | 9.04% | 11.40% | 0.8955 | 0.9436 | **0%** |

Additional interpretation:

- Fixed delta-six used 964 compiler pairs, all for their intended requests. It
  held used pairs for about 635 ms on average, which explains its poor fidelity.
- Balanced dynamic used 1,088 compiler pairs, all for their intended requests,
  and stored them for about 82 ms on average.
- Zero-waste dynamic generated 565 pairs, used all 565 for their intended
  requests, stored them for about 31.7 ms, and expired none.
- Zero expiry is achieved conservatively by reducing compiler admission to two
  simultaneous preparations. It trades readiness and latency improvement for
  resource efficiency and fidelity.
- The balanced dynamic configuration is the best current latency/readiness
  tradeoff; the cap-two dynamic configuration is the clean zero-waste result.

Earlier baseline, before the one-shot/request-protection corrections:

| Configuration | Mean latency | Pre-ready | Fidelity at use | Expiry |
|---|---:|---:|---:|---:|
| ODG | 1.1073 ms | 0% | — | 0% |
| Fixed delta=2, cap=3 | 0.9905 ms | 14.33% | 0.8846 | 69.14% |
| Dynamic lookahead=8, cap=3 | 0.9829 ms | 14.31% | 0.8953 | 69.82% |
| Fixed delta=6, cap=4 | 0.9726 ms | 14.37% | 0.8844 | 65.35% |

Those older compiler results allowed a future-targeted cached pair to be used
by another request on the same link and allowed continuous regeneration. They
are retained only to document why the lifecycle was changed.

Generated output directories are deliberately ignored by Git. On the original
machine, the key artifacts are:

- `output/compiler_qft_serialized_odg_full_seed0/`
- `output/compiler_qft_serialized_full_seed0/`
- `output/compiler_qft_serialized_dynamic_full_seed0/`
- `output/compiler_qft_dynamic_cap2_full_seed0/`

The aggregate rows needed to verify the table are tracked in
`results/compiler_qft_seed0_summary.csv`. Re-run the commands below to
regenerate the complete per-pair JSON artifacts in another checkout.

## 8. Environment setup

The compatible SeQUeNCe implementation currently used is the `SeQUeNCe`
directory inside `anub-dota/qnoc-stress-testing`, not an arbitrary PyPI release.
On the original machine it is located at:

`C:\Users\sanje\Desktop\BTP\repo\qnoc-stress-testing\SeQUeNCe`

Recommended clean setup:

```powershell
git clone https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE.git
git clone https://github.com/anub-dota/qnoc-stress-testing.git

cd qnoc-stress-testing\SeQUeNCe
python -m pip install -r requirements.txt
python -m pip install -e .

cd ..\..\Compiler-Driven-ACE
$env:PYTHONPATH = (Resolve-Path "..\qnoc-stress-testing\SeQUeNCe").Path
```

The SeQUeNCe fork declares Python `>=3.11,<3.14`, although the original machine
also completed these runs under its available Python installation. Prefer
Python 3.11-3.13 for reproducibility.

Important dependencies include NumPy, SciPy, QuTiP, qutip-qip, Matplotlib,
Pandas, NetworkX, and pytest. Use the SeQUeNCe fork's `requirements.txt` as the
source of truth.

## 9. Run commands

Set the runtime dependency for the current PowerShell session:

```powershell
$env:PYTHONPATH = "C:\path\to\qnoc-stress-testing\SeQUeNCe"
```

### Quick physical smoke test

```powershell
python run_compiler_pregeneration.py `
  --trace "C:\path\to\qft_requests.txt" `
  --config config\final_config\grid_4x4_ace_3.json `
  --mesh 4x4 `
  --strategies on-demand,fixed,dynamic `
  --seeds 0 `
  --total-memories 4 `
  --compiler-memories 3 `
  --generation-capacity 3 `
  --delta-layers 6 `
  --dynamic-lookahead-layers 8 `
  --coherence-time-layers 10 `
  --compiler-reservation-ms 1000 `
  --max-layers 60 `
  --stop-time-s 200 `
  --output output\compiler_smoke
```

### Balanced full comparison

Remove `--max-layers` and use `--stop-time-s 300`. For a ten-seed experiment,
set `--seeds 0,1,2,3,4,5,6,7,8,9`; this will take much longer than the seed-0
validation.

### Zero-expiry profile

```powershell
python run_compiler_pregeneration.py `
  --trace "C:\path\to\qft_requests.txt" `
  --config config\final_config\grid_4x4_ace_3.json `
  --mesh 4x4 `
  --strategies dynamic `
  --seeds 0 `
  --total-memories 4 `
  --compiler-memories 2 `
  --generation-capacity 2 `
  --delta-layers 6 `
  --dynamic-lookahead-layers 8 `
  --coherence-time-layers 10 `
  --compiler-reservation-ms 1000 `
  --stop-time-s 300 `
  --output output\compiler_qft_dynamic_cap2_full_seed0
```

Use `--verbose` for ACE event output. Without it, the runner captures the very
large event stream and prints one summary line per strategy/seed.

## 10. Tests

```powershell
$env:PYTHONPATH = "C:\path\to\qnoc-stress-testing\SeQUeNCe"
python -m unittest discover -s test -p "test_compiler*.py" -v
python -m py_compile adaptive_continuous.py reservation.py compiler_scheduler.py compiler_trace.py parallel_core.py run_compiler_pregeneration.py
```

At handoff time, all seven compiler tests pass.

## 11. Known limitations and research cautions

1. Results above use only seed 0. Run multiple seeds and report mean, standard
   deviation, and confidence intervals before comparing formally with a paper.
2. The supplied QFT trace is highly oversubscribed relative to four memories.
   Future knowledge cannot bypass the physical concurrency bound.
3. The planner is greedy in trace order, not a global optimizer.
4. Fixed delta is expressed in circuit layers, while generation, decoherence,
   retry, and reservation events occur in physical simulation time. Congestion
   makes layer-to-time conversion nonuniform.
5. The one-second compiler reservation is a tunable guard window, not a value
   derived from an online completion-time estimator.
6. The application consumes end-to-end entanglement; it does not model the data
   qubit's teleportation gates and classical receiver correction.
7. The current swap-based cache adoption requires transient application memory.
   Supporting four simultaneously held compiler pairs without blocking their
   consumers requires direct reservation/memory ownership handoff.
8. A pair can still fail to generate physically or its RSVP/timecard can be
   rejected. Knowing the request does not guarantee physical success.
9. The exact source-paper tables and plots should be re-extracted from the PDFs
   when writing a publication comparison. Do not claim exact paper reproduction
   solely from trend agreement.
10. `output/` is ignored. Preserve important aggregate results in documentation
    or a deliberately tracked results directory before cleaning a machine.

## 12. Recommended next work

Priority order:

1. Run the balanced and zero-waste dynamic profiles over at least ten seeds;
   compute mean, standard deviation, and confidence intervals.
2. Add a physical-time-aware launch estimator using observed RSVP and EPR
   generation distributions instead of a fixed layer offset/reservation window.
3. Replace the greedy planner with deadline-aware admission and edge-coloring or
   matching-based communication sublayers.
4. Implement direct compiler-to-application reservation ownership transfer so
   a cached pair can be consumed without a second memory at each endpoint.
5. Optimize explicitly for a multi-objective cost: latency, pre-ready rate,
   fidelity at use, and expiry/waste.
6. Add more traces in the same format and evaluate topology/workload sensitivity.
7. Reproduce the source paper's exact topology, workload, arrival process, and
   parameter matrix before making quantitative paper-vs-reproduction claims.

The most important conceptual conclusion so far is that compiler knowledge
solves uncertainty, not capacity. The QFT workload can demand 28 EPR endpoints
at a core in one logical layer, while only four memories exist. Correct
compiler-driven execution must jointly schedule communication and EPR creation;
pre-generation by itself cannot make every request ready.

## 13. Continuation update (2026-09-09)

Development continues on `codex/ace-physical-time-scheduler`. The following
reproducibility infrastructure has been added without changing or replacing the
single-seed results in Section 7:

- an explicit dynamic minimum lead, separate from total lookahead;
- physical setup/generation and layer-duration samples in `runs.json`;
- lead calibration from declared empirical quantiles and safety factor;
- a QFT matrix runner covering ODG, fixed, cap-two/cap-three dynamic, and
  calibrated dynamic over common seeds;
- sample SD and two-sided Student-t 95% intervals;
- seed-paired latency differences and reductions versus ODG;
- trace/config hashes and complete experiment parameters in artifacts.

The handoff URL `https://github.com/anub-dota/qnoc-stress-testing` returned a
GitHub 404 and could not be cloned on the continuation machine. The adjacent
`SeQUeNCe-compiler-native` checkout is a different native-integration project
and was not substituted. Consequently, no new physical result is claimed until
the exact compatible runtime is supplied or access is restored.

The verified GitHub identity requested for future commits and pushes is
`DhruvPansuriya`; the local Git author matches that identity. No public
`Compiler-Driven-ACE` repository was visible under that account, so no
destination remote was invented.
