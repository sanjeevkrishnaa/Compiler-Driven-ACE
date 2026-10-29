# ACE simulator source map

This package contains this repository's extensions to **SeQUeNCe**, not a copy of
the upstream simulator. Keep the separately pinned SeQUeNCe 0.8.1 dependency on
`PYTHONPATH`. Run commands from the repository root so configuration and data
paths keep their established meaning.

| Package | Responsibility | Start reading |
| --- | --- | --- |
| `compiler/` | Parse communication traces and plan/trigger compiler pre-generation. | [compiler_trace.py](compiler/compiler_trace.py), [compiler_scheduler.py](compiler/compiler_scheduler.py) |
| `simulation/` | Run experiments, release dependent hops, prioritize ready pairs, admit requests and coordinate completion. | [parallel_core.py](simulation/parallel_core.py), [request_scheduler.py](simulation/request_scheduler.py) |
| `protocols/` | Physical generation, cached-pair coordination, purification and entanglement swapping. | [generation.py](protocols/generation.py), [adaptive_continuous.py](protocols/adaptive_continuous.py) |
| `resources/` | Memory state, booking ownership, capacity and resource release. | [reservation.py](resources/reservation.py), [resource_manager.py](resources/resource_manager.py), [memory_manager.py](resources/memory_manager.py) |
| `applications/` | Application requests, delivery credit and benchmark consumption. | [request_app_parallel.py](applications/request_app_parallel.py) |
| `topology/` | Quantum routers and network construction. | [node.py](topology/node.py), [router_net_topo_adaptive.py](topology/router_net_topo_adaptive.py) |
| `observability/` | Event records, invariant auditing, latency calculations and runtime provenance. | [execution_events.py](observability/execution_events.py), [invariants.py](observability/invariants.py), [latency_metrics.py](observability/latency_metrics.py) |
| `traffic/` | Traffic matrices, patterns and PIR input generation. | [traffic.py](traffic/traffic.py), [generate_pir_traffic.py](traffic/generate_pir_traffic.py) |
| `cli/` | Command-line experiment implementations. | [run_trace_comparison.py](cli/run_trace_comparison.py) |
| `utilities/` | Shared helpers and request-number normalization. | [utility.py](utilities/utility.py), [fix_request_numbers.py](utilities/fix_request_numbers.py) |
| `examples/` | Original ACE demonstration scenarios. | [demo.py](examples/demo.py) |

## Follow an EPR pair

Pre-generation:

```text
compiler/compiler_trace.plan_preparations
  -> compiler/compiler_scheduler.launch_preparation
  -> protocols/adaptive_continuous.request_compiler_pair
  -> resources/reservation.create_rules_adaptive
  -> protocols/generation
  -> protocols/adaptive_continuous.add_generated_entanglement_pair
```

Execution and consumption:

```text
simulation/request_scheduler._try_admit
  -> protocols/adaptive_continuous: readiness and pair matching
  -> resources/reservation.schedule: existing-memory ownership handoff
  -> protocols/generation: native cached-pair delivery/control exchange
  -> applications/request_app_parallel.get_memory: credit and terminal discard
  -> resources/reservation.release_reservation
```

These requests measure EPR delivery, not a full data-qubit teleportation circuit.
The package relocation does not change that boundary or its timing rules.

## Running and importing

The four root scripts remain small compatibility launchers. Existing commands
such as `python run_trace_comparison.py ...` continue to work. The equivalent
package entry point is:

```text
python -m ace.cli.run_trace_comparison --help
```

Internal callers now use explicit package imports, for example:

```python
from ace.compiler.compiler_trace import plan_preparations
from ace.simulation.parallel_core import run_parallel_experiment
```

Use [paths.py](paths.py) to resolve historical source labels for source inspection
and provenance hashes. New CLI metadata includes `source_layout` and
`source_paths`, alongside the existing source hashes. Frozen results, source
snapshots and historical reports keep their original paths as provenance.

The obsolete batch launcher and fixed-delay experiment runners are under
[legacy/](../legacy/README.md), not mixed into the maintained simulator package.
