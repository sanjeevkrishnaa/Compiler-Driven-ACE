# After the mapping work: what remains, how, and what the literature says

Written 2026-10-25. Status labels: **done** (verified in this repository), **running**, **ready** (tooling written, not run),
**open** (needs a decision or a design). Nothing here is a result unless it says so.

## 0. Goal

Make Dynamic compiler-driven pre-generation beat on-demand generation (ODG) on the fair metrics, on QFT-96 first. Current reference
(`results/qft96_physical_per_qubit_30seed_2026-10-25`, 30 physics seeds, mean ± sd):

| | ODG | Dynamic |
|---|---|---|
| fair request latency (arrival → delivery) | 1.5256 ± 0.0160 ms | 2.5701 ± 0.0960 ms |
| admission wait | 0.200 ms | 1.638 ms |
| generation / service | 1.125 ms | 0.732 ms |
| makespan | 4.337 s | 4.694 s |
| delivered fidelity | 0.9498 | 0.9430 |

Dynamic generates faster (0.73 vs 1.13 ms) and loses on waiting for a free memory. Every improvement below attacks that wait.

## 1. Metric contract (fixed before any further experiment)

Headline: request arrival (eligibility) → EPR delivery, queueing and RSVP control delay included, cached-pair storage before the request
excluded. Always reported with: median, p95, max; admission wait; generation/service; makespan; throughput; EPR hit rate; EPR waste and
expiry; storage time; fidelity at creation, at use and delivered; memory occupancy. Why both a per-request and a whole-trace number: with
parallel requests a request-level mean can improve while the whole trace gets longer (dynamic today), and eligibility-based timing starts a
later request's clock only when its predecessors finish, so delays that push later layers back do not show in the per-request mean
(the coordinated-omission pattern; Sources 1–3).

## 2. Workstreams, in order

### A. Routing study on QFT-96 (steps 1–5 of the plan)
- **done** Placement recovery and contract exporter (commit f426699): the mapper's own partition is in `mapping.npz` for the 30 archived 48-qubit traces;
  replay of any hop trace reproduces it (30/30). QFT-96 replays to 1,770 migrations / 4,954 hops.
- **done** Four policy traces for QFT-96 validated (replay equals contract). `max_reliability` takes 5,070 hops (confounded by length).
- **running** 5 arms (supplied file as control, xy, yx, shortest_reliable, max_reliability) × ODG/dynamic × 30 seeds, then `compare_routing.py`.
  The control arm must reproduce 1.5256 / 2.5701 ms to the last digit; if it does not, nothing else from the run is trusted.
- **running** Memory occupancy per arm on seeds 0–2 (`tools/diagnostics/occupancy.py`; 3 of 5 arms already written).
- **Decision rule (written now, before seeing the data):** an arm "reduces Dynamic congestion" only if its dynamic admission wait and dynamic−ODG latency
  gap are lower than the control's by more than the Welch 95% interval, and the makespan does not get worse. A difference inside the interval is "no effect".
- **Caveat that stays in every table:** QFT-96's reliability map is synthetic (the mapper's is unavailable), so `shortest_reliable` and `max_reliability` there are
  not the supplied routes (825 of 1,770 routes equal the supplied file). XY/YX do not depend on it.

### B. More routing arms (open — design needed)
- **O1TURN-style** (Seo et al., ISCA 2005, Source 7): per migration pick XY or YX with a seeded coin. Cheap, same hop count, spreads relay load. Arm name `o1turn`.
- **Congestion-aware, offline:** `tools/routing_research` earlier found an exact per-layer optimum cutting excess load 66–89% at capacity 4 and simulated latency −25% (QFT)
  on the OLD 48-qubit setup. It must be re-expressed as a policy that reads the placement contract and writes `migrations.jsonl`, with its objective and the
  information it uses written down (the rebuild plan requires this), then rerun on the corrected timing. Never used as a baseline until documented.
- Literature note: plain dimension-order routing has no load balancing; oblivious XY/YX mixing and centralised XY-or-YX selection per source–destination pair are the
  standard cheap improvements; adaptive routing needs runtime load (Source 7). Our routing is offline and centralised, which matches the centralised variant.

### C. Dynamic parameter sweep (step 6) — **ready**
`tools/dynamic_sweep/run_sweep.py` (dry run tested: 26 points). One factor at a time around the baseline of the 30-seed run; ODG as the reference.
What each parameter does, from the code:

| parameter | what it controls | expectation (to be tested, not assumed) |
|---|---|---|
| compiler-memories | planner cap on cards held for pre-generation per core and layer | strong: earlier diagnosis, 3→1 of 4 cut latency 5.46→1.88 ms (old settings) |
| total-memories | communication qubits per core (4 in the group's Table I) | strong; 6, 8 are counterfactual |
| generation-capacity | preparations a core may start per layer | none (earlier: no effect) |
| dynamic-lookahead-layers | how far back the planner may place a preparation | none: the planner tries layer L−1 first, which is almost always free |
| delta-layers | used only by `fixed` (prepare exactly delta layers ahead) | meaningless for `dynamic`; swept on `fixed` |
| coherence-time-layers | the PLANNER's window (preparations older than this are not planned; hold length cap), not the memory's physical coherence | unknown |
| admission (event/poll), starvation guard | how the per-qubit scheduler picks waiting requests | unknown |

Plan: screening with 5 seeds per point on the control route and on the best route arm from A; the points that move the metric beyond the seed spread are rerun with
30 seeds. A first 2-D grid of compiler-memories × total-memories because those two interact. No claim from a screening point alone.

### D. Improving the Dynamic algorithm (the research contribution — **open**)
Diagnosis already established (old settings, `docs/reports/dynamic-vs-odg-diagnosis.md`): pre-generated pairs hold a card about 24 ms vs about 6 ms for an ordinary request;
a request served from a ready pair still needs a free card (the pair is swapped into the request's slot); and later hops of a chain wait longest
(pair held 11.9 / 23.7 / 39.2 ms for first / second / third-or-later hop). Candidate fixes, each tied to a cause, with what the literature offers:

1. **Chain-position-aware, just-in-time preparation.** Prepare hop k when hop k−1 starts or is about to finish, not one layer before. Closest literature:
   SwitchQNet's compiler uses lookahead over upcoming communication and buffer capacity to decide when to generate pairs, parking them in reserved buffer qubits,
   and ties early generation to fidelity loss (Source 4). The UNIQ formulation tracks a pair's occupancy of communication qubits from generation to consumption (Source 5).
   Measure first: how much of the 9 ms (old) wait comes from third-or-later hops.
2. **Cap by demand, not by constant.** Compiler memories per core chosen from the trace's per-core demand curve instead of 3 of 4 everywhere. The only knob with a strong effect so far.
3. **Admission priority.** Serve requests that already have a ready pair first; stop ordinary requests being starved by cached pairs of other requests.
4. **Age-based discard / eviction.** Free a card held by a cached pair when a waiting request cannot be admitted; cutoff and discard-oldest policies are well studied in repeater chains and trade rate
   against fidelity (Source 6). ACE already has a cutoff ratio (earlier cut-off study); the open point is eviction on demand.
5. **Consume-in-place.** Let a request use its ready pair without a second card. ACE's paper describes the swap into the request's slot as its design (§IV-C7), so changing it is a
   modelling decision for the group, not a bug fix.
6. **Online replanning** using the actual state instead of the offline layer plan (the RL compiler line, Source 4b). Largest effort; only if 1–4 are insufficient.
Each candidate is evaluated against the same fixed baselines, on the same 30 seeds, and reported even when it does not help.

### E. Rigour items still open from earlier sessions
- Rerun the **ten benchmarks** at **96 qubits** (Experiments 1 and 2 were 48 and on the old latency definition). Needs the mapper at 96 qubits with the group's slot rule (2 free slots per core — unconfirmed).
- **Independent mappings:** placements are identical across mapping seeds 42/43/44 (checked on 4 of 10 workloads), so "3 mapping seeds" are route variants. For independent mappings vary the circuit seed or the initial placement,
  or use a different placer; otherwise report one placement and the physics seeds only.
- **Physical parameters** (ACE 1 s / 0.95 vs the ACGP paper 1 ms / 0.85): with 1 ms every cached pair expires. Everything about pre-generation depends on this.
- **Hop-by-hop teleportation:** teleport time per hop is not modelled (latency is EPR delivery); relay computation-slot occupancy is out of the current scope but hop-by-hop puts the qubit in each relay.
- **QFT-96 provenance:** who produced `qft_requests.txt`, with which placer and reliability map; can the mapper reproduce it byte for byte.
- **Classical delay constants** (100 µs end processing, 20 µs per hop) are metro-network values that set the millisecond timescale on a chip.
- Control arm and baseline regression after any ACE source change (`tools/ace_correctness/baseline.py check`).

### F. Logging and reproducibility
Every run directory keeps `summary.csv`, `metadata.json` and the exact command; each step is committed as `[abisfa] - …` and appended to `docs/worklog/README.md`;
anything not verified is marked UNVERIFIED in the text. No ACE source is edited while a run uses the working tree.

## 3. Decisions needed from the group
1. Is consume-in-place (D5) in scope, or is the swap into the request's own card fixed?
2. Is the offline congestion-aware route (B) allowed to use the whole trace (future information), or only the layers already released?
3. Which physical parameter set is canonical (E)?
4. Independent mappings: change the placer/seed, or accept one placement?

## Sources
1. Coordinated omission and response vs service time: https://www.scylladb.com/2021/04/22/on-coordinated-omission/ ; open vs closed workloads: https://brooker.co.za/blog/2023/05/10/open-closed/
2. Quantum-network latency definitions: https://arxiv.org/html/2610.26900 ; https://arxiv.org/pdf/2212.08806 ; https://arxiv.org/pdf/2502.01964 ; busy time vs queueing: https://arxiv.org/html/2409.07049
3. Distributed-QC compilers measure depth/total latency; teleportation serialisation: https://arxiv.org/html/2605.21795v2 ; buffering: https://arxiv.org/html/2503.18329v1
4. SwitchQNet (lookahead EPR generation, reserved buffers): https://dl.acm.org/doi/10.1145/3695053.3731046 ; 4b. RL compiler: https://arxiv.org/pdf/2404.17077
5. UNIQ (pair occupancy of communication qubits): https://arxiv.org/pdf/2512.00401 ; network-aware scheduling: https://arxiv.org/pdf/2504.20176 ; EPR prefetch: https://arxiv.org/html/2509.02827
6. Cutoff and discard policies: https://www.nature.com/articles/s41534-023-00713-9 ; https://arxiv.org/html/2207.06533 ; https://arxiv.org/html/2607.24557
7. O1TURN and XY/YX load balancing: https://www.csl.cornell.edu/courses/ece5970/rguides/seo-o1turn-isca2005.html ; https://people.csail.mit.edu/devadas/pubs/prom.pdf ; https://kolodny.net.technion.ac.il/files/2016/07/Centralized-Adaptive-Routing-for-NoCs.pdf

Search coverage: the searches returned abstract-level summaries only; I did not open the papers, so the mapping of ideas to our setting above is my reading, not a claim from them.
No search result gave a ready decoherence-aware lookahead rule or a request-aware scheduling queue for this setting.
