"""Canonical repository paths for packaged code and historical source labels."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = {'adaptive_continuous.py': 'ace/protocols/adaptive_continuous.py',
 'compiler_settings.py': 'ace/compiler/settings.py',
 'compiler_scheduler.py': 'ace/compiler/compiler_scheduler.py',
 'compiler_trace.py': 'ace/compiler/compiler_trace.py',
 'demo.py': 'ace/examples/demo.py',
 'execution_events.py': 'ace/observability/execution_events.py',
 'fix_request_numbers.py': 'ace/utilities/fix_request_numbers.py',
 'generate_pir_traffic.py': 'ace/traffic/generate_pir_traffic.py',
 'generation.py': 'ace/protocols/generation.py',
 'invariants.py': 'ace/observability/invariants.py',
 'latency_metrics.py': 'ace/observability/latency_metrics.py',
 'memory_manager.py': 'ace/resources/memory_manager.py',
 'node.py': 'ace/topology/node.py',
 'parallel_core.py': 'ace/simulation/parallel_core.py',
 'parallel_core_helper.py': 'ace/simulation/parallel_core_helper.py',
 'purification.py': 'ace/protocols/purification.py',
 'request_app.py': 'ace/applications/request_app.py',
 'request_app_dynamic.py': 'ace/applications/request_app_dynamic.py',
 'request_app_parallel.py': 'ace/applications/request_app_parallel.py',
 'request_scheduler.py': 'ace/simulation/request_scheduler.py',
 'reservation.py': 'ace/resources/reservation.py',
 'resource_manager.py': 'ace/resources/resource_manager.py',
 'router_net_topo_adaptive.py': 'ace/topology/router_net_topo_adaptive.py',
 'run_compiler_pregeneration.py': 'ace/cli/run_compiler_pregeneration.py',
 'run_pir_experiments.py': 'ace/cli/run_pir_experiments.py',
 'run_pir_experiments_event.py': 'ace/cli/run_pir_experiments_event.py',
 'run_trace_comparison.py': 'ace/cli/run_trace_comparison.py',
 'runner.py': 'legacy/runners/runner.py',
 'runtime_provenance.py': 'ace/observability/runtime_provenance.py',
 'swapping.py': 'ace/protocols/swapping.py',
 'traffic.py': 'ace/traffic/traffic.py',
 'traffic_pattern_generator.py': 'ace/traffic/traffic_pattern_generator.py',
 'utility.py': 'ace/utilities/utility.py'}

def source_path(name: str) -> Path:
    """Resolve an original source label to its maintained implementation."""
    return REPO_ROOT / SOURCE_PATHS.get(name, name)
