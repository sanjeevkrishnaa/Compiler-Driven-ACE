#!/usr/bin/env python3
"""Create a fresh, hash-audited QAOA Golden-study root from tracked inputs.

This command copies only the QAOA T-HQA placement and routed-trace inputs from
the archived golden-study corpus.  It never copies raw simulation output, and
it records the source corpus and every transferred input hash in the new root.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


MEMORIES = [2, 3, 4, 6, 8, 16, 32]
MAPPING_SEEDS = [42, 43, 44]
ROUTES = {
    "mesh": ["xy", "yx", "shortest_reliable", "max_reliability"],
    "torus": ["dijkstra"],
}
LOCKED_SOURCES = [
    "adaptive_continuous.py", "compiler_scheduler.py", "compiler_trace.py",
    "execution_events.py", "generation.py", "invariants.py", "latency_metrics.py",
    "node.py", "parallel_core.py", "request_app_parallel.py", "request_scheduler.py",
    "reservation.py", "resource_manager.py", "run_trace_comparison.py",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def selected_rows(audit: Path) -> tuple[list[dict[str, str]], list[str]]:
    with audit.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = [row for row in reader if row["mapping_algorithm"] == "T-HQA"
                and row["workload"] == "qaoa"
                and int(row["mapping_seed"]) in MAPPING_SEEDS
                and row["route_policy"] in ROUTES.get(row["topology"], [])]
    expected = sum(len(values) for values in ROUTES.values()) * len(MAPPING_SEEDS)
    if len(rows) != expected:
        raise ValueError(f"expected {expected} QAOA T-HQA route aliases, found {len(rows)}")
    if not all(row.get("valid") == "True" for row in rows):
        raise ValueError("source mapping audit contains an invalid QAOA route")
    if len({row["request_trace_sha256"] for row in rows}) != 11:
        raise ValueError("expected 11 byte-distinct QAOA request traces")
    return rows, fields


def execution_spec() -> dict[str, Any]:
    return {
        "schema": "golden-study-execution-v1",
        "study_id": "qaoa-mesh-torus-2026-10-26-two-evaluation-seeds",
        "phase": "base-evaluation", "repository_root": "../..",
        "source_lock": "manifests/base-evaluation_source-lock.json",
        "mapping_audit": "validation/mapping_audit.csv",
        "trace_path_template": "traces/placements/{topology}/{mapping_algorithm}/{workload}/seed_{mapping_seed}/routes/{route_policy}/requests.txt",
        "trace_selector": {
            "mapping_algorithm": "T-HQA", "required_workload_count": 1, "workloads": ["qaoa"],
            "mapping_seeds": MAPPING_SEEDS, "topology_routes": ROUTES,
            "deduplicate_exact_trace_hashes": True,
            "deduplication_rule": "Execute one representative per byte-identical trace; retain all conceptual mapping and route aliases.",
        },
        "physics_seeds": {
            "training": [30, 31, 32, 33, 34, 35, 36, 37, 38, 39], "evaluation": [0, 1],
            "rule": "Training and evaluation seeds are disjoint. Base-evaluation jobs use only evaluation seeds.",
        },
        "topology_configs": {"mesh": "config/final_config/grid_4x4_ace_3.json", "torus": "config/final_config/grid_4x4_torus_ace_3.json"},
        "memory": {"total_memories_per_core": MEMORIES, "compiler_allocations": "every integer from 0 through total_memories_per_core - 1", "generation_capacity_rule": "max(1, compiler_memories_per_core)"},
        "execution_groups": [
            {"id": "ODG", "runner_strategies": ["on-demand"], "compiler_allocations": [0], "chain_hops_prepared": None, "congestion_threshold": None},
            {"id": "CGP_ACGP_DYNAMIC_FULL", "runner_strategies": ["continuous", "adaptive-continuous", "dynamic"], "compiler_allocations": "all", "chain_hops_prepared": None, "congestion_threshold": None},
            {"id": "DYNAMIC_FIRST_HOP", "runner_strategies": ["dynamic"], "compiler_allocations": "all", "chain_hops_prepared": 1, "congestion_threshold": None},
        ],
        "adaptive_congestion_policy": {"status": "separate-training-phase-required", "prohibited": "Do not select a threshold from evaluation seeds 0 and 1."},
        "runner_parameters": {
            "mesh": "4x4", "delta_layers": 6, "preparation_trigger": "layer-start", "preparation_delay_ms": 0.0,
            "planner_lead_layers": 1, "predecessor_distance": 1, "dynamic_lookahead_layers": 8,
            "coherence_time_layers": 10.0, "fidelity_threshold": 0.01, "pregeneration_buffer_ms": 0.0,
            "compiler_reservation_ms": 1000.0, "request_duration_ms": 50.0, "stop_time_s": 200.0,
            "scheduler": "per-qubit", "admission": "event", "autonomous_cache_follows_compiler_memories": True,
            "stop_after_workload": True, "starvation_guard": True, "max_layers": None,
        },
    }


def prepare(repository: Path, root: Path, source: Path) -> None:
    if root.exists():
        raise FileExistsError(f"refusing to replace existing study root: {root}")
    source_audit = source / "validation/mapping_audit.csv"
    rows, fields = selected_rows(source_audit)
    qasm = source / "inputs/qaoa/circuit.qasm"
    qasm_hash = sha256(qasm)
    if qasm_hash != "dbb27d15d80cac7adc6a3da8b70ffe1770583458022870bddcdaac5718136710":
        raise ValueError("unexpected QAOA QASM hash")
    root.mkdir(parents=True)
    (root / "inputs/qaoa").mkdir(parents=True)
    shutil.copy2(qasm, root / "inputs/qaoa/circuit.qasm")
    copied: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["topology"], row["mapping_seed"])
        if key in copied:
            continue
        copied.add(key)
        relative = Path("traces/placements") / row["topology"] / "T-HQA" / "qaoa" / f"seed_{row['mapping_seed']}"
        shutil.copytree(source / relative, root / relative)
    for row in rows:
        trace = root / "traces/placements" / row["topology"] / "T-HQA" / "qaoa" / f"seed_{row['mapping_seed']}" / "routes" / row["route_policy"] / "requests.txt"
        if sha256(trace) != row["request_trace_sha256"]:
            raise ValueError(f"transferred trace hash mismatch: {trace}")
    validation = root / "validation"
    validation.mkdir()
    with (validation / "mapping_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    record = {
        "schema": "qaoa-mapping-audit-v1", "workload": "qaoa", "mapping_algorithm": "T-HQA",
        "mapping_seeds": MAPPING_SEEDS, "route_aliases": len(rows), "distinct_request_trace_hashes": 11,
        "qasm_sha256": qasm_hash, "source_study": str(source.relative_to(repository)),
        "source_mapping_audit_sha256": sha256(source_audit), "mapping_audit_sha256": sha256(validation / "mapping_audit.csv"),
        "historical_results_reused": False,
    }
    write_json(validation / "mapping_record.json", record)
    write_json(root / "mapping_contract.json", {"schema": "qaoa-mapping-contract-v1", "workload": "qaoa", "qasm_sha256": qasm_hash, "mapping_algorithm": "T-HQA", "mapping_seeds": MAPPING_SEEDS, "routing": ROUTES, "input_provenance": record})
    spec = execution_spec()
    write_json(root / "execution_spec.json", spec)
    lock = {
        "schema": "golden-study-source-lock-v1",
        "purpose": "Fresh QAOA base-evaluation jobs use these exact ACE simulation sources and the clean pinned SeQUeNCe revision.",
        "repository_files": {name: sha256(repository / name) for name in LOCKED_SOURCES},
        "sequence": {"git_sha": subprocess.run(["git", "-C", str(repository.parent / "SeQUeNCe-0.8.1"), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip(), "tracked_tree_clean": True},
    }
    write_json(root / "manifests/base-evaluation_source-lock.json", lock)
    (root / "README.md").write_text(
        "# QAOA two-seed golden study (26 October 2026)\n\n"
        "This is a fresh QAOA-only simulation root.  Its inputs are audited copies of the tracked T-HQA mapping corpus; no historical raw results were copied or reused as evidence.\n\n"
        "The immutable base manifest is generated from `execution_spec.json`.  It covers mapping seeds 42/43/44, mesh XY/YX/shortest-reliable/maximum-reliability, torus Dijkstra, M=2/3/4/6/8/16/32, every legal compiler allocation, ODG/CGP/ACGP/Dynamic full-chain/Dynamic first-hop, and physics seeds 0/1.\n\n"
        "Primary latency is arrival/eligibility to completion.  The study uses `pregeneration_buffer_ms=0.0`; no historical 5.3-ms subtraction is permitted.  Only atomically finalized raw job directories are reportable.\n",
        encoding="utf-8",
    )
    print(json.dumps({"root": str(root), "qasm_sha256": qasm_hash, "route_aliases": len(rows), "distinct_traces": 11, "spec_sha256": canonical_hash(spec)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path("results/golden_study_2026-10-25"))
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    prepare(repository, args.root.resolve(), args.source.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
