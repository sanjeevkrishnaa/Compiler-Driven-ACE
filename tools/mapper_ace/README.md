# Mapper-to-ACE boundary

`mapper/qmap` is vendored dependency code. Its placement algorithms and
`Partition` representation are not modified here. The project-owned adapter in
this directory defines the boundary used by ACE experiments:

1. `build_migration_records` exports one record per logical migration. The
   record contains `(qubit, source_core, destination_core)` and the complete
   physical path selected by an explicit policy.
2. `write_migration_trace` writes the authoritative `ace-migration-v2` JSONL
   artifact. It is the trace to archive and compare across routing studies.
3. `write_adjacent_requests` derives the legacy ACE text input by expanding the
   already selected path into adjacent requests. No routing decision is made
   during this export.

The `xy` and `yx` policies are dimension-order baselines for 2-D meshes. qmap
numbers mesh cores lexicographically by coordinate, and the policy names refer
to coordinate dimensions (dimension 0 first for `xy`), not core-number order.
`dijkstra` delegates to qmap's deterministic shortest-path model and is used
for torus studies. `shortest_reliable` and `max_reliability` delegate to qmap's
deterministic shortest-hop and maximum-product-reliability paths respectively.

Every migration is validated for endpoint correctness and physical adjacency;
the complete trace is also checked against the original partition transitions.
This prevents a malformed route or an accidental mismatch between mapper and
ACE input from silently entering a benchmark.

## Reproducible command

`export.py` accepts a JSON placement contract containing the mapper's initial
placement and per-layer assignments. Run it from the repository root with the
mapper package on `PYTHONPATH`:

```bash
PYTHONPATH=mapper python -m tools.mapper_ace.export \
  placement.json results/mapper_export --policy shortest_reliable
```

The output directory contains `migrations.jsonl` (authoritative),
`requests.txt` (legacy ACE input), and `manifest.json` (input hash, policy,
topology, migration count, and hop count). The command never edits qmap output
in place and can be rerun for every routing policy.
