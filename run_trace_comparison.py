"""Compare ACE pre-generation strategies on a compiler-emitted trace.

The trace is the only workload input.  Every strategy is run through the same
ACE physical simulator, mesh, request manager, memory count, request window,
and random seeds.  ``continuous`` and ``adaptive-continuous`` are ACE's
autonomous cache protocols; ``fixed`` and ``dynamic`` are compiler-directed
one-shot preparation policies.
"""

from __future__ import annotations

import argparse
import hashlib
import csv
import json
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from statistics import fmean

from compiler_trace import (
    config_topology,
    mesh_dimensions,
    parse_compiler_trace,
    plan_preparations,
    to_ace_layers,
    validate_neighbor_requests,
)
from latency_metrics import arrival_latencies_ms
from parallel_core import run_parallel_experiment


AUTONOMOUS_STRATEGIES = {"continuous", "adaptive-continuous"}
COMPILER_STRATEGIES = {"on-demand", "fixed", "dynamic"}
ALL_STRATEGIES = AUTONOMOUS_STRATEGIES | COMPILER_STRATEGIES


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _mean_fidelity(fidelity_dict: dict) -> float | None:
    values = [value for values in fidelity_dict.values() for value in values]
    return fmean(values) if values else None


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _compiler_spec(args: argparse.Namespace, trace, columns: int, strategy: str) -> dict:
    schedule, blocked, peak = plan_preparations(
        trace,
        strategy=strategy,
        compiler_memories_per_core=args.compiler_memories,
        generation_capacity_per_core=args.generation_capacity,
        coherence_time_layers=args.coherence_time_layers,
        delta_layers=args.delta_layers,
        dynamic_lookahead_layers=args.dynamic_lookahead_layers,
    )
    return {
        "requests": trace.requests,
        "schedule": schedule,
        "strategy": strategy,
        "columns": columns,
        "planner_blocked": blocked,
        "planner_peak_memory": peak,
        "compiler_memories_per_core": 0 if strategy == "on-demand" else args.compiler_memories,
        "fidelity": args.fidelity_threshold,
        "reservation_duration_ms": args.compiler_reservation_ms,
    }


# A request "waited" for a memory if it was admitted more than a microsecond after it became eligible.  Generation takes
# about a millisecond, so this is far below any real wait, and far above the one picosecond the scheduler leaves after a
# release (request_scheduler.GRACE_PS), which is bookkeeping, not contention.
WAIT_THRESHOLD_MS = 1e-3


def _admission_waits(stats: dict) -> dict:
    waits = [part["admission_wait_time_ms"] for part in stats["timing_breakdown"].values()
             if "admission_wait_time_ms" in part]
    if not waits:
        return {"average_admission_wait_ms": None, "max_admission_wait_ms": None, "requests_that_waited_fraction": None}
    return {"average_admission_wait_ms": fmean(waits), "max_admission_wait_ms": max(waits),
            "requests_that_waited_fraction": sum(w > WAIT_THRESHOLD_MS for w in waits) / len(waits)}


def _arrival_latency(result: dict, requests, reduce):
    if requests is None:
        return None
    values = list(arrival_latencies_ms(result["request_manager"], requests).values())
    return reduce(values) if values else None


def _row(strategy: str, seed: int, result: dict, request_count: int, requests=None) -> dict:
    stats = result["stats"]
    compiler = result["compiler_metrics"]
    completed = stats["completed_requests"]
    row = {
        "strategy": strategy,
        "seed": seed,
        "requests": request_count,
        "completed_requests": completed,
        "completion_rate": completed / request_count if request_count else 0,
        "average_request_latency_ms": stats.get("avg_request_latency_ms"),
        "end_to_end_latency_ms": stats["end_to_end_latency_ms"],
        # the same arrival-to-completion definition under every scheduler
        "average_arrival_latency_ms": _arrival_latency(result, requests, fmean),
        "max_arrival_latency_ms": _arrival_latency(result, requests, max),
        # Compatibility aliases for existing analysis tools.  In metric version
        # 3 they have arrival-to-completion semantics, not the former
        # buffer-subtracted semantics.
        "average_eligible_latency_ms": _arrival_latency(result, requests, fmean),
        "max_eligible_latency_ms": _arrival_latency(result, requests, max),
        # time requests spent waiting for a free memory before being admitted (per-qubit scheduler only)
        **_admission_waits(stats),
        "metric_version": stats["metric_version"],
        "average_delivered_epr_fidelity": _mean_fidelity(result["fidelity_dict"]),
        "total_retries": stats.get("total_retries", 0),
        "requests_with_retries": stats.get("requests_with_retries", 0),
        # latency decomposition: where a request's time actually goes
        "avg_reservation_setup_time_ms": stats.get("avg_reservation_setup_time_ms"),
        "max_reservation_setup_time_ms": stats.get("max_reservation_setup_time_ms"),
        "avg_entanglement_generation_time_ms": stats.get("avg_entanglement_generation_time_ms"),
        "max_entanglement_generation_time_ms": stats.get("max_entanglement_generation_time_ms"),
        "avg_retry_wait_time_ms": stats.get("avg_retry_wait_time_ms"),
        # layer-level view, and how much the schedule stretched under contention
        "avg_layer_latency_ms": stats.get("avg_layer_latency_ms"),
        "max_layer_latency_ms": stats.get("max_layer_latency_ms"),
        "min_layer_latency_ms": stats.get("min_layer_latency_ms"),
        "total_layers": stats.get("total_layers"),
        "retry_layers": stats.get("retry_layers"),
        "total_layers_with_retries": stats.get("total_layers_with_retries"),
        # entanglement efficiency, defined identically for every strategy
        "protocol_generated_pairs": stats.get("protocol_generated_pairs"),
        "protocol_used_pairs": stats.get("protocol_used_pairs"),
        "protocol_unused_pairs": stats.get("protocol_unused_pairs"),
        "protocol_waste_percentage": stats.get("protocol_waste_percentage"),
    }

    # Compiler-only fields.  Every one of these is None for a strategy with no
    # compiler controller, which is a meaningful absence rather than a zero.
    compiler_fields = (
        "scheduled_preparations", "planner_blocked_preparations",
        "planner_peak_compiler_memory_per_core", "runtime_admission_attempts",
        "runtime_launched_preparations", "runtime_accepted_preparations",
        "runtime_rejected_preparations", "runtime_rejection_events",
        "pregenerated_hits", "pregenerated_success_rate",
        "intended_request_hits", "intended_request_hit_rate",
        "compiler_not_ready_requests", "late_compiler_pair_uses",
        "on_demand_fallbacks", "on_demand_fallback_rate",
        "generated_compiler_pairs", "utilized_compiler_pairs",
        "expired_compiler_pairs", "remaining_compiler_pairs",
        "compiler_expiry_percentage", "compiler_waste_percentage",
        "average_fidelity_at_creation", "average_fidelity_at_utilization",
    )
    row.update({
        name: (None if compiler is None else compiler.get(name))
        for name in compiler_fields
    })
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/final_config/grid_4x4_ace_3.json"))
    parser.add_argument("--mesh", default="4x4")
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh",
                        help="interconnect of the trace; --config must be the matching topology file (checked)")
    parser.add_argument(
        "--strategies",
        default="on-demand,continuous,adaptive-continuous,fixed,dynamic",
        help="comma-separated: on-demand, continuous, adaptive-continuous, fixed, dynamic",
    )
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--total-memories", type=int, default=4)
    parser.add_argument("--compiler-memories", type=int, default=3)
    parser.add_argument("--generation-capacity", type=int, default=3)
    parser.add_argument("--delta-layers", type=int, default=6)
    parser.add_argument("--dynamic-lookahead-layers", type=int, default=8)
    parser.add_argument("--coherence-time-layers", type=float, default=10)
    parser.add_argument("--fidelity-threshold", type=float, default=0.01)
    parser.add_argument("--pregeneration-buffer-ms", type=float, default=5.3)
    parser.add_argument("--compiler-reservation-ms", type=float, default=1000)
    parser.add_argument("--request-duration-ms", type=float, default=50)
    parser.add_argument("--stop-time-s", type=float, default=200)
    parser.add_argument("--scheduler", choices=("legacy", "per-qubit"), default="legacy",
                        help="legacy: per-core batches (the historical runs); per-qubit: hops of one qubit in order, "
                             "different qubits concurrent (docs/plans/ace-request-scheduler-design.md)")
    parser.add_argument("--admission", choices=("poll", "event"), default="event",
                        help="per-qubit scheduler only")
    parser.add_argument("--autonomous-cache-follows-compiler-memories", action="store_true",
                        help="CGP/ACGP cache at most --compiler-memories pairs per core (default: the config file's fixed adaptive_max_memory)")
    parser.add_argument("--stop-after-workload", action="store_true",
                        help="end the simulation 1 ms after the last request completes (default: run to --stop-time-s); per-qubit only")
    parser.add_argument("--no-starvation-guard", action="store_true", help="per-qubit event admission only")
    parser.add_argument("--max-layers", type=int)
    parser.add_argument("--output", type=Path, default=Path("output/trace_comparison"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    strategies = _csv_values(args.strategies)
    invalid = set(strategies) - ALL_STRATEGIES
    if invalid:
        parser.error(f"unknown strategies: {', '.join(sorted(invalid))}")
    try:
        seeds = [int(seed) for seed in _csv_values(args.seeds)]
    except ValueError:
        parser.error("--seeds must be a comma-separated list of integers")
    if args.compiler_memories > args.total_memories:
        parser.error("--compiler-memories cannot exceed --total-memories")

    trace = parse_compiler_trace(args.trace)
    if args.max_layers is not None:
        trace = replace(
            trace,
            requests=tuple(request for request in trace.requests if request.layer < args.max_layers),
            layer_count=min(trace.layer_count, args.max_layers),
        )
    rows, columns = mesh_dimensions(trace, args.mesh)
    validate_neighbor_requests(trace, rows, columns, args.topology)
    declared = config_topology(json.loads(Path(args.config).read_text(encoding='utf-8')), rows, columns)
    if declared != args.topology:
        parser.error(f"--topology {args.topology} needs a {args.topology} topology file, but {args.config} is a {declared}")
    layers = to_ace_layers(trace, columns=columns, fidelity=args.fidelity_threshold)
    scheduler_options = ({"admission": args.admission, "starvation_guard": not args.no_starvation_guard}
                         if args.scheduler == "per-qubit" else None)
    args.output.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    for seed in seeds:
        for strategy in strategies:
            compiler_spec = (
                _compiler_spec(args, trace, columns, strategy)
                if strategy in COMPILER_STRATEGIES else None
            )
            # The ACE router starts its autonomous cache protocol during timeline
            # initialization.  ``update_prob`` selects static continuous versus
            # feedback-adaptive neighbor choice; no compiler controller is attached.
            update_prob = strategy == "adaptive-continuous"
            label = f"trace-{strategy}-seed-{seed}"
            run = run_parallel_experiment
            if args.verbose:
                result = run(
                    str(args.config), update_prob, False, layers, args.pregeneration_buffer_ms,
                    args.request_duration_ms, label, seed=seed, compiler_spec=compiler_spec,
                    total_memories_per_core=args.total_memories,
                    autonomous_cache_limit=(args.compiler_memories if args.autonomous_cache_follows_compiler_memories and strategy in AUTONOMOUS_STRATEGIES else None),
                    stop_after_workload=args.stop_after_workload,
                    simulation_stop_time_s=args.stop_time_s,
                    serialize_conflicts=True,
                    scheduler=args.scheduler, request_plan=trace.requests,
                    scheduler_options=scheduler_options,
                )
            else:
                with redirect_stdout(StringIO()):
                    result = run(
                        str(args.config), update_prob, False, layers, args.pregeneration_buffer_ms,
                        args.request_duration_ms, label, seed=seed, compiler_spec=compiler_spec,
                        total_memories_per_core=args.total_memories,
                    autonomous_cache_limit=(args.compiler_memories if args.autonomous_cache_follows_compiler_memories and strategy in AUTONOMOUS_STRATEGIES else None),
                    stop_after_workload=args.stop_after_workload,
                        simulation_stop_time_s=args.stop_time_s,
                        serialize_conflicts=True,
                        scheduler=args.scheduler, request_plan=trace.requests,
                        scheduler_options=scheduler_options,
                    )
            row = _row(strategy, seed, result, len(trace.requests), trace.requests)
            summary.append(row)
            print(
                f"{strategy:20} seed={seed} complete={row['completion_rate']:.2%} "
                f"latency={row['average_request_latency_ms']} ms "
                f"fidelity={row['average_delivered_epr_fidelity']}"
            )

    _write_csv(args.output / "summary.csv", summary)
    (args.output / "metadata.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(),
            "metric_version": 3,
            "implementation_version": 4,
            "physical_seed_algorithm": "SeedSequence([trial_seed, sorted_timeline_entity_index])",
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parent / name).read_bytes()).hexdigest()
                              for name in ['reservation.py', 'resource_manager.py', 'generation.py', 'adaptive_continuous.py', 'request_app_parallel.py', 'parallel_core.py', 'compiler_scheduler.py', 'compiler_trace.py', 'latency_metrics.py']},
            "readiness_definition": "physical creation strictly before first application submission",
        "trace": str(args.trace.resolve()),
        "mesh": f"{rows}x{columns}",
        "trace_layers": trace.layer_count,
        "trace_requests": len(trace.requests),
        "strategies": strategies,
        "seeds": seeds,
        "parameters": vars(args),
    }, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {args.output / 'summary.csv'}")


if __name__ == "__main__":
    main()
