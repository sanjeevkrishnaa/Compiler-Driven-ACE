"""Run compiler-driven fixed/dynamic pre-generation through physical ACE/SeQUeNCe."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
from statistics import fmean
from contextlib import redirect_stdout

from compiler_trace import (
    mesh_dimensions,
    parse_compiler_trace,
    plan_preparations,
    to_ace_layers,
    validate_neighbor_requests,
)
from parallel_core import run_parallel_experiment


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _mean_fidelity(fidelity_dict) -> float | None:
    values = [fidelity for fidelities in fidelity_dict.values() for fidelity in fidelities]
    return fmean(values) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compiler-driven EPR pre-generation using ACE physical protocols"
    )
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument(
        "--config", type=Path,
        default=Path("config/final_config/grid_4x4_ace_3.json"),
    )
    parser.add_argument("--mesh", default="4x4")
    parser.add_argument("--strategies", default="on-demand,fixed,dynamic")
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--compiler-memories", type=int, default=3)
    parser.add_argument("--total-memories", type=int, default=4)
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
    parser.add_argument("--output", type=Path, default=Path("output/compiler_pregeneration"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.compiler_reservation_ms <= 0:
        parser.error("--compiler-reservation-ms must be positive")

    trace = parse_compiler_trace(args.trace)
    if args.max_layers is not None:
        if args.max_layers < 1:
            parser.error("--max-layers must be positive")
        trace = replace(
            trace,
            requests=tuple(request for request in trace.requests if request.layer < args.max_layers),
            layer_count=min(trace.layer_count, args.max_layers),
        )
    rows, columns = mesh_dimensions(trace, args.mesh)
    validate_neighbor_requests(trace, rows, columns)
    layers = to_ace_layers(trace, columns=columns, fidelity=args.fidelity_threshold)
    strategies = _csv_values(args.strategies)
    invalid = set(strategies) - {"on-demand", "fixed", "dynamic"}
    if invalid:
        parser.error(f"unknown strategies: {', '.join(sorted(invalid))}")
    try:
        seeds = [int(seed) for seed in _csv_values(args.seeds)]
    except ValueError:
        parser.error("--seeds must be a comma-separated list of integers")

    args.output.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    run_outputs = []
    for seed in seeds:
        for strategy in strategies:
            schedule, blocked, peak = plan_preparations(
                trace,
                strategy=strategy,
                compiler_memories_per_core=args.compiler_memories,
                generation_capacity_per_core=args.generation_capacity,
                coherence_time_layers=args.coherence_time_layers,
                delta_layers=args.delta_layers,
                dynamic_lookahead_layers=args.dynamic_lookahead_layers,
            )
            compiler_limit = 0 if strategy == "on-demand" else args.compiler_memories
            compiler_spec = {
                "requests": trace.requests,
                "schedule": schedule,
                "strategy": strategy,
                "columns": columns,
                "planner_blocked": blocked,
                "planner_peak_memory": peak,
                "compiler_memories_per_core": compiler_limit,
                "fidelity": args.fidelity_threshold,
                "reservation_duration_ms": args.compiler_reservation_ms,
            }
            label = f"compiler-{strategy}-seed-{seed}"
            if args.verbose:
                result = run_parallel_experiment(
                    str(args.config), False, False, layers,
                    args.pregeneration_buffer_ms, args.request_duration_ms,
                    label, seed=seed, compiler_spec=compiler_spec,
                    total_memories_per_core=args.total_memories,
                    simulation_stop_time_s=args.stop_time_s,
                )
            else:
                with redirect_stdout(StringIO()):
                    result = run_parallel_experiment(
                        str(args.config), False, False, layers,
                        args.pregeneration_buffer_ms, args.request_duration_ms,
                        label, seed=seed, compiler_spec=compiler_spec,
                        total_memories_per_core=args.total_memories,
                        simulation_stop_time_s=args.stop_time_s,
                    )

            stats = result["stats"]
            metrics = result["compiler_metrics"]
            row = {
                "strategy": strategy,
                "seed": seed,
                "requests": metrics["requests"],
                "completed_requests": stats["completed_requests"],
                "completion_rate": (
                    stats["completed_requests"] / metrics["requests"] if metrics["requests"] else 0
                ),
                "average_request_latency_ms": stats.get("avg_request_latency_ms"),
                "end_to_end_latency_ms": stats["end_to_end_latency_ms"],
                "average_delivered_epr_fidelity": _mean_fidelity(result["fidelity_dict"]),
                "scheduled_preparations": metrics["scheduled_preparations"],
                "planner_blocked_preparations": metrics["planner_blocked_preparations"],
                "runtime_launched_preparations": metrics["runtime_launched_preparations"],
                "runtime_accepted_preparations": metrics["runtime_accepted_preparations"],
                "runtime_rejected_preparations": metrics["runtime_rejected_preparations"],
                "runtime_rejection_events": metrics["runtime_rejection_events"],
                "pregenerated_hits": metrics["pregenerated_hits"],
                "pregenerated_success_rate": metrics["pregenerated_success_rate"],
                "intended_request_hits": metrics["intended_request_hits"],
                "intended_request_hit_rate": metrics["intended_request_hit_rate"],
                "compiler_not_ready_requests": metrics["compiler_not_ready_requests"],
                "late_compiler_pair_uses": metrics["late_compiler_pair_uses"],
                "on_demand_fallbacks": metrics["on_demand_fallbacks"],
                "on_demand_fallback_rate": metrics["on_demand_fallback_rate"],
                "generated_compiler_pairs": metrics["generated_compiler_pairs"],
                "utilized_compiler_pairs": metrics["utilized_compiler_pairs"],
                "expired_compiler_pairs": metrics["expired_compiler_pairs"],
                "compiler_expiry_percentage": metrics["compiler_expiry_percentage"],
                "compiler_waste_percentage": metrics["compiler_waste_percentage"],
                "average_compiler_fidelity_at_creation": metrics["average_fidelity_at_creation"],
                "average_compiler_fidelity_at_utilization": metrics["average_fidelity_at_utilization"],
                "average_compiler_storage_time_ms": metrics["average_storage_time_ms"],
            }
            summary_rows.append(row)
            run_outputs.append({
                "summary": row,
                "schedule": [
                    {"request_id": item.request_id, "generation_layer": item.generation_layer}
                    for item in schedule
                ],
                "epr_utilization_trace": metrics["epr_utilization_trace"],
                "rejection_reasons": metrics["rejection_reasons"],
            })
            print(
                f"{strategy:9} seed={seed} complete={row['completion_rate']:.2%} "
                f"latency={row['average_request_latency_ms']} ms "
                f"pre-ready={row['pregenerated_success_rate']:.2%} "
                f"expiry={row['compiler_expiry_percentage']:.2f}% "
                f"fidelity@use={row['average_compiler_fidelity_at_utilization']}"
            )

    _write_rows(args.output / "summary.csv", summary_rows)
    (args.output / "runs.json").write_text(
        json.dumps({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trace": str(args.trace.resolve()),
            "config": str(args.config.resolve()),
            "mesh": f"{rows}x{columns}",
            "trace_layers": trace.layer_count,
            "trace_requests": len(trace.requests),
            "parameters": {
                "compiler_memories": args.compiler_memories,
                "total_memories": args.total_memories,
                "generation_capacity": args.generation_capacity,
                "delta_layers": args.delta_layers,
                "dynamic_lookahead_layers": args.dynamic_lookahead_layers,
                "coherence_time_layers": args.coherence_time_layers,
                "fidelity_threshold": args.fidelity_threshold,
                "pregeneration_buffer_ms": args.pregeneration_buffer_ms,
                "compiler_reservation_ms": args.compiler_reservation_ms,
                "request_duration_ms": args.request_duration_ms,
                "stop_time_s": args.stop_time_s,
            },
            "runs": run_outputs,
        }, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"Wrote {args.output / 'summary.csv'}")
    print(f"Wrote {args.output / 'runs.json'}")


if __name__ == "__main__":
    main()
