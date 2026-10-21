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
    mesh_dimensions,
    parse_compiler_trace,
    plan_preparations,
    to_ace_layers,
    validate_neighbor_requests,
)
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


def _row(strategy: str, seed: int, result: dict, request_count: int) -> dict:
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
                "metric_version": stats["metric_version"],
        "average_delivered_epr_fidelity": _mean_fidelity(result["fidelity_dict"]),
        "total_retries": stats.get("total_retries", 0),
        "requests_with_retries": stats.get("requests_with_retries", 0),
    }
    if compiler is None:
        row.update({
            "scheduled_preparations": 0,
            "pregenerated_success_rate": None,
            "on_demand_fallback_rate": None,
            "compiler_waste_percentage": None,
            "average_compiler_fidelity_at_utilization": None,
        })
    else:
        row.update({
            "scheduled_preparations": compiler["scheduled_preparations"],
            "pregenerated_success_rate": compiler["pregenerated_success_rate"],
            "on_demand_fallback_rate": compiler["on_demand_fallback_rate"],
            "compiler_waste_percentage": compiler["compiler_waste_percentage"],
            "average_compiler_fidelity_at_utilization": compiler[
                "average_fidelity_at_utilization"
            ],
        })
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/final_config/grid_4x4_ace_3.json"))
    parser.add_argument("--mesh", default="4x4")
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
    validate_neighbor_requests(trace, rows, columns)
    layers = to_ace_layers(trace, columns=columns, fidelity=args.fidelity_threshold)
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
                    simulation_stop_time_s=args.stop_time_s,
                    serialize_conflicts=True,
                )
            else:
                with redirect_stdout(StringIO()):
                    result = run(
                        str(args.config), update_prob, False, layers, args.pregeneration_buffer_ms,
                        args.request_duration_ms, label, seed=seed, compiler_spec=compiler_spec,
                        total_memories_per_core=args.total_memories,
                        simulation_stop_time_s=args.stop_time_s,
                        serialize_conflicts=True,
                    )
            row = _row(strategy, seed, result, len(trace.requests))
            summary.append(row)
            print(
                f"{strategy:20} seed={seed} complete={row['completion_rate']:.2%} "
                f"latency={row['average_request_latency_ms']} ms "
                f"fidelity={row['average_delivered_epr_fidelity']}"
            )

    _write_csv(args.output / "summary.csv", summary)
    (args.output / "metadata.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(),
            "metric_version": 2,
            "implementation_version": 3,
            "physical_seed_algorithm": "SeedSequence([trial_seed, sorted_timeline_entity_index])",
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parent / name).read_bytes()).hexdigest()
                              for name in ['reservation.py', 'resource_manager.py', 'generation.py', 'adaptive_continuous.py', 'request_app_parallel.py', 'parallel_core.py', 'compiler_scheduler.py', 'compiler_trace.py']},
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
