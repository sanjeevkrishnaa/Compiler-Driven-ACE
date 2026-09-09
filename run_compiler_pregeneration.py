"""Run compiler-driven fixed/dynamic pre-generation through physical ACE/SeQUeNCe."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import platform
from statistics import fmean
from contextlib import redirect_stdout
import sys

from compiler_trace import (
    mesh_dimensions,
    parse_compiler_trace,
    plan_preparations,
    to_ace_layers,
    validate_neighbor_requests,
)
from experiment_contract import (
    contract_sha256, load_contract, select_profile, serialize_conflict_layers,
    serialization_sha256, validate_workload,
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    parser.add_argument(
        "--memory-allocation", choices=("shared", "static"), default="shared",
        help="shared ACE pool or disjoint compiler/on-demand memory banks",
    )
    parser.add_argument(
        "--on-demand-memories", type=int,
        help="static on-demand bank size; required with --memory-allocation static",
    )
    parser.add_argument("--delta-layers", type=int, default=6)
    parser.add_argument("--dynamic-lookahead-layers", type=int, default=8)
    parser.add_argument(
        "--dynamic-min-lead-layers", type=int, default=1,
        help="minimum logical-layer lead for dynamic generation; use a calibrated value",
    )
    parser.add_argument("--coherence-time-layers", type=float, default=10)
    parser.add_argument("--fidelity-threshold", type=float, default=0.01)
    parser.add_argument("--pregeneration-buffer-ms", type=float, default=5.3)
    parser.add_argument("--compiler-reservation-ms", type=float, default=1000)
    parser.add_argument("--request-duration-ms", type=float, default=50)
    parser.add_argument("--stop-time-s", type=float, default=200)
    parser.add_argument("--max-layers", type=int)
    parser.add_argument("--output", type=Path, default=Path("output/compiler_pregeneration"))
    parser.add_argument(
        "--configuration-name",
        help="stable experiment label used when combining several summary files",
    )
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--profile", help="profile id from --contract")
    parser.add_argument(
        "--strict-compiler-only", action="store_true",
        help="forbid on-demand fallback and consume ready compiler pairs directly",
    )
    parser.add_argument("--validate-only", action="store_true",
                        help="validate and print the resolved experiment without simulating")
    parser.add_argument(
        "--contract-seed-limit", type=int,
        help="run a non-publishable prefix of contract seeds for physical validation",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if bool(args.contract) != bool(args.profile):
        parser.error("--contract and --profile must be supplied together")
    contract = None
    contract_profile = None
    contract_hash = None
    strict_compiler_only = args.strict_compiler_only
    if args.contract:
        controlled = {
            "--mesh", "--strategies", "--seeds", "--compiler-memories",
            "--total-memories", "--generation-capacity", "--memory-allocation",
            "--on-demand-memories", "--delta-layers",
            "--dynamic-lookahead-layers", "--dynamic-min-lead-layers",
            "--coherence-time-layers", "--fidelity-threshold",
            "--pregeneration-buffer-ms",
            "--compiler-reservation-ms", "--request-duration-ms",
            "--stop-time-s", "--max-layers", "--configuration-name",
            "--strict-compiler-only",
        }
        conflicts = sorted(name for name in controlled if any(
            token == name or token.startswith(name + "=") for token in sys.argv[1:]
        ))
        if conflicts:
            parser.error(
                "contract-controlled options cannot be supplied explicitly: "
                + ", ".join(conflicts)
            )
        try:
            contract = load_contract(args.contract)
            contract_profile = select_profile(contract, args.profile)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            parser.error(f"invalid experiment contract: {error}")
        contract_hash = contract_sha256(args.contract)
        workload = contract["workload"]
        replications = contract["replications"]
        scheduler = contract["scheduler"]
        runtime = contract["runtime_overrides"]["ace"]
        policy_names = {
            "full-odg": "on-demand",
            "matched-odg": "matched-on-demand",
            "fixed": "fixed",
            "dynamic": "dynamic",
        }
        args.mesh = workload["mesh"]
        args.seeds = ",".join(str(seed) for seed in range(
            replications["seed_start"],
            replications["seed_start"] + replications["seed_count"],
        ))
        args.strategies = ",".join(
            policy_names[policy] for policy in contract_profile["policies"]
        )
        args.total_memories = contract_profile["total_entanglement_memories_per_core"]
        args.compiler_memories = contract_profile["compiler_memories_per_core"]
        args.memory_allocation = contract_profile.get(
            "memory_allocation",
            "shared" if contract_profile["id"] == "full-odg-4" else "static",
        )
        args.on_demand_memories = (
            contract_profile["on_demand_memories_per_core"]
            if args.memory_allocation == "static" else None
        )
        args.generation_capacity = args.compiler_memories
        args.delta_layers = scheduler["fixed_delta_layers"]
        args.dynamic_lookahead_layers = scheduler["dynamic_lookahead_layers"]
        args.dynamic_min_lead_layers = scheduler["dynamic_minimum_lead_layers"]
        args.coherence_time_layers = scheduler["coherence_time_layers"]
        args.fidelity_threshold = runtime["fidelity_threshold"]
        args.pregeneration_buffer_ms = runtime["pregeneration_buffer_ms"]
        args.compiler_reservation_ms = runtime["compiler_reservation_ms"]
        args.request_duration_ms = runtime["request_duration_ms"]
        args.stop_time_s = runtime["stop_time_s"]
        strict_compiler_only = (
            contract_profile.get("execution_mode") == "strict-compiler-only"
        )
        if _sha256(args.config) != runtime["topology_config_sha256"]:
            parser.error("ACE topology config SHA-256 does not match experiment contract")
        if args.contract_seed_limit is not None:
            if not 1 <= args.contract_seed_limit <= replications["seed_count"]:
                parser.error("--contract-seed-limit must be within the contract seed count")
            args.seeds = ",".join(str(seed) for seed in range(
                replications["seed_start"],
                replications["seed_start"] + args.contract_seed_limit,
            ))
    elif args.contract_seed_limit is not None:
        parser.error("--contract-seed-limit requires --contract")
    if args.compiler_reservation_ms <= 0:
        parser.error("--compiler-reservation-ms must be positive")
    if args.memory_allocation == "static":
        if args.on_demand_memories is None:
            parser.error("--on-demand-memories is required for static allocation")
        if args.compiler_memories + args.on_demand_memories != args.total_memories:
            parser.error("static compiler + on-demand memories must equal total memories")
        if args.compiler_memories < 1 or args.on_demand_memories < 0:
            parser.error("static allocation requires a nonempty compiler bank")
        if args.on_demand_memories == 0 and not strict_compiler_only:
            parser.error("zero on-demand memories requires --strict-compiler-only")
    elif args.on_demand_memories is not None:
        parser.error("--on-demand-memories is only valid with static allocation")
    if strict_compiler_only and set(item.strip() for item in args.strategies.split(",")) - {"fixed", "dynamic"}:
        parser.error("strict compiler-only execution supports fixed and dynamic strategies only")

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
    source_trace_layers = trace.layer_count
    conflict_serialization = None
    minimum_layer_duration_ps = None
    if contract is not None:
        try:
            validate_workload(
                contract, trace_sha256=_sha256(args.trace), mesh=args.mesh,
                cores=trace.core_count, logical_qubits=trace.qubit_count,
                layers=trace.layer_count, requests=len(trace.requests),
            )
        except ValueError as error:
            parser.error(str(error))
        request_layers, batches, _ = serialize_conflict_layers(
            trace.requests, trace.layer_count
        )
        serialization_hash = serialization_sha256(request_layers)
        if (len(batches) != contract["workload"]["serialized_sublayers"]
                or serialization_hash != contract["workload"]["serialization_map_sha256"]):
            parser.error("conflict serialization does not match experiment contract")
        trace = replace(
            trace,
            requests=tuple(replace(request, layer=request_layers[request.request_id])
                           for request in trace.requests),
            layer_count=len(batches),
        )
        conflict_serialization = {
            "method": contract["timing"]["conflict_serialization"],
            "source_layers": source_trace_layers,
            "serialized_sublayers": len(batches),
            "request_layer_map_sha256": serialization_hash,
        }
        minimum_layer_duration_ps = contract["timing"]["logical_layer_duration_ps"]
    layers = to_ace_layers(trace, columns=columns, fidelity=args.fidelity_threshold)
    strategies = _csv_values(args.strategies)
    invalid = set(strategies) - {"on-demand", "matched-on-demand", "fixed", "dynamic"}
    if invalid:
        parser.error(f"unknown strategies: {', '.join(sorted(invalid))}")
    if args.configuration_name and len(strategies) != 1:
        parser.error(
            "--configuration-name requires exactly one strategy so aggregate "
            "configuration labels remain unique"
        )
    try:
        seeds = [int(seed) for seed in _csv_values(args.seeds)]
    except ValueError:
        parser.error("--seeds must be a comma-separated list of integers")

    if args.validate_only:
        print(json.dumps({
            "valid": True,
            "trace_sha256": _sha256(args.trace),
            "contract_sha256": contract_hash,
            "study_id": contract.get("study_id") if contract else None,
            "profile": args.profile,
            "strategies": strategies,
            "seeds": seeds,
            "mesh": args.mesh,
            "memory_allocation": args.memory_allocation,
            "total_memories": args.total_memories,
            "compiler_memories": args.compiler_memories,
            "on_demand_memories": (
                args.on_demand_memories if args.memory_allocation == "static"
                else args.total_memories
            ),
            "generation_capacity": args.generation_capacity,
            "conflict_serialization": conflict_serialization,
            "minimum_layer_duration_ps": minimum_layer_duration_ps,
            "contract_replications_complete": (
                args.contract_seed_limit is None if contract else None
            ),
        }, indent=2))
        return

    args.output.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    run_outputs = []
    for seed in seeds:
        for strategy in strategies:
            scheduler_strategy = (
                "on-demand" if strategy in {"on-demand", "matched-on-demand"} else strategy
            )
            schedule, blocked, peak = plan_preparations(
                trace,
                strategy=scheduler_strategy,
                compiler_memories_per_core=args.compiler_memories,
                generation_capacity_per_core=args.generation_capacity,
                coherence_time_layers=args.coherence_time_layers,
                delta_layers=args.delta_layers,
                dynamic_lookahead_layers=args.dynamic_lookahead_layers,
                dynamic_min_lead_layers=args.dynamic_min_lead_layers,
            )
            compiler_limit = (
                0 if strategy in {"on-demand", "matched-on-demand"}
                else args.compiler_memories
            )
            compiler_spec = {
                "requests": trace.requests,
                "schedule": schedule,
                "strategy": scheduler_strategy,
                "columns": columns,
                "planner_blocked": blocked,
                "planner_peak_memory": peak,
                "compiler_memories_per_core": compiler_limit,
                "fidelity": args.fidelity_threshold,
                "reservation_duration_ms": args.compiler_reservation_ms,
                "static_compiler_memories": (
                    args.compiler_memories if args.memory_allocation == "static" else None
                ),
                "strict_compiler_only": strict_compiler_only,
            }
            label = f"compiler-{strategy}-seed-{seed}"
            if args.verbose:
                result = run_parallel_experiment(
                    str(args.config), False, False, layers,
                    args.pregeneration_buffer_ms, args.request_duration_ms,
                    label, seed=seed, compiler_spec=compiler_spec,
                    total_memories_per_core=args.total_memories,
                    simulation_stop_time_s=args.stop_time_s,
                    minimum_layer_duration_ps=minimum_layer_duration_ps,
                    strict_compiler_only=strict_compiler_only,
                )
            else:
                with redirect_stdout(StringIO()):
                    result = run_parallel_experiment(
                        str(args.config), False, False, layers,
                        args.pregeneration_buffer_ms, args.request_duration_ms,
                        label, seed=seed, compiler_spec=compiler_spec,
                        total_memories_per_core=args.total_memories,
                        simulation_stop_time_s=args.stop_time_s,
                        minimum_layer_duration_ps=minimum_layer_duration_ps,
                        strict_compiler_only=strict_compiler_only,
                    )

            stats = result["stats"]
            metrics = result["compiler_metrics"]
            row = {
                "configuration": (
                    args.configuration_name
                    or (f"{args.profile}:{strategy}" if args.profile else strategy)
                ),
                "strategy": strategy,
                "seed": seed,
                "total_memories": args.total_memories,
                "compiler_memories": compiler_limit,
                "generation_capacity": args.generation_capacity,
                "memory_allocation": args.memory_allocation,
                "compiler_bank_memories": (
                    args.compiler_memories if args.memory_allocation == "static" else None
                ),
                "on_demand_bank_memories": (
                    args.on_demand_memories if args.memory_allocation == "static"
                    else args.total_memories
                ),
                "strict_compiler_only": strict_compiler_only,
                "strict_compiler_misses": metrics["strict_compiler_misses"],
                "delta_layers": args.delta_layers,
                "dynamic_lookahead_layers": args.dynamic_lookahead_layers,
                "dynamic_min_lead_layers": args.dynamic_min_lead_layers,
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
                "simulator_timing_breakdown": stats.get("timing_breakdown", {}),
                "simulator_layer_latencies_ms": stats.get("layer_latencies", {}),
                "node_seeds": result["node_seeds"],
            })
            print(
                f"{strategy:9} seed={seed} complete={row['completion_rate']:.2%} "
                f"latency={row['average_request_latency_ms']} ms "
                f"pre-ready={row['pregenerated_success_rate'] if row['pregenerated_success_rate'] is not None else 'n/a'} "
                f"expiry={row['compiler_expiry_percentage'] if row['compiler_expiry_percentage'] is not None else 'n/a'}% "
                f"fidelity@use={row['average_compiler_fidelity_at_utilization']}"
            )

    _write_rows(args.output / "summary.csv", summary_rows)
    (args.output / "runs.json").write_text(
        json.dumps({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trace": str(args.trace.resolve()),
            "trace_sha256": _sha256(args.trace),
            "config": str(args.config.resolve()),
            "config_sha256": _sha256(args.config),
            "python": platform.python_version(),
            "mesh": f"{rows}x{columns}",
            "trace_layers": trace.layer_count,
            "source_trace_layers": source_trace_layers,
            "trace_requests": len(trace.requests),
            "conflict_serialization": conflict_serialization,
            "experiment_contract": (
                {
                    "path": str(args.contract.resolve()),
                    "sha256": contract_hash,
                    "study_id": contract["study_id"],
                    "profile": args.profile,
                    "replications_complete": args.contract_seed_limit is None,
                    "validation_seed_limit": args.contract_seed_limit,
                } if contract is not None else None
            ),
            "parameters": {
                "compiler_memories": args.compiler_memories,
                "total_memories": args.total_memories,
                "generation_capacity": args.generation_capacity,
                "memory_allocation": args.memory_allocation,
                "on_demand_memories": args.on_demand_memories,
                "strict_compiler_only": strict_compiler_only,
                "delta_layers": args.delta_layers,
                "dynamic_lookahead_layers": args.dynamic_lookahead_layers,
                "dynamic_min_lead_layers": args.dynamic_min_lead_layers,
                "coherence_time_layers": args.coherence_time_layers,
                "fidelity_threshold": args.fidelity_threshold,
                "pregeneration_buffer_ms": args.pregeneration_buffer_ms,
                "compiler_reservation_ms": args.compiler_reservation_ms,
                "request_duration_ms": args.request_duration_ms,
                "stop_time_s": args.stop_time_s,
                "minimum_layer_duration_ps": minimum_layer_duration_ps,
                "node_seed_scheme": "configured_seed + experiment_seed * 1000003",
                "conflict_serialization": "stable-greedy-selective-bipartite-optimal-v1",
            },
            "runs": run_outputs,
        }, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"Wrote {args.output / 'summary.csv'}")
    print(f"Wrote {args.output / 'runs.json'}")


if __name__ == "__main__":
    main()
