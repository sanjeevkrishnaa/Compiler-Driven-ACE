# Work log: mapping, ACE correctness, routing

A running log kept step by step, newest entries at the bottom of each date. Each fact is marked
**checked** (read in code/paper or reproduced) or **UNVERIFIED**.

Program order (agreed 2026-10-25):
1. Mapping and routing: understand and fix the mapper; trace format `(qubit, source core, destination core)`;
   routing as a separate, swappable step (XY, the mapper's routing, others); one canonical trace set for all benchmarks.
2. ACE correctness from the code: time units (ms vs. coherence in µs), redo the week-2 reproduction from scratch.
3. Hundreds of experiments on the trusted pipeline.
4. Routing studies: torus + Dijkstra, congestion vs. routing strategy, SeQUeNCe path selection.
5. Application-specific routing (Palesi et al., IEEE TPDS 20(3), 2009), then the full pipeline.

---

## 2026-10-25

### Mapper source and the mid-term trace (checked)
- `~/Downloads/codebase.zip` (`3jeev/`) holds the same `qmap/` package as `mapper/` in this repo: `diff -rq` finds no
  differences. The zip adds `generate.py`, `Makefile` and `tests/`.
- The README command
  `python generate.py --benchmark qft --initial-placement oee --cores 16 --reliability-min 0.1 --reliability-max 1.0 --seed 42`
  (qiskit 2.5.2, numpy 2.5.1, scipy 1.18.0, networkx 3.6.1, Python 3.14) reproduces the mid-term `qft_requests.txt`:
  4,954 hop requests, 766 layers, identical except 20 lines. Those are two 5-hop moves (q93 13→3 and q80 3→13) where a
  different path of equal length was chosen.
- **The trace is not XY-routed**, although the reports say so. The mapper takes a shortest-hop path and breaks ties by
  link reliability, and link reliabilities are drawn at random from U[0.1, 1.0]. Some routes go X-first, others Y-first.
  The two differing moves are reliability-tie-break flips. **UNVERIFIED:** why the tie-break flips between runs (float
  near-tie or a library difference).

### Decision: 96 qubits (checked against the papers)
Each core has **8 computation qubits + 4 communication qubits, as separate qubits** (12 per core):
- Group's paper `2607.14592v1.pdf`, Table I: "Computation Qubits per core 8", "Communication Qubits per core 4";
  Section IV: "Each core contains 8 computation qubits and 4 communication qubits … total number of computational
  qubits is therefore m×n×8".
- `Decentralized_Framework_for_Teleportation_in_Quantum_Core_Interconnects.pdf`, Section IV: "N computation qubits …
  M communication qubits are assigned to handle inter-core communication"; Fig. 4 draws them as different qubits.

So the mapper's 8 slots are computation qubits; ACE's 4 memories are communication qubits.
Logical qubits = 16 cores × (8 − 2 free slots) = **96**.

The earlier 48-qubit workload (Experiments 1 and 2, heatmaps, torus, routing study) came from
`tools/congestion_study/run_study.py` (commit `2902a4c`, 2026-10-21), which treated the 4 communication memories as
part of the 8 slots (4 data + 4 communication, minus 1 spare = 3 per core). That contradicts the papers. Those results
must be redone on 96-qubit traces.

**UNVERIFIED:** that 2 free slots per core is what the group intends (the papers fix 8 computation qubits per core,
not how many a circuit fills). To confirm with Rajeswari.

### The per-core arrangement (checked in code unless marked)

```
one core (16 of them on a 4x4 mesh)
├── 8 computation qubits   ← the mapper places logical (circuit) qubits here
│     ├── 6 filled at the start      (initial placement: exactly 6 per core in qft_requests.txt)
│     └── 2 free slots               (reserved_ancilla = 2; landing room for incoming qubits)
└── 4 communication qubits ← ACE's "memories"; they make EPR pairs with neighbour cores
      ├── 3 the compiler may hold (pre-generated pairs)   (compiler memories = 3)
      └── 1 kept for on-demand requests                  (on-demand reserve = 1)
```

- **Computation qubits** hold the program's logical qubits and run its gates. A two-qubit gate needs both operands
  in the same core, so the mapper moves qubits between cores.
- **Communication qubits** never hold program data. Each emits a photon towards the BSM node between two adjacent
  cores, and on success the two communication qubits share an EPR pair. Teleportation then uses that pair to move one
  computation qubit's state into the other core. One hop uses one communication qubit at each end.
- **Free slots:** a teleported qubit must land in an empty computation qubit of the destination core. If every core
  started full, the first move would have nowhere to go. The mapper therefore fills only 8 − 2 = 6 per core at the
  start (`workload_capacity`, used for the initial placement only, `qmap/placement/base.py:122-130`). Afterwards a
  core may hold up to all 8 (`architecture.capacity`, checked in `qmap/validation.py`), so the free slots move around.
  This matches HQA's requirement of free space for teleportation (Escofet et al., arXiv 2403.17205).
- **Communication memory split** (ACE run settings `--total-memories 4 --compiler-memories 3`; same in the
  mid-term): the compiler may occupy at most 3 of the 4 for pre-generated pairs; 1 is left for on-demand
  generation. **UNVERIFIED (phase 2):** whether ACE's 4 memories are shared across all of a core's neighbour links or
  split per link.
- **Multi-hop moves:** see "Point 3" below.

### Point 3: what happens in the relay core of a multi-hop move (checked in papers and code)
The group's two papers describe **two different models**:

| | A. Hop-by-hop teleportation | B. Entanglement swapping |
|---|---|---|
| Source | `Decentralized_Framework…pdf`, Sec. IV-A ("the source core transfers the qubit to the next core along the path … repeated until the qubit reaches the destination core") | `2607.14592v1.pdf` (ACGP), Sec. II and III-A ("intermediate cores perform entanglement swapping to construct a long-distance EPR pair between the source and destination cores. Teleportation proceeds only after this process completes"); Table I swap probability 0.95 |
| Does the qubit land in the relay? | Yes, in a computation qubit | No, it goes source → destination in one teleport |
| Relay's computation slots | Needs a free one when the qubit arrives | Not used |
| Relay's communication qubits | 1 for the incoming pair, 1 for the outgoing pair (one after the other) | 2 at once (one pair on each side), released by the swap |
| EPR pairs | One per hop, made one after the other | One per hop, all made in parallel, then swapped |
| Teleports | One per hop | One |

What the current pipeline does (checked):
- The mapper bills a qubit only at its source and destination (`qmap/validation.py` checks occupancy of placements);
  it never puts the qubit in a relay core, so it never checks for a free slot there.
- `qmap/io/requests.py:25-45` splits the route into one request per adjacent pair of cores.
- ACE treats each request as one adjacent-core EPR pair. It neither teleports nor swaps (`ace-physical-parameters.md`:
  "swapping … not exercised"). The per-qubit scheduler releases hop k only after hop k−1 completes
  (`request_scheduler.py:7-8`, "the qubit has to arrive before it can move on"), which is model A's timing.
- So today's pipeline is a **mix**: model A's timing (hops one after another), with no check of the relay's computation
  slots (which model A needs), and no swapping (which model B needs). Neither paper's model is implemented exactly.

In both models the relay core spends communication qubits, so Experiment 2's own-versus-relay split stays meaningful.

**Phase 1 direction (2026-10-25):** make model A (store-and-forward) explicit and complete, because it matches the
existing hop-split trace. Model B (swapping, as in the ACGP paper) is kept as a later option, still to confirm with the
group. Proposed rules:
- reserve a computation slot at the next core before the hop starts (not only before it completes), so the
  teleport always has somewhere to land;
- after hop 0→1 completes, q occupies that slot at core 1, and core 0's slot is freed;
- core 1 keeps q's slot until hop 1→2 has moved q on;
- two ledgers, because the qubits are separate (8 computation + 4 communication per core): a computation-slot ledger
  for data qubits and ACE's existing communication-memory ledger for EPR pairs.

Issues to settle before building (none checked yet):
- The mapper never checks a relay core's computation slots. If a relay is full (8 of 8) when q passes, the plan is
  infeasible as written: wait, reroute, or let the mapper account for relays?
- Waiting for a slot can deadlock: two qubits crossing in opposite directions between two full cores each hold a
  slot the other needs. The slot reservation needs the same no-hold-and-wait rule ACE's `event` admission already uses.
- How often relays are full along the QFT-96 routes is unknown; a read-only count over the trace would answer it.

Nothing was run in this repository today beyond read-only checks; the reproduction ran in a scratch environment.

### Is the relay gap ACE's problem or ours? (checked in code)
- **Ours (the interface between the trace and ACE).** ACE inherits SeQUeNCe's path reservation: an end-to-end request
  reserves `memory_size` memories at the two ends and `2 × memory_size` at each intermediate core, generates every link
  and swaps at the intermediates (ACE `reservation.py:481-530`, `create_rules_adaptive`; `swapping.py`; native
  `sequence/network_management/reservation.py:457-460`). The path comes from XY routing (`node.py:18`, `xyrouting`).
  So ACE already implements model B. We bypass it because the trace splits each move into adjacent hops.
- **What ACE lacks:** data qubits and teleportation. It stops once an EPR pair is delivered, so model A
  (store-and-forward) needs a computation-slot ledger that we would write ourselves.
- **Native SeQUeNCe 0.8.1 has both:** `DQCNode` has a separate data memory array next to the communication memories
  (`sequence/topology/node.py:812-842`), plus `TeleportApp` and `TeleportProtocol` and the same swapping path
  reservation. What it lacks is ACE's adaptive continuous generation (CGP/ACGP, the cache of pre-generated pairs),
  which is why ACE is used.
- If moves were sent end-to-end, ACE would route them XY, not on the mapper's path. Choosing the route ourselves would
  need an explicit path passed in. **UNVERIFIED** how much work that is.

### Plan: our routing → hop-by-hop requests → unchanged ACE (checked in code)
- **Works without ACE changes** for any route made of adjacent hops. ACE only checks that each hop joins adjacent
  cores on the configured mesh or torus (`compiler_trace.py:191-210`, `validate_neighbor_requests`) and that a qubit's
  hops in a layer form a continuous chain (`request_scheduler.py:106-132`). A one-hop request never meets ACE's XY
  routing. This is how ACE runs today.
- **Not 100% correct yet:** (a) no computation-slot ledger, so a full relay core is not detected; (b) no teleportation,
  so "latency" is the EPR pair's delivery, not the qubit's arrival; (c) the phase-2 ACE checks are still open.
- **Pre-generating a later hop is already allowed.** The planner treats every hop as its own request and picks its
  generation layer from the request's layer only (`compiler_trace.py:258-312`). Hops 1→2 and 2→3 of the same qubit in
  layer L get the same candidate layers, so both pairs can be prepared together. The chain order applies only when the
  pairs are *used* (hop 2→3 is released after 1→2 completes).
- Side effects: the 2→3 pair holds its memories until 1→2 completes (part of the ~24 ms hold, handoff §5); the
  planner works in whole layers, so it cannot time 2→3 to "just before 1→2 finishes"; under ODG, 2→3's generation
  starts only after 1→2 completes. **Open (phase 2):** is that serialization a fair ODG baseline?

### ACE has no computation qubits (checked)
- An ACE core is a `QuantumRouterAdaptive` (`node.py:43`) with a single `MemoryArray` of **communication memories**.
  There is no data memory array; `DQCNode` and `data_memo` appear nowhere in the ACE code.
- The config `grid_4x4_ace_3.json` says `memo_size: 8`, but every run overwrites it with `--total-memories`
  (4) at `parallel_core.py:535-538`. Those 8 are communication memories, unrelated to the 8 computation qubits.
- A program qubit exists in ACE only as the `qubit` number on a request, used to chain hops. Computation qubits are
  tracked only by the mapper (placement per layer, at most 8 per core).

### Native SeQUeNCe: both qubit kinds? how are multi-hop requests served? (checked in code)
**Upstream SeQUeNCe 0.8.1** (`BTP/SeQUeNCe-0.8.1`):
- `DQCNode` (`sequence/topology/node.py:812-842`) has communication memories plus a separate `DataMemoryArray`.
- A multi-hop teleport A→C is served end to end by swapping (model B): `TeleportApp.start` calls `RequestApp.start`
  (`sequence/app/teleport_app.py:50-55`) → RSVP reserves `memory_size` at the ends and `2 × memory_size` at each
  middle node (`network_management/reservation.py:457-460`) → every link generates a pair → middle nodes swap →
  A does the Bell measurement on (data qubit, communication qubit) (`entanglement_management/teleportation.py:143-153`)
  → C corrects. The path is a Dijkstra shortest path on channel length (`topology/router_net_topo.py:183-197`).
- The teleported state ends in C's **communication** memory (`teleport_app.py` `teleport_complete(comm_key)`),
  is recorded, and the memory is then reset. It is not moved into a data qubit at C, so even upstream does not model
  destination data-slot occupancy.

**Group's native fork** (`BTP/SeQUeNCe`, remote `sanjeevkrishnaa/SeQUeNCe`, branch `codex/native-compiler-4x4-physical`;
not fully read):
- `sequence_model.py` (the ISVLSI/ACGP reproduction backend): 8 computation + 4 communication memories per node,
  swap probability 0.95, XY routing, "swap_order: sequential from source after all elementary links are ready",
  "data_memory_model: independent six-state probes; ideal local gates and destination data storage". A request claims
  one free computation slot at its source and destination (`data_claims`, lines 936-1000) and releases it on
  completion; it does not track where the program's qubits are.
- Its compiler trace reader rejects non-adjacent requests (`compiler_trace.py:280`), so the native compiler studies
  were also fed hop-split traces.

### DECISION: model B, entanglement swapping (user, 2026-10-25)
A move from 0 to 2 via 1: link pairs 0–1 and 1–2, swap at 1, one end-to-end pair 0–2, one teleport 0→2. The data
qubit never lands in the relay. This matches the group's ACGP paper, upstream SeQUeNCe, the group's native fork and
the literature (three-node teleportation between non-neighbouring nodes: Hermans et al., Nature 2022). The
store-and-forward proposal is dropped, and with it the relay "8 of 8" question.

### What is still not correct in ACE under swapping (checked in code unless marked)
1. **Hop-split input.** Each move reaches ACE as separate adjacent requests (`compiler_trace.py:204`
   `validate_neighbor_requests` rejects anything else), so ACE never swaps.
2. **Chain ordering.** `request_scheduler.py:106-132` releases hop k only after hop k−1 completes. Under swapping, all
   links of a move are generated in parallel and then swapped.
3. **Admission ignores relays.** `_try_admit` and `_free_memories` (`request_scheduler.py:209-255`) check memories
   at the source and destination only. Under swapping, each relay needs 2 memories at once
   (`reservation.py`; native `reservation.py:457-460`).
4. **Swap success is 1.** `node.py:73` hard-codes `swapping_success_rate = 1`; the group's paper (Table I) says 0.95.
5. **Route is not ours.** An end-to-end request follows ACE's forwarding table: Dijkstra on channel length
   (`router_net_topo_adaptive.py:53-100`), ties broken by networkx. Classical messages follow XY (`node.py:18, 103,
   128`). To use our routing, the request must carry its path. **UNVERIFIED:** whether quantum and classical paths
   can then disagree, and what that does.
6. **Compiler pre-generation is per adjacent request.** The planner books one pair per hop request
   (`compiler_trace.py:258-312`). Under swapping, a move needs one pre-generated pair on every link of its path,
   consumed together and then swapped. **UNVERIFIED:** whether ACE's compiler-pair consumption (`generation.py`
   265-343) works on links inside a multi-hop reservation.
7. **The compiler memory cap assumes one memory per request per core.** The 3+1 rule and the
   generation-capacity limit count endpoints only; a relay holds 2.
8. **No teleportation.** Latency ends when the end-to-end pair exists. The teleport (Bell measurement, classical
   message to the destination, correction) is not modelled.
9. **Congestion metrics.** The own-versus-relay split was computed from hop-split traces; under swapping a relay
   holds 2 memories per move, so it must be recomputed.
10. **Still open from the handoff, independent of swapping:** time units (ms vs. µs coherence), accepted autonomous
   reservations never released, `num_unused_entanglement_pairs`, the 0.2 s period comment, lookahead never changing
   the schedule, the swap-into-own-memory on a cache hit, ODG fidelity constant at 0.9498, physical parameters.

### SCOPE (user, 2026-10-25)
In scope: mapping (supplied mapper, we consume its output) → routing (ours) → EPR generation for each move (ACE,
end to end with swapping) → timing and latency of the EPR pair.
Out of scope: computation-qubit occupancy (the mapper keeps every core at most 8; with swapping, relays hold no data
qubit) and teleportation itself. Every reported latency is **EPR delivery latency, teleportation excluded**, and must
say so. Teleportation adds a Bell measurement, one classical message and a correction per move. It is assumed the
same for every policy, so policy comparisons hold, but absolute numbers are not "teleportation latency" as in the
ACGP paper's Fig. 3. **UNVERIFIED:** that the addition is really policy-independent (the classical message length
depends on the route).
Items 1–7 of the ACE gap list stay in scope; item 8 is out.

### Worked example: how ACE serves a multi-hop move today (checked in code)
QFT-96, layer 68, `qft_requests.txt` lines 320-324: q93 moves 13→14→15→11→7→3 as five lines.
Core c is `router_{c//4}_{c%4}` (`compiler_trace.py:187-188`), so 13 = router_3_1, 3 = router_0_3.
- The five hops are five separate adjacent requests chained in trace order. Hop k is released when hop k−1's pair
  is delivered (`request_scheduler.py:106-132`). Each hop: admission checks 1 free memory at both its cores, an RSVP
  reservation on the 1-hop path, generation through the BSM node between them, or use of a compiler-prepared pair.
- ACE has **two routing mechanisms**. (a) Quantum path of a reservation: a forwarding table from Dijkstra on channel
  length (`router_net_topo_adaptive.py:53-100`). On the mesh every link has the same length, so all shortest paths tie.
  **UNVERIFIED** which one networkx returns. (b) Classical messages: `xyrouting` (`node.py:18-40`) moves along the
  **column first, then the row**, and is used for every message not sent to a neighbour (`node.py:103, 128`).
- In the trace, q93's route changes column first (13→14→15) and then row (15→11→7→3), which is XY by ACE's
  definition. Our reproduction gave 13→9→5→1→2→3 (row first). The mapper does not follow XY; this move only happens to.

### Swapping on a long route: what waits for what (checked in code)
- ACE's swap rules (`reservation.py:650-683`) use **nested (doubling) swapping**, decided locally. Each relay swaps
  as soon as *its* left and right pairs are ready; nobody waits for the whole path. For 13,14,15,11,7,3:
  14 swaps (13|15), 11 swaps (15|7), then 15 swaps (13|7), then 7 swaps (13|3).
- The end-to-end pair still needs every link, so a move finishes when its **slowest** link (plus the swaps) is
  done. Rough estimate, assuming independent exponential link times with mean T: parallel ≈ T·(1 + 1/2 + … + 1/n)
  = 2.28 T for n = 5, against ≈ 5 T for hop-by-hop. **Estimate, not measured.**
- Costs: (1) all cores on the path hold memories at once (2 per relay) from reservation to the end-to-end pair,
  so long routes add congestion; (2) early links wait and decohere; (3) swaps can fail: at p = 0.95 per swap,
  4 swaps all succeed with 0.95⁴ ≈ 0.81 (ACE uses p = 1 today, `node.py:73`). **UNVERIFIED** what ACE does
  after a failed swap (regenerate inside the same reservation, or fail the request).
- Pre-generated link pairs remove the wait for slow links, which is where the compiler method can help on long
  routes; the memory they hold is the congestion cost.

### DECISION: after a failed swap, regenerate only what was destroyed, keep the rest (user, 2026-10-25)

### How a swap works in ACE (checked in `swapping.py`, `reservation.py:650-683`)
- Middle core (`EntanglementSwappingA_bds.start`, `swapping.py:100-160`): it holds one memory paired with its left
  partner and one with its right partner, and does a Bell measurement on the two. With probability `success_prob`
  it succeeds: the two far memories become one pair, its fidelity comes from `swapping_res()` (lower than either
  input), and its expiry is the earlier of the two inputs. A `SWAP_RES` message goes to each far end. Either way, the
  middle core's two memories return to RAW.
- Far ends (`EntanglementSwappingB_bds.received_message`, `swapping.py:302-325`): on success (and not expired) the
  memory is re-labelled as paired with the other far end and marked ENTANGLED; on failure (`fidelity=0`) or expiry it
  returns to RAW.
- The rounds are a **dependency order**, not synchronised steps: 15 can swap only once it holds pairs to 13 and 7,
  and those exist only after 14 and 11 have swapped.
- **A failed swap destroys both pairs it consumed**, and with them every link inside them. If 15's swap (13|7)
  fails, pairs 13═15 and 15═7 are lost, which were built from links 13═14, 14═15, 15═11 and 11═7. Link 7═3 is not
  involved and is kept. Physics forces this (a failed Bell measurement destroys both inputs); "regenerate only what
  was destroyed" is the most that can be kept.
- Memories that return to RAW inside an active reservation should start generating again under that reservation's
  rules. **UNVERIFIED in a run**; also unverified: whether a relay's freed memory stays booked until the reservation
  ends (50 ms request window), which would add to congestion.
- `SWAP_RES` messages to non-neighbours travel over XY classical routing, so a swap's result takes several classical
  hops to reach a far end.

### Runs on unmodified ACE (2026-10-25) — checking the stories
Probe scripts live in the session scratchpad (`ace_probe/probe.py`, `fixspy.py`). They import ACE as it is and only
wrap functions to record events. Settings: 4 memories per core, background generation off
(`adaptive_max_memory = 0`), per-qubit scheduler with `event` admission, lead 5.3 ms, window 50 ms, seed 0.

1. **Routes (confirmed, plus one new finding).** For 13→3, ACE's quantum path (forwarding table) is
   13→9→5→1→2→3 (rows first), but classical messages go 13→14→15→11→7→3 (XY). **The quantum path and the classical
   path differ.** For 3→13, 0→15 and 5→10 they agree. The table computes each pair from the lexicographically
   smaller router name and reverses it, so the direction decides which one you get.
2. **Hop-split (confirmed).** q93's five hops run strictly one after another. Per-hop latencies
   0.80/1.20/0.50/5.00/0.50 ms (≈ 8.0 ms in total); the move took **34.5 ms** of elapsed time, because each hop
   waits its own 5.3 ms lead before its reservation starts (5 × 5.3 = 26.5 ms).
3. **End-to-end with swapping: BROKEN in base ACE for 3 or more hops.**
   - 1 hop: completes (0.80 ms). 2 hops (13→15): completes (1.50 ms, one swap).
   - 3, 4, 5 and 6 hops (13→11, 13→7, 13→3, 0→15): **never complete** in 10 s simulated time. The request
     times out every 50 ms and is resubmitted (181 submissions). Only the first round of swaps ever happens.
   - Relay memory reservations are correct: 1 memory at each end, 2 at each relay (timecard events).
   - **Root cause (checked by logging and by a patch applied in memory only):** a second-round swap needs a handshake
     between non-neighbours (for example core 10 with core 13), so the messages are forwarded through core 9.
     At the final destination, `QuantumRouterAdaptive.receive_message` (`node.py:136-140`) passes `src` = the
     **last forwarder**, not the original sender. ACE stores the original sender in `msg.src` (`node.py:100`) but
     never uses it. SeQUeNCe's resource manager replies to `src` (`resource_manager.py:262-274`), so core 13 answers
     core 9. Core 9 has no such protocol and sends `RELEASE_PROTOCOL`, cancelling core 13's side. Core 10's swap
     never starts.
   - **With the sender fix applied in memory only** (pass `msg.src` at the final destination), all lengths complete
     on the first submission: 13→11 2.60 ms, 13→7 2.50 ms, 13→3 **3.60 ms**, 0→15 5.50 ms.
   - Existing results are not affected: every trace request so far was a single hop, which only talks to neighbours.
4. **Failed swaps (with the fix; swap success overridden in memory).** p = 0.95, seeds 0–2: 3.6, 3.7, 5.4 ms.
   p = 0.5: 32.4, 7.0, 61.7 ms (the last needed a second submission after the 50 ms window). After a failure, both
   input pairs go RAW, those links are generated again inside the same reservation, and pairs not involved are
   kept. This matches the decision "regenerate only what was destroyed". **UNVERIFIED:** with p = 1, seed 0,
   core 1 swapped twice; why is not yet understood.

No ACE source file was changed. The fix is a proposal, not applied.

### The ACE paper, read in full (Zhan et al., arXiv 2502.01964v2, `BTP/2502.01964v2.pdf`, 8 pages)
What it says, and how it bears on our findings:
- **Built for multi-hop requests with swapping.** A request asks for an end-to-end pair between initiator and
  responder; TTS = t − start time (Eq. 1) "includes the time for elementary link entanglement generation and
  entanglement swapping". The 20-node network uses paths with 2 intermediate nodes and the 200-node AS network
  uses exactly 4. So ACE as published serves 3- and 5-link paths, which our copy cannot (bug above).
- **Routing:** "static routing … forwarding table … following the shortest distance path" (§II-A2). This matches the
  Dijkstra table. Path computation happens between request arrival and start time and is not in TTS, which is the
  same role as our 5.3 ms lead.
- **Classical latency (Eq. 2):** l(u,v) = d/c + hops × 20 µs (forward) + 100 µs (end processing), Table I. Our
  `router_net_topo_adaptive.py:104-115` applies exactly this to every classical channel. Our config keeps the
  100 µs / 20 µs metro-network constants while shrinking links to 2.5 cm, so these delays, not light travel, set
  our millisecond timescale. **Input for the phase-2 "why ms" question.**
- **Swapping success rate 1** in Table I. ACE's hard-coded 1 (`node.py:73`) follows the paper; 0.95 is from the
  group's ACGP paper.
- **Using a pre-generated pair (§IV-C3, C7, Fig. 6b):** the alphabetically larger ("primary") node picks the pair,
  and its qubits are "reallocated" to the memory slot allocated for the on-demand request. So the request needing
  its own slot (handoff §3 item 6) is the paper's design, not an artefact.
- **ODO fidelity is constant at 0.949** in the paper (Fig. 8b); our ODG's constant 0.9498 matches (handoff §3 item 7).
- ACP FSM (§III-A): sleep τ → if counter < MAX_MEMORY_ACP and a free memory → pick a neighbour from the probability
  table → QUERY → YES/NO. Adaptive update (Alg. 1): +δ for each neighbour on a served request's path, then normalise;
  the initiator sends the path to intermediate nodes. There is a "phantom" neighbour None. δ = 0.05.
- Purification: as-soon-as-possible pumping on the primary node, new pair kept, old pair measured (§IV-C6).
- Table I: 10 memories per node, ACP max 5, memory efficiency 0.6, detector 0.95, coherence 2 s, initial fidelity
  0.95, gate and measurement fidelity 0.99, photonic BSM success 0.5, 10 km links, 0.2 dB/km, requests at 10 Hz,
  fidelity threshold 0.5, request window slightly under 0.1 s.
- Results: two-node ODO 5.95 ms vs ACP 0.39 ms (−94%); 20-node −70% vs ODO; 200-node 15.7 → 6.8 ms (−57%);
  fidelity +0.01 to +0.05.

**Where the forwarding bug came from (checked in git):** our topology has only neighbour classical channels
(144 = 96 router–BSM + 48 router–router). Commit `2310181` (2026-10-23, "Route classical messages across the sparse
ACE mesh") added `send_message` with XY forwarding; the receive path kept passing the last hop as `src`. The paper
describes per-link classical channels plus Eq. 2 for multi-hop delay. **UNVERIFIED:** whether the published ACE
code (github.com/caitaozhan/adaptive-continuous) uses all-pairs classical channels with Eq. 2 delays; if it does,
the bug exists only in our sparse-mesh adaptation.

### FIX: relayed classical messages keep their original sender (2026-10-25)
- `node.py` `receive_message`: at the final destination, `src = getattr(msg, "src", src)` before dispatching to the
  network manager, resource manager, ACP or protocols. One line plus a comment.
- Test `test/test_multihop_forwarding.py`: 3-, 4-, 5- and 6-hop requests complete on the first submission; 1-hop
  (0.80002526 ms) and 2-hop (1.50003851 ms) latencies are unchanged. **Checked that it fails on the old `node.py`**
  (all four multi-hop cases: `0 != 1`) and passes with the fix.
- Full suite: 151 tests OK (149 existing + 2 new).
- Baseline check (`tools/ace_correctness/baseline.py check --strict`, incl. QFT-96): 164 rows compared, 164 identical, PASS.
