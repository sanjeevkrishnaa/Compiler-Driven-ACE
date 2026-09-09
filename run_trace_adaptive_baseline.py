"""Replay a compiler trace against physical ACE ODG, CGP, and ACGP.

This deliberately does *not* attach ``CompilerPreGenerationController``.  It
therefore measures the repository's native continuous-generation policies:

* ``odg``: no autonomous speculative generation;
* ``cgp``: continuous generation with a fixed (uniform) neighbor table;
* ``acgp``: continuous generation whose table is updated from application use.

All policies consume the same conflict-serialized trace through
``ParallelLayerRequestManager``.  The adaptive cap is an occupancy limit over
the shared physical memory pool; it is not a disjoint memory bank.
"""

from __future__ import annotations

import argparse
import csv
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import platform
from statistics import fmean

from compiler_trace import (
    mesh_dimensions, parse_compiler_trace, to_ace_layers,
    validate_neighbor_requests,
)
from experiment_contract import (
    contract_sha256, load_contract, serialize_conflict_layers,
    serialization_sha256, validate_workload,
)
from parallel_core import run_parallel_experiment


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _mean_fidelity(values_by_app) -> float | None:
    values = [value for values in values_by_app.values() for value in values]
    return fmean(values) if values else None


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Physical ACE ODG/CGP/ACGP replay of a compiler trace"
    )
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--mesh", default="4x4")
    parser.add_argument("--strategies", default="odg,cgp,acgp")
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--config-odg", type=Path,
                        default=Path("config/final_config/grid_4x4_ace_0.json"))
    parser.add_argument("--config-adaptive", type=Path,
                        default=Path("config/final_config/grid_4x4_ace_3.json"))
    parser.add_argument("--total-memories", type=int, default=4)
    parser.add_argument("--adaptive-memory-cap", type=int, default=3)
    parser.add_argument("--fidelity-threshold", type=float, default=0.01)
    parser.add_argument("--pregeneration-buffer-ms", type=float, default=5.3)
    parser.add_argument("--request-duration-ms", type=float, default=50)
    parser.add_argument("--stop-time-s", type=float, default=200)
    parser.add_argument("--max-layers", type=int)
    parser.add_argument("--contract", type=Path,
                        help="validates trace and uses its serialized-layer duration")
    parser.add_argument("--output", type=Path,
                        default=Path("output/trace_adaptive_baseline"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.total_memories < 1 or not 0 <= args.adaptive_memory_cap <= args.total_memories:
        parser.error("adaptive memory cap must be between zero and total memories")
    strategies = _csv_values(args.strategies)
    if not strategies or set(strategies) - {"odg", "cgp", "acgp"}:
        parser.error("--strategies must be a nonempty subset of odg,cgp,acgp")
    try:
        seeds = [int(value) for value in _csv_values(args.seeds)]
    except ValueError:
        parser.error("--seeds must be comma-separated integers")

    trace = parse_compiler_trace(args.trace)
    if args.max_layers is not None:
        if args.max_layers < 1:
            parser.error("--max-layers must be positive")
        from dataclasses import replace
        trace = replace(trace,
            requests=tuple(request for request in trace.requests
                           if request.layer < args.max_layers),
            layer_count=min(trace.layer_count, args.max_layers))
    rows, columns = mesh_dimensions(trace, args.mesh)
    validate_neighbor_requests(trace, rows, columns)

    contract = None
    contract_hash = None
    source_layers = trace.layer_count
    minimum_layer_duration_ps = None
    serialization = None
    if args.contract:
        try:
            contract = load_contract(args.contract)
            validate_workload(contract, trace_sha256=_sha256(args.trace), mesh=args.mesh,
                              cores=trace.core_count, logical_qubits=trace.qubit_count,
                              layers=trace.layer_count, requests=len(trace.requests))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            parser.error(f"invalid contract or workload: {error}")
        request_layers, batches, _ = serialize_conflict_layers(trace.requests, trace.layer_count)
        digest = serialization_sha256(request_layers)
        expected = contract["workload"]
        if (len(batches) != expected["serialized_sublayers"]
                or digest != expected["serialization_map_sha256"]):
            parser.error("conflict serialization does not match contract")
        from dataclasses import replace
        trace = replace(trace,
            requests=tuple(replace(request, layer=request_layers[request.request_id])
                           for request in trace.requests), layer_count=len(batches))
        minimum_layer_duration_ps = contract["timing"]["logical_layer_duration_ps"]
        serialization = {"source_layers": source_layers,
                         "serialized_sublayers": len(batches),
                         "request_layer_map_sha256": digest}
        contract_hash = contract_sha256(args.contract)

    resolved = {
        "valid": True, "trace_sha256": _sha256(args.trace), "mesh": args.mesh,
        "trace_requests": len(trace.requests), "source_trace_layers": source_layers,
        "serialized_trace_layers": trace.layer_count, "strategies": strategies,
        "seeds": seeds, "memory_pool": {"physical_per_core": args.total_memories,
        "adaptive_occupancy_cap": args.adaptive_memory_cap,
        "demand_eligible_per_core": args.total_memories},
        "contract_sha256": contract_hash, "conflict_serialization": serialization,
        "minimum_layer_duration_ps": minimum_layer_duration_ps,
    }
    if args.validate_only:
        print(json.dumps(resolved, indent=2))
        return

    layers = to_ace_layers(trace, columns=columns, fidelity=args.fidelity_threshold)
    args.output.mkdir(parents=True, exist_ok=True)
    summaries, runs = [], []
    for seed in seeds:
        for strategy in strategies:
            is_odg = strategy == "odg"
            config = args.config_odg if is_odg else args.config_adaptive
            # CGP freezes the uniform neighbor table; ACGP learns from use.
            update_prob = strategy == "acgp"
            label = f"trace-{strategy}-seed-{seed}"
            kwargs = dict(seed=seed, total_memories_per_core=args.total_memories,
                          simulation_stop_time_s=args.stop_time_s,
                          minimum_layer_duration_ps=minimum_layer_duration_ps,
                          adaptive_memory_cap=(0 if is_odg else args.adaptive_memory_cap))
            if args.verbose:
                result = run_parallel_experiment(str(config), update_prob, False, layers,
                    args.pregeneration_buffer_ms, args.request_duration_ms, label, **kwargs)
            else:
                with redirect_stdout(StringIO()):
                    result = run_parallel_experiment(str(config), update_prob, False, layers,
                        args.pregeneration_buffer_ms, args.request_duration_ms, label, **kwargs)
            stats = result["stats"]
            row = {
                "strategy": strategy, "seed": seed,
                "completion_rate": (
                    stats["completed_requests"] / len(trace.requests)
                    if trace.requests else 1.0
                ),
                "completed_requests": stats["completed_requests"],
                "requests": len(trace.requests),
                "average_request_latency_ms": stats.get("avg_request_latency_ms"),
                "end_to_end_latency_ms": stats["end_to_end_latency_ms"],
                "retry_layers": stats.get("retry_layers", 0),
                "total_retries": stats.get("total_retries", 0),
                "average_delivered_epr_fidelity": _mean_fidelity(result["fidelity_dict"]),
                "physical_memories_per_core": args.total_memories,
                "adaptive_occupancy_cap_per_core": 0 if is_odg else args.adaptive_memory_cap,
                "memory_allocation": "shared",
                "adaptive_probability_updates": update_prob,
            }
            summaries.append(row)
            runs.append({"summary": row, "node_seeds": result["node_seeds"],
                         "simulator_timing_breakdown": stats.get("timing_breakdown", {}),
                         "simulator_layer_latencies_ms": stats.get("layer_latencies", {})})
            print(f"{strategy:4} seed={seed} complete={row['completion_rate']:.2%} "
                  f"latency={row['average_request_latency_ms']} ms retries={row['total_retries']} "
                  f"fidelity={row['average_delivered_epr_fidelity']}")
    _write_csv(args.output / "summary.csv", summaries)
    (args.output / "runs.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(), "resolved": resolved,
        "configs": {"odg": str(args.config_odg.resolve()),
                    "adaptive": str(args.config_adaptive.resolve())},
        "config_sha256": {"odg": _sha256(args.config_odg),
                          "adaptive": _sha256(args.config_adaptive)},
        "python": platform.python_version(), "runs": runs,
    }, indent=2), encoding="utf-8")
    print(f"Wrote {args.output / 'summary.csv'}")
    print(f"Wrote {args.output / 'runs.json'}")


if __name__ == "__main__":
    main()
