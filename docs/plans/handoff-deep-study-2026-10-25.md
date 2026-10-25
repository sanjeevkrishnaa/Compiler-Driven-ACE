# Handoff for the deep-study phase (2026-10-25)

For: studying the mapping code and algorithm from the basics and changing it, understanding all of ACE (and SeQUeNCe) to find remaining bugs,
re-examining the latency definition, and improving dynamic pre-generation against on-demand generation (ODG) — all on the **96-qubit plan** of the mid-term.
Everything below was checked in the repository unless it is marked **UNVERIFIED**. Read section 1 first: it changes what the other four tasks should be run on.

Branch `codex/ace-scheduler-correctness` (https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE). Python: `../Compiler-Driven-ACE/.venv/bin/python`.
Full report: `docs/latex/ace_report/ace_report.pdf` (Chapters 12 and 13 are the newest). Earlier handoff: `docs/plans/handoff-2026-10-24.md`.

## 0. The numbers you are working against

| | ODG | Dynamic | Source |
|---|---|---|---|
| QFT, **48 qubits**, 4 memories, corrected scheduler | **1.589 ± 0.046 ms** | **5.566 ± 0.214 ms** | Experiment 1; mean ± sd over 9 runs (3 mapping seeds × 3 physics seeds) |
| QFT, **96 qubits** (the mid-term trace), 4 memories, corrected scheduler | **2.157 ± 0.024 ms** | **9.843 ± 0.025 ms** | `results/qft96_corrected_scheduler_2026-10-25/`; sd over 3 physics seeds, **one trace** |
| QFT, 96 qubits, mid-term report, old (serialized) scheduler | 1.0976 ms | 0.6858 ms (-37.52%) | mid-term PDF, Table 6.2 |

* The 96-qubit run is new (made for this handoff). It has the **same sign** as the 48-qubit result: under the corrected scheduler dynamic is slower than ODG on QFT at four memories, on both traces.
* Two consistency checks that the 96-qubit run reproduces the mid-term's *plan*: dynamic's ready-pair hit rate is 48.57% (mid-term "readiness" 48.56%), and dynamic's generation time is 0.686 ms, which equals the
  mid-term's dynamic "latency" (0.6858 ms). That is, the mid-term's old latency for dynamic was essentially generation time only; the 9.1 ms of waiting for a free memory (ODG: 1.1 ms) was invisible under the old scheduler.
* Delivered fidelity: ODG 0.9498; dynamic 0.9212 (mid-term: 0.9003 with the old scheduler).
* Dynamic's whole-trace time on QFT-96: 14.02 s against 10.03 s for ODG (mid-term old scheduler: -5.9%).

## 1. First decision: what "the 96-qubit plan" is, and what it must be run on

What is known (checked):
* The mid-term used `qft_requests.txt` (copies: `BTP/qft_requests.txt`, `BTP/BTP_Codex_Handoff_2026-08-29/input/qft_requests.txt`; identical; sha256 `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`).
  Header: 16 cores, **8 qubit slots per core, 96 qubits**, 766 layers, 4,954 requests. The handoff archive calls it "the supplied 4x4 QFT compiler trace".
* Its mapping algorithm, circuit and settings are **not recorded anywhere in the repository**. It was supplied; nothing says it came from the vendored mapper. **UNVERIFIED: who produced it, with which placer.**
* The mid-term's ACE configuration (same as ours): 4x4 mesh, `config/final_config/grid_4x4_ace_3.json`, 4 memories per core of which 3 compiler-eligible, delta 6, lookahead 8, coherence 10 layers,
  compiler reservation 1000 ms, 5.3 ms lead, 50 ms request duration, ACE physical parameters. The 96-qubit rerun above used exactly these.
* Our ten-benchmark study (Experiments 1 and 2, the heatmaps, the torus, the routing study) is a **different workload**: MQT Bench circuits at **48 qubits**, mapped by the vendored mapper
  (`mapper/`, HQA placer with OEE initial placement, seeds 42-44; `results/congestion/mqt_ten_workload_congestion_results.zip`, `study.json`). Its architecture (from `study.json`) has 128 physical slots (16 cores x 8), of which per core 4 are communication slots and 4 data slots,
  with 1 spare data slot per core, hence `initial_workload_capacity = 48 = 16 x (4 - 1)`.
  The 96-qubit trace has 8 *qubit* slots per core, so it was made under a different slot assumption (96 = 16 x 6). **UNVERIFIED** which one the supervisor intends.

What to do (suggested order):
1. Ask whoever supplied `qft_requests.txt` for the placer, the circuit generator and the slot assumption. Record the answer in `mapper/PROVENANCE.md`.
2. Try to **reproduce `qft_requests.txt` byte for byte** with the vendored mapper (`tools/congestion_study/run_study.py` has `--total-qubits`, `--memory-slots`, `--on-demand-reserve`, `--spare-data-slots-per-core`,
   `--logical-qubits`, `--placer`, `--initial-placement`, `--circuit-seed`, `--optimization-level`; the mid-term trace probably needs `--logical-qubits 96`). **UNVERIFIED that it can be reproduced.** If it can, that fixes the
   algorithm and settings for everything that follows. If not, treat the supplied file as the fixed input and say so.
3. Decide the rule for all later experiments: *same trace, same mapper settings, same ACE configuration, same seeds, same physical parameters*. The repository's own rule (do not silently change benchmark, mapping, seed,
   transpilation or physics parameters) already says this; the open point is only that Experiments 1 and 2 used 48 qubits and must be rerun at 96 if 96 is the plan.
4. To rerun at 96 qubits: map the ten benchmarks at 96 qubits, then run Experiment 1 (`tools/experiment1/run_experiment1.py --traces-dir <dir>`, as the torus run does) and the four-policy comparison
   (`tools/experiment1/four_policies.py`). The QFT-96 trace is already in the right format (`run_trace_comparison.py --trace`).

## 2. Study track A: the mapping code and algorithm, from the basics

Where: `mapper/` (verbatim copy, 49 files hash-verified against the original; `mapper/PROVENANCE.md`). Algorithm table: `mapper/README.md`. Entry point: `python -m qmap run --grid 4x4 --benchmark qft`.
The papers in `/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/` that concern the project: `Wu_2021_Quantum_Sci._Technol._6_045027.pdf` (quantum-circuit mapping reference; **UNVERIFIED** it is the HQA paper — its first page
carries no title text), `2607.14592v1.pdf` (Adaptive Entanglement Management in Quantum Multi-Core Architectures — the group's paper), `Decentralized_Framework_for_Teleportation_in_Quantum_Core_Interconnects.pdf`.

Suggested reading order and what to understand at each step:
1. `qmap/circuit/` (`ir.py`, `loader.py`, `slicer.py`, `generators.py`): how a circuit becomes time slices of two-qubit operations. Exercise: slice a 4-qubit QFT by hand.
2. `qmap/architecture/` (`topology.py`, `core.py`, `reliability.py`, `architecture.py`): cores, capacity, distance, **shortest-path routing** (this is where Dijkstra lives; the torus is a topology option here).
3. `qmap/placement/base.py`, `cost.py`, `assignment.py` (Hungarian matching), `attraction.py`: how a slice's placement is chosen.
4. `qmap/placement/HQA.py`, then `T_HQA.py`, `TR_HQA.py`, `T_HQAR.py`, `GTR_QA.py`: the variants differ in the placement cost and the path billed (table in the README).
5. `qmap/placement/initial.py` and `oee.py`: the initial placement (OEE) that seeds slice 0.
6. `qmap/io/traces.py`, `requests.py`: how a placement sequence becomes the request trace ACE consumes (a qubit moving several cores becomes a chain of adjacent hops).
   This is the link between the mapper and everything downstream: **the own-versus-relay classification and the per-qubit chains in ACE are reconstructed from this format**.
7. `tools/congestion_study/run_study.py` (the pipeline around the mapper) and `tools/congestion_study/hotspot_analysis.py`.

Checks that tell you whether you understood it: reproduce one archived trace file exactly (`mapper/PROVENANCE.md` documents how all 420 were reproduced); hand-derive the chain of hops for one multi-hop move and compare with
`requests.txt`; change one cost term and predict which requests change.
Candidates for the "changes in it" (none tested): placement cost aware of congestion (not only distance); capacity-aware routing of multi-hop moves (the offline-routing study, Chapter 9 of the report, bounds what it could gain:
excess demand -84% on the mesh at four memories); the torus (already supported).

## 3. Study track B: all of ACE, then SeQUeNCe, to find remaining bugs

Map of what was read and verified in this session (file:line refer to this commit):
* `request_scheduler.py`: per-qubit request manager. `_activate_layer` 151-158 (launches the compiler's preparations of that layer), `_free_memories` 209, `_try_admit` 232-255 (admission needs a card with no overlapping booking),
  `get_individual_latencies_breakdown` (wait split). Written in this work.
* `compiler_trace.py` / `compiler_scheduler.py`: the planner (`plan_preparations`, `_candidate_layers` 242-255) and the runtime controller (`on_original_layer` 66, retry every 1 ms on rejection, 113-120).
* `adaptive_continuous.py`: the autonomous CGP/ACGP protocol: `start` 147-178, `request_compiler_pair` 192-236 (same quota counter), `select_neighbor` 262, `update_probability_table` 404-447, `match_generated_entanglement_pair` 491-547.
* `generation.py`: how a request uses a ready pair: 265-343 (**swap into the request's own memory, then release the pair's memory**). Note that the file contains **two near-identical protocol classes** (compare lines 221-296 with 774-856).
* `reservation.py`: reservation identity (`ApplicationReservation`, written in this work), `release_reservation` 434, `release_consumed_compiler_memory` 473, autonomous expiry 559-581.
* `node.py:57`: the autonomous protocol's period is 2e11 ps = 0.2 s.
* SeQUeNCe v0.8.1 at `/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/SeQUeNCe-0.8.1/` (the one ACE imports): `kernel/timeline.py` (event loop; `stop` only sets `stop_time`), memory, BSM, generation, resource manager, reservation protocol.
* Correctness tooling to use while reading: `tools/ace_correctness/` (baseline, audit, harness with microcases), `invariants.py` and `execution_events.py` (event log + invariant checker), `tools/diagnostics/occupancy.py`
  (records bookings, wait causes, hold times, admission blocking per run). Earlier audit: `docs/reports/ace-correctness-audit.md` (findings F1-F10, all fixed or documented).

**Candidate bugs and oddities to check first** (all **UNVERIFIED** as bugs; each has evidence that makes it worth a look):
1. *Accepted autonomous reservations are never released from the memory timecards.* In one CGP run the event log shows 19,922 bookings released within 0.2 ms (rejected handshakes) and 1,672 accepted ones with no release event.
   If they stay in `card.reservations` forever, every later overlap scan grows (CGP/ACGP runs on the random circuit take over an hour). Check `len(card.reservations)` over time.
2. `num_unused_entanglement_pairs` (`adaptive_continuous.py:377`) is incremented for every released memory; in one run 20 of 1,626 releases had no cached pair. It also misses pairs still cached at the end. Use (generated - used) / generated.
3. `adaptive_continuous.py:166` comment says "the 'period' is one second"; ACE passes 0.2 s (`node.py:57`). `round_to_period` floors.
4. The name `retry_wait_time_ms` in the breakdown includes the wait for admission, not only retries.
5. The planner's `dynamic_lookahead_layers` never changes the schedule (checked: identical in 210 configurations, `results/diagnostics_dynamic_vs_odg_2026-10-24/lookahead_check.txt`). Is that the intended semantics of "latest feasible layer"?
6. A request with a ready pair still takes a free memory of its own (the swap). Is this the paper's design (arXiv 2502.01964) or an artefact? If artefact, it is the largest single lever in section 5.
7. Delivered fidelity of ODG is 0.9498 in every run. Check what the formula includes (gate and measurement fidelity 0.99, detector 0.95, memory fidelity 0.95).
8. In SeQUeNCe: events at equal times run in unspecified order (ACE works around it with a 1 ps grace); `Reservation.__eq__` ignored identity (fixed in ACE by a subclass, not upstream); the memory cut-off (`cutoff_ratio`) exists but is unset in ACE
   (`docs/reports/memory-cutoff-study.md`).

## 4. The latency definition

Current definition (`latency_metrics.py`, column `average_eligible_latency_ms`): for each completed request, completion time minus the time it became eligible minus the 5.3 ms lead. Eligible = the start of its layer for a first hop,
the completion of the previous hop for a later hop of the same qubit's chain. It therefore **includes** waiting for a free memory, the reservation messages' classical delay and generation; it **excludes** the wait for earlier hops of
the chain and for earlier layers (those are `dependency_wait`), and the 5.3 ms lead. Definition and tests: Chapter 5 of the report, `test/test_latency_metrics.py`.

Questions to settle before improving dynamic (each changes the headline):
* It is **per hop**, not per route or per qubit move. Is per-hop the right unit for the claim "pre-generation reduces latency"?
* It excludes the dependency wait, which is longer under dynamic (QFT, 4 memories: 12.5 ms against 7.7 ms for ODG, mapping seed 42): the compiler's choices change when hops become eligible. A per-route or per-layer measure would include it.
* The old (serialized) latency counted a request from its batch's submission and gave dynamic a 41% gain on QFT-48; the common definition gives -250%. Which definition does the mid-term's 37.52% belong to? (The old one: dynamic's number is essentially its generation time.)
* Candidates: per-route completion time; per-layer duration; whole-trace time (QFT-96: 14.02 s dynamic against 10.03 s ODG); tail latency (p95); time to first pair. `tools/diagnostics/` already records per-request wait, hold and hit data.
* Whatever is chosen, keep one definition valid for every scheduler and policy, and never compare ACE milliseconds with the native SeQUeNCe backend's.

## 5. Improving dynamic against ODG

Why dynamic is slower (full account: Chapter 12 of the report, `docs/reports/dynamic-vs-odg-diagnosis.md`; mechanism read in the code and measured):
the extra latency is waiting for a free memory, not generation (QFT-48, 4 memories: generation 1.13 ms ODG, 0.65 ms dynamic; wait 0.44 ms against 4.81 ms). Prepared pairs hold memory cards about 24 ms against about 6 ms for
an ordinary request; a request with a ready pair still needs its own card; the pair of a later hop of a chain is made at the start of the previous layer but used only after the hop before it completes.
What did **not** matter: request duration, compiler reservation window, generation capacity, planner lookahead. What did: the number of memories the compiler may hold (cap 1/2/3 of 4: 1.88/2.77/5.46 ms; ODG 1.57 ms, mapping seed 42).
Preparing pairs only for first hops: 1.89 ms (an isolation experiment, not a policy).

Candidate directions (**none implemented or tested; no algorithm is proposed here**):
1. *Per-hop just-in-time preparation*: prepare the pair of hop k when hop k-1 is about to complete, not at the previous layer's start (needs the controller to react to completions).
2. *Use the cached memory as the request's memory* so a hit needs one card, not two (changes the swap in `generation.py`; check physical validity first — section 3 item 6).
3. *Benefit-aware planning*: a ready pair saves about 0.9 ms of generation but costs about 24 ms of card time; prepare only where cards are free (the planner currently checks only compiler memory, not requests' needs).
4. *Admission priority*: let requests pre-empt unready preparations, or prefer requests that have a ready pair.
5. *Cap tuning per workload and memory count* (the cap sweep shows the compiler cap is the strongest lever).
Success test: on QFT at four memories, dynamic should reach ODG's latency (1.589 ms on the 48-qubit trace, 2.157 ms on the 96-qubit trace) or better with 0% waste, and keep its advantage on the benchmarks where it already wins
(GHZ, Bernstein-Vazirani, BMW, CDKM adder, VQE). Compare on all nine (or ten) benchmarks and both topologies before claiming anything, with paired seeds.

## 6. Rules in force

Never compare raw ACE ms with native SeQUeNCe ms; compare policies only within a backend; never merge legacy and corrected tables; do not claim congestion-aware routing is complete or successful; do not call structural (trace) results
physical; do not silently change benchmark, mapping, seed, transpilation or physical parameters; do not drop requests (a fallback is not a failure); use paired seeds; invariants: exact request-pair identity, single consumption,
no provenance corruption, every request accounted for. Do not touch the uncommitted `BTP_REPORT_SOURCE.tex` in the main checkout or reset `codex/strict-compiler-4plus0`.
Commit headings are meaningful: `[heading] - description`. Physical parameters remain an open decision (`docs/reports/ace-physical-parameters.md`).

## 7. Quick reference

```
PY=../Compiler-Driven-ACE/.venv/bin/python
$PY -B -m unittest discover -s test -p 'test_*.py'                       # 149 tests
$PY -B tools/ace_correctness/baseline.py check --golden results/ace_correctness_baseline_2026-10-24/legacy \
    --strict --external "qft96=/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/qft_requests.txt"   # 164 rows, must pass
# one run on a trace (corrected scheduler), as used for QFT-96
$PY -B run_trace_comparison.py --trace results/qft96_corrected_scheduler_2026-10-25/qft96_requests.txt --mesh 4x4 \
    --strategies on-demand,dynamic --seeds 0,1,2 --total-memories 4 --compiler-memories 3 --generation-capacity 3 \
    --delta-layers 6 --dynamic-lookahead-layers 8 --coherence-time-layers 10 --compiler-reservation-ms 1000 \
    --stop-time-s 300 --scheduler per-qubit --output out/run
# why-slow diagnostics for any run: tools/diagnostics/occupancy.py (see its docstring); batch: tools/diagnostics/run_diagnostics.py
```
Results: `results/experiment1_*` (ODG, dynamic; CGP, ACGP), `results/experiment1_four_policies_*`, `results/diagnostics_dynamic_vs_odg_2026-10-24`, `results/qft96_corrected_scheduler_2026-10-25`.
Unfinished: CGP/ACGP on the random circuit (set aside; large-memory runs take over an hour each); the 96-qubit reruns of the ten benchmarks; a 96-qubit mapped version of the other nine circuits (does not exist yet).
