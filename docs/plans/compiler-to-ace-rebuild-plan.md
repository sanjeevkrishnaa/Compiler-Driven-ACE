# Compiler-to-ACE rebuild plan

**Status:** draft for joint review.  It records the decisions needed before changing
the mapper-to-ACE interface; it does not authorise a change to benchmark results.

## Problem statement

The vendor mapper produces a placement transition for each circuit timeslice.  A
transition is a logical migration `(qubit, source core, target core)`.  Its current
exporter expands every migration into adjacent edges.  ACE subsequently sees those
edges as independent application requests.  That bypasses native ACE's end-to-end
reservation and entanglement-swapping path, so an edge trace cannot represent one
end-to-end logical migration faithfully.

The target contract is one end-to-end migration with an explicitly selected physical
path.  ACE must reserve one communication memory at each endpoint and two at every
internal relay, establish link EPR pairs, swap at relays, and then model one endpoint
teleportation.  A logical data qubit does not reside at a relay under this model.

## Scope boundary

`mapper/qmap/` is a vendored dependency.  It remains unchanged until an upstream
change is explicitly justified and separately reviewed.  Project-owned code shall
live in a new integration layer (proposed: `tools/mapper_ace/`).  That layer reads a
validated mapper partition and writes a versioned migration artifact.

## Trace-v2 proposal

Use JSON Lines for the machine-readable artifact and retain a human-readable
companion report.  Every run also writes an immutable manifest.

```json
{"schema":"ace-migration-v2","migration_id":"m000184","layer":57,
 "qubit":47,"source_core":2,"destination_core":12,
 "path":[2,3,7,11,12],"route_policy":"xy",
 "topology":"mesh-4x4","path_hops":4}
```

The manifest must include: mapper-source hashes; mapper version; circuit and QASM
hashes; circuit/transpiler/mapping/reliability seeds; topology; core/data/communication
capacities; placer and its parameters; route-policy name and parameters; initial and
per-layer placement hashes; artifact hash; and the trace schema version.

`path` is authoritative.  ACE must not silently substitute its own shortest path.
The adapter must verify, for every layer, that applying the migration endpoints
reconstructs the mapper's next placement.  It must also verify that path endpoints,
adjacency, and topology are valid.

## Routing-policy vocabulary

The existing vendor `shortest` policy means minimum hop count, then maximum path
reliability, then lexicographic core path.  It is **not XY**.  Existing `reliability`
means maximum product reliability, with hop count as a tie-breaker.  The integration
layer must name policies unambiguously:

1. `xy` and `yx`: deterministic mesh-only baselines.
2. `shortest_reliable`: current vendor shortest-hop/reliability-tiebreak behaviour.
3. `max_reliability`: current T-HQAR physical-path behaviour.
4. `dijkstra_<weight>`: only after its edge weight and tie-breaking rules are written
   into the contract.
5. `offline_congestion_v1`: future policy; never used as a baseline until its future
   information and objective are documented.

Topology and placement are separate.  HQA, T-HQA, TR-HQA, and GTR-QA select
placements differently; T-HQAR uses the same placement objective as T-HQA but changes
the physical route.  Routing comparisons must hold the partition fixed unless the
research question explicitly tests joint mapping and routing.

## Gates

### Gate M1 - mapper evidence

- Verify all vendor files against the supplied archive and existing provenance.
- Hand-trace a small circuit through ASAP slicing, placement, migration extraction,
  and path selection.
- Reproduce one archived 48-qubit trace with the recorded environment.
- Establish whether the supplied 96-qubit QFT trace can be reproduced.  Until then,
  retain it as a historical fixed input, not as canonical mapper evidence.

### Gate M2 - trace-v2 implementation

- Implement the project-owned adapter and JSONL schema.
- Unit-test XY/YX, current shortest-reliable, and max-reliability paths.
- Add replay, topology, placement, deterministic-output, and manifest tests.
- Produce a small golden migration artifact and independently inspect it.

### Gate A1 - ACE protocol contract

- Demonstrate native ACE's end-to-end reservation on a multi-hop request.
- Make ACE consume prescribed migration paths and reject a path it cannot honour.
- Test endpoint-one/relay-two communication-memory reservation, swapping, endpoint
  EPR delivery, and one endpoint teleportation.
- Separate data-slot accounting from communication-memory accounting.

### Gate A2 - units and metrics

- Trace every timing value from configuration through SeQUeNCe's ps timeline to every
  reported unit.
- Publish a parameter-and-unit table for coherence, generation, gates, measurement,
  classical delay, reservation windows, and policy periods.
- Define route, layer, whole-program, and per-request metrics before comparing policies.

### Gate R - reproducible results

- Reproduce the accepted historical baseline under its original contract.
- Rerun corrected baselines under trace-v2 and ACE's end-to-end semantics.
- Keep old edge-trace values labelled historical; never merge them with corrected data.
- Require paired seeds, request/pair completion audits, route-decision artifacts, and
  raw-output hashes for every final table.

## Immediate work

Proceed with M1 code reading and a small deterministic mapper walkthrough.  Do not
implement trace-v2 or rerun benchmark suites until the project team approves this
protocol and artifact contract.
