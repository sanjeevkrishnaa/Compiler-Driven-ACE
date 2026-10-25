# ACE correctness audit — 2026-10-25

This note records the repository evidence behind the current ACE comparison.
It is intentionally separate from generated result folders and does not alter
the vendored mapper or SeQUeNCe dependency.

## Code provenance

| Component | Status | Evidence |
| --- | --- | --- |
| `mapper/qmap/**` | Vendored dependency; unchanged by the adapter | `mapper/PROVENANCE.md`; migration/routing behavior audited in source |
| `tools/mapper_ace/**` | Project-created in this branch | Commit `4ea7f99`; migration-v2 schema and explicit route policies |
| `parallel_core.py`, `request_scheduler.py`, `latency_metrics.py` | ACE implementation plus correctness work | Git history includes Gate 3/3b and metric-version commits |
| `main4.py` and other root runners | Historical project runners | Not used by the corrected headline comparison |
| `results/**` | Generated experiment artifacts | Each result folder has its own metadata/README; do not treat as source |

## The 5.3 ms value

`git blame` and history show the value in `main4.py` was introduced in the
original ACE import commit `c29d5e6` by Sanjeev:

```python
pregeneration_time_ms = 5.3  # Pre-generation buffer time
```

The value was passed to `run_parallel_experiment`, converted to simulation
picoseconds, and added before every reservation window. It was not derived from
the classical channel delay, EPR-generation model, coherence time, or a paper
table. The historical runner then reported a local service value that removed
5.3 ms from completion time. Therefore it is a historical experiment setting,
not a physical ACE constant and not a valid subtraction in a request-latency
headline.

The corrected timing path computes the RSVP guard from configured classical
channel delay (`parallel_core.py::_control_plane_guard`) and adds only an
explicitly requested experimental lead. Headline corrected runs use lead 0.

## Current metric contract

For each completed request, the fair request metric is:

```text
completion_time - eligibility_time
```

Eligibility is layer activation for the first hop of a qubit and predecessor
hop completion for a later hop of that same qubit in the same layer. Thus it
includes RSVP/control delay, shared-memory admission queueing, retries, and EPR
generation. It does not charge a request for a compiler-generated pair that was
already sitting in memory before that request became eligible.

Independent qubits can share an eligibility time and run concurrently; hops of
one qubit cannot bypass their predecessor. Mean latency is an average over
individual request intervals, not a makespan. A complete comparison therefore
reports the latency distribution (mean, median, p95, max), completion rate,
throughput, and end-to-end makespan separately.

## Current QFT-96 evidence

The versioned timing-model matrix uses 4 shared communication memories per
core, 3 compiler memories, 4×4 mesh, 4,954 adjacent-hop requests, and 30
physics seeds. The corrected per-qubit row is the current headline comparison:

* ODG: `1.526 ± 0.016 ms` mean fair request latency; `4.337 ± 0.026 s`
  makespan.
* Dynamic: `2.570 ± 0.096 ms` mean fair request latency; `4.694 ± 0.086 s`
  makespan.

The result is not evidence that pre-generation is conceptually wrong. It shows
that the current Dynamic reservation policy creates enough shared-memory
admission pressure to outweigh its service-time reduction. Optimization must be
evaluated against both latency and makespan while preserving completion and
fidelity.

## Reproducibility rules

1. Archive the migration-level trace and its selected routing policy before
   deriving adjacent-hop ACE requests.
2. Record the ACE commit, Python interpreter, SeQUeNCe version/commit, config,
   memory budgets, timing lead, scheduler, admission mode, and all seeds.
3. Never compare metric-version-2 local/service values with metric-version-3
   arrival-to-completion values.
4. Never compare ACE runs using SeQUeNCe 0.8.1 with native SeQUeNCe 1.0.0 runs
   until ACE has been ported and its complete test suite has passed there.
