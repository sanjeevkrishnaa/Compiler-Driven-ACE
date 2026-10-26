#!/usr/bin/env python3
"""Build an immutable, hash-checked ACE execution manifest.

All scientific choices come from ``execution_spec.json``.  This module expands
them, validates the current mapper audit and source files, and groups only
runner strategies that share every command-line parameter.  Exact trace-hash
deduplication preserves all conceptual aliases in every generated job.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def inside(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the study root: {relative}") from exc
    return path


def repository_root(root: Path, spec: dict[str, Any]) -> Path:
    relative = spec.get("repository_root")
    if not isinstance(relative, str) or not relative:
        raise ValueError("execution spec needs an explicit repository_root")
    repository = (root / relative).resolve()
    try:
        root.resolve().relative_to(repository)
    except ValueError as exc:
        raise ValueError("study root must be located inside repository_root") from exc
    return repository


def _nonnegative_unique(values: Any, label: str) -> list[int]:
    if not isinstance(values, list) or not values or any(not isinstance(v, int) or v < 0 for v in values):
        raise ValueError(f"{label} must be a non-empty list of non-negative integers")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")
    return values


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("schema") != "golden-study-execution-v1":
        raise ValueError("execution spec needs schema golden-study-execution-v1")
    selector = spec.get("trace_selector")
    if not isinstance(selector, dict) or not isinstance(selector.get("mapping_algorithm"), str):
        raise ValueError("trace_selector needs an explicit mapping_algorithm")
    _nonnegative_unique(selector.get("mapping_seeds"), "trace_selector.mapping_seeds")
    routes = selector.get("topology_routes")
    if not isinstance(routes, dict) or not routes:
        raise ValueError("topology_routes must be a non-empty object")
    if "torus" in routes and routes["torus"] != ["dijkstra"]:
        raise ValueError("topology_routes must use only dijkstra for torus")
    required_workloads = selector.get("required_workload_count")
    if not isinstance(required_workloads, int) or required_workloads < 1:
        raise ValueError("trace_selector.required_workload_count must be positive")
    workloads = selector.get("workloads")
    if workloads is not None:
        if (not isinstance(workloads, list) or not workloads
                or any(not isinstance(v, str) or not v for v in workloads)
                or len(set(workloads)) != len(workloads)):
            raise ValueError("trace_selector.workloads must be a unique non-empty list of names")
        if len(workloads) != required_workloads:
            raise ValueError("trace_selector.workloads must match required_workload_count")
    seeds = spec.get("physics_seeds")
    if not isinstance(seeds, dict):
        raise ValueError("physics_seeds must be an object")
    training = _nonnegative_unique(seeds.get("training"), "physics_seeds.training")
    evaluation = _nonnegative_unique(seeds.get("evaluation"), "physics_seeds.evaluation")
    if set(training) & set(evaluation):
        raise ValueError("training and evaluation physics seeds must be disjoint")
    memories = spec.get("memory", {}).get("total_memories_per_core")
    if not isinstance(memories, list) or not memories or memories != sorted(set(memories)) or any(not isinstance(v, int) or v < 1 for v in memories):
        raise ValueError("total memories must be a unique increasing positive-integer list")
    if spec["memory"].get("generation_capacity_rule") != "max(1, compiler_memories_per_core)":
        raise ValueError("unsupported generation_capacity_rule")
    groups = spec.get("execution_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("execution_groups must be a non-empty list")
    ids: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("id"), str) or group["id"] in ids:
            raise ValueError("execution group ids must be non-empty and unique")
        ids.add(group["id"])
        strategies = group.get("runner_strategies")
        if not isinstance(strategies, list) or not strategies or any(v not in {"on-demand", "continuous", "adaptive-continuous", "dynamic"} for v in strategies):
            raise ValueError(f"execution group {group['id']} has invalid runner_strategies")
        allocations = group.get("compiler_allocations")
        if allocations != "all" and (not isinstance(allocations, list) or any(not isinstance(v, int) or v < 0 for v in allocations)):
            raise ValueError(f"execution group {group['id']} has invalid compiler_allocations")
    required_runner = {
        "mesh", "delta_layers", "preparation_trigger", "preparation_delay_ms",
        "planner_lead_layers", "predecessor_distance", "dynamic_lookahead_layers",
        "coherence_time_layers", "fidelity_threshold", "pregeneration_buffer_ms",
        "compiler_reservation_ms", "request_duration_ms", "stop_time_s", "scheduler",
        "admission", "autonomous_cache_follows_compiler_memories", "stop_after_workload",
        "starvation_guard", "max_layers",
    }
    runner = spec.get("runner_parameters")
    if not isinstance(runner, dict) or set(runner) != required_runner:
        missing = required_runner - set(runner or {})
        extra = set(runner or {}) - required_runner
        raise ValueError(f"runner_parameters mismatch; missing={sorted(missing)}, extra={sorted(extra)}")


def selected_traces(root: Path, spec: dict[str, Any]) -> list[dict[str, Any]]:
    audit_path = inside(root, spec["mapping_audit"], "mapping_audit")
    selector = spec["trace_selector"]
    seeds = set(selector["mapping_seeds"])
    routes = selector["topology_routes"]
    selected_workloads = set(selector.get("workloads", []))
    selected: list[dict[str, Any]] = []
    with audit_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            topology = row["topology"]
            if (row["mapping_algorithm"] != selector["mapping_algorithm"]
                    or int(row["mapping_seed"]) not in seeds
                    or (selected_workloads and row["workload"] not in selected_workloads)
                    or row["route_policy"] not in routes.get(topology, ())):
                continue
            fields = {
                "topology": topology,
                "mapping_algorithm": row["mapping_algorithm"],
                "workload": row["workload"],
                "mapping_seed": int(row["mapping_seed"]),
                "route_policy": row["route_policy"],
            }
            relative = spec["trace_path_template"].format(**fields)
            trace = inside(root, relative, "request trace")
            expected = row["request_trace_sha256"]
            if not trace.is_file() or sha256(trace) != expected:
                raise ValueError(f"trace missing or hash-mismatched: {relative}")
            selected.append({**fields, "trace_path": relative, "trace_sha256": expected})
    expected_aliases = len(seeds) * sum(len(values) for values in routes.values()) * selector["required_workload_count"]
    if len(selected) != expected_aliases:
        raise ValueError(f"selected {len(selected)} route aliases; expected {expected_aliases}")
    return selected


def trace_groups(rows: Iterable[dict[str, Any]], deduplicate: bool) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = row["trace_sha256"] if deduplicate else canonical_hash(row)
        groups[key].append(row)
    return [sorted(values, key=lambda r: (r["topology"], r["workload"], r["route_policy"], r["mapping_seed"])) for _, values in sorted(groups.items())]


def expand(root: Path, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_spec(spec)
    repository = repository_root(root, spec)
    aliases = selected_traces(root, spec)
    grouped = trace_groups(aliases, bool(spec["trace_selector"].get("deduplicate_exact_trace_hashes")))
    jobs: list[dict[str, Any]] = []
    seeds = spec["physics_seeds"]["evaluation"]
    for trace_aliases in grouped:
        representative = trace_aliases[0]
        config = inside(repository, spec["topology_configs"][representative["topology"]], "topology config")
        if not config.is_file():
            raise ValueError(f"missing topology config: {config}")
        for total in spec["memory"]["total_memories_per_core"]:
            for execution_group in spec["execution_groups"]:
                requested = execution_group["compiler_allocations"]
                allocations = range(total) if requested == "all" else requested
                for compiler in allocations:
                    if compiler >= total:
                        raise ValueError(f"compiler allocation {compiler} is not below total memory {total}")
                    definition = {
                        "schema": "golden-study-run-job-v1",
                        "study_id": spec["study_id"],
                        "phase": spec["phase"],
                        "execution_group": execution_group["id"],
                        "runner_strategies": execution_group["runner_strategies"],
                        "trace_path": representative["trace_path"],
                        "trace_sha256": representative["trace_sha256"],
                        "trace_aliases": trace_aliases,
                        "config_path": str(config.relative_to(repository)),
                        "config_sha256": sha256(config),
                        "topology": representative["topology"],
                        "route_policy": representative["route_policy"],
                        "total_memories_per_core": total,
                        "compiler_memories_per_core": compiler,
                        "generation_capacity_per_core": max(1, compiler),
                        "chain_hops_prepared": execution_group["chain_hops_prepared"],
                        "congestion_threshold": execution_group["congestion_threshold"],
                        "physics_seeds": seeds,
                        "runner_parameters": spec["runner_parameters"],
                    }
                    job_id = canonical_hash(definition)[:24]
                    jobs.append({"job_id": job_id, "output_path": f"raw/{spec['phase']}/{job_id}", **definition})
    jobs.sort(key=lambda job: job["job_id"])
    simulation_count = sum(len(job["runner_strategies"]) * len(job["physics_seeds"]) for job in jobs)
    route_counts: dict[str, dict[str, int]] = {}
    for topology, policies in spec["trace_selector"]["topology_routes"].items():
        for policy in policies:
            matching = [row for row in aliases if row["topology"] == topology and row["route_policy"] == policy]
            route_counts[f"{topology}:{policy}"] = {
                "conceptual_aliases": len(matching),
                "distinct_trace_hashes": len({row["trace_sha256"] for row in matching}),
            }
    summary = {
        "schema": "golden-study-execution-plan-v1",
        "study_id": spec["study_id"],
        "phase": spec["phase"],
        "execution_spec_sha256": canonical_hash(spec),
        "mapping_audit_sha256": sha256(inside(root, spec["mapping_audit"], "mapping_audit")),
        "conceptual_trace_aliases": len(aliases),
        "distinct_trace_hashes": len(grouped),
        "runner_jobs": len(jobs),
        "simulator_policy_seed_evaluations": simulation_count,
        "physics_seed_count": len(seeds),
        "route_trace_counts": route_counts,
        "job_manifest": f"manifests/{spec['phase']}_jobs.jsonl.gz",
    }
    summary["plan_sha256"] = canonical_hash({"summary": summary, "jobs": jobs})
    return jobs, summary


def write_latex(path: Path, summary: dict[str, Any]) -> None:
    rows = [
        ("Conceptual T-HQA route aliases", f"{summary['conceptual_trace_aliases']:,}"),
        ("Distinct request-trace hashes", f"{summary['distinct_trace_hashes']:,}"),
        ("Resumable runner jobs", f"{summary['runner_jobs']:,}"),
        ("Paired evaluation physics seeds", f"{summary['physics_seed_count']:,}"),
        ("Policy-seed simulator evaluations", f"{summary['simulator_policy_seed_evaluations']:,}"),
    ]
    body = [
        "% Generated by tools/golden_study/plan_execution.py; do not edit by hand.",
        "\\begin{table}[H]", "\\centering", "\\small",
        "\\caption{Frozen base-evaluation execution plan. The adaptive-congestion policy is trained separately before evaluation.}",
        "\\label{tab:golden-execution-plan}", "\\begin{tabular}{lr}", "\\toprule",
        "Quantity & Count \\\\", "\\midrule",
    ]
    body.extend(f"{label} & {value} \\\\" for label, value in rows)
    body.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")


def write_plan(root: Path, spec: dict[str, Any]) -> tuple[Path, Path, dict[str, Any]]:
    jobs, summary = expand(root, spec)
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    jobs_path = manifests / f"{spec['phase']}_jobs.jsonl.gz"
    payload = "".join(json.dumps(job, sort_keys=True) + "\n" for job in jobs).encode()
    with jobs_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
            handle.write(payload)
    summary_path = manifests / f"{spec['phase']}_plan.json"
    summary["job_manifest_sha256"] = sha256(jobs_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return jobs_path, summary_path, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, help="defaults to <root>/execution_spec.json")
    parser.add_argument("--latex-output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    spec = read_json((args.spec or root / "execution_spec.json").resolve())
    jobs, plan, summary = write_plan(root, spec)
    if args.latex_output is not None:
        write_latex(args.latex_output.resolve(), summary)
    print(f"wrote {jobs}")
    print(f"wrote {plan}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.latex_output is not None:
        print(f"wrote {args.latex_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
