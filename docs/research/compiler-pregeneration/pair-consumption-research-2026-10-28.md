# Pre-generated pair consumption: research and implementation

## Conclusion for this simulator

**Use in-place ownership handoff for entanglement delivery.** An application
receives the existing entangled memories; allocating another communication
memory merely to change their reservation owner is not a fundamental physical
requirement. Explicit `swap` remains a distinct extra-communication-memory
model, not the default.

This conclusion applies to the implemented **EPR-service interface**. The
current trace application records delivered entanglement and then discards it.
It does not execute a data-qubit teleportation circuit. New summary rows label
`latency_scope=entanglement_delivery`; metadata implementation version 5 also
records that data teleportation, data-memory occupancy, and its gate/reset
times are not simulated. The latency definition itself is unchanged.

## What the primary sources establish

1. **Delivered EPR qubits can be used in place.** NetQASM's create-and-keep API
   returns handles to the physical halves already generated. Applications can
   operate on those qubits. Its sequential interface explicitly describes
   measuring and freeing a qubit before generating another. This supports
   ownership transfer without copying the state to a second EPR memory.
   [NetQASM SDK](https://netqasm.readthedocs.io/en/latest/quickstart/modules.html).
2. **Teleportation needs a data qubit plus an EPR pair.** With source data Q and
   pair halves A/B, the sender measures Q and A in the Bell basis and sends two
   classical bits; corrections on B recover the input state. B is the output
   qubit, not a simultaneously free communication memory. The protocol does not
   prescribe an additional application EPR slot at each endpoint.
   [IBM Quantum](https://quantum.cloud.ibm.com/learning/en/courses/basics-of-quantum-information/entanglement-in-action/quantum-teleportation).
3. **Communication/storage roles depend on hardware.** NetQASM's architecture
   allows a communication qubit to hold a stored state; some platforms have
   restricted communication qubits and require explicit local transfers.
   [NetQASM architecture paper, section II.1](https://arxiv.org/html/2111.09823).
4. **The received output remains occupied.** AutoComm's teleportation-based
   communication discusses the destination communication qubit remaining occupied
   by the teleported data and the cost of releasing it. A handoff at the network
   interface therefore must not be interpreted as immediately freeing a live
   data-bearing destination qubit.
   [AutoComm, sections 2.2 and 4.3](https://arxiv.org/html/2207.11674v1).
5. **A concrete teleportation API returns that output.** SquidASM documents the
   send routine as measuring the source qubit, while its receive routine returns
   the teleported qubit. Its application must decide when to release that output.
   [SquidASM routines](https://squidasm.readthedocs.io/en/stable/modules/routines.html).
6. **Entanglement service is a meaningful separate boundary.** The original ACE
   paper measures requests for entanglement links, completed when the link has
   been established. It is not a full simulation of arbitrary data teleportation
   and computation. [ACE paper, section II.C](https://arxiv.org/html/2212.08806v1).

The implementation choice below is our inference from this interface and these
sources, rather than a claim that every hardware architecture uses identical
memory policies.

## Memory lifecycle and accounting

| Stage | Sender | Receiver | Resource consequence |
| --- | --- | --- | --- |
| Pre-generation | A is stored and entangled | B is stored and entangled | One physical EPR slot per endpoint is occupied. |
| Delivery claim | Application adopts A's existing lease | Application adopts B's existing lease | Same memories and state; compiler quota changes ownership, but the physical slots remain booked. |
| Actual teleportation, outside current benchmark | Local Bell measurement consumes Q and A | B retains the output pending corrections | Source memories become reusable after the required local reset; B is not yet free. |
| Output placement, outside current benchmark | Source may begin new work | Keep B as data, or transfer into available data memory | A storage SWAP, correction, reset and occupancy must be modeled if required by the selected hardware. |
| Current benchmark's terminal consumer | Discards delivered EPR half | Discards delivered EPR half | Current RAW/reset bookkeeping represents terminal discard, not a teleported output being silently freed. |

A data qubit is distinct from the entanglement resource. In a split data/communication
architecture it belongs to the data bank; it should not automatically create a
fifth communication-memory requirement. Conversely, a future full teleportation
backend must check destination data capacity and retain the received state until
its real transfer or use completes. The present simulator does not enforce that
data-plane contract, and its numbers must not be presented as full teleportation
or quantum-program execution latency.

## Applied changes and verification

- The controller and generic, compiler-study, and routing launchers default to
  `handoff`. Historical named swap variants remain explicit reproductions.
- The existing physical handoff validates both endpoints and pair fidelity,
  transfers booking ownership without changing memory identity or state, retains
  quantum age/physical expiry, and cancels obsolete compiler booking cleanup.
- Native RSVP and cached-pair control messages retain their existing delays.
  Expiry during control propagation rejects the claim and uses normal fallback.
- Compiler quota release does not free the physical application booking. A
  single-memory-per-endpoint case works without exceeding its memory budget.
- A new physical integration regression checks the actual memory object,
  quantum-state key, stored state, generation timestamp, and expiration event
  before/after handoff at both endpoints. All **161 compiler tests pass**.
- All eight fresh QFT-96 verification trials complete and pass physical audits.

## Fresh default-mode confirmation

Full original mesh/XY QFT-96 trace, 3,876 adjacent requests, seeds 6–9, four
physical communication memories per core, C=4, all chain hops, ready-first,
two-layer lead, zero extra buffer. Values below measure EPR delivery.

| Strategy | Mean latency, ms | p95, ms | Trace service completion, s |
| --- | ---: | ---: | ---: |
| ODG | 1.335462 | 3.150081 | 4.060008 |
| Compiler C=4, in-place delivery | **0.656721** | **1.900037** | **3.389160** |

No lead window is subtracted; control, admission, retries and physical pair
service remain included. Local data-teleportation operations are excluded from
both strategies, not assumed to be physically instantaneous.

[Seed rows](data/pair-consumption-research-2026-10-28/all_seeds.csv),
[aggregates](data/pair-consumption-research-2026-10-28/aggregate.csv),
[audits](data/pair-consumption-research-2026-10-28/audits.csv), and
[raw evidence and source snapshots](../../../results/researched_pair_delivery_2026-10-28/README.md).

Reproduce with the pinned SeQUeNCe 0.8.1 runtime on `PYTHONPATH`:

```text
python -B -m tools.compiler_study.run_full_chain_latency --compiler-memories 4 --seeds 6,7,8,9 --compiler-reservation-ms 1000 --trace results/qft96_2seed_2026-10-26/traces/placements/mesh/T-HQA/qft96/seed_42/routes/xy/requests.txt --config config/final_config/grid_4x4_ace_3.json --output output/researched-pair-delivery-reproduction
```
