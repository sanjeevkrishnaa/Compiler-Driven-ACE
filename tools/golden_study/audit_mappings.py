#!/usr/bin/env python3
"""Validate every fresh Golden-study mapper output and write source tables.

This is intentionally an audit rather than an ACE runner. It verifies that every
job declared in ``mapping_jobs.json`` produced exactly its declared route outputs,
that each route references the immutable placement contract it was derived from,
and that the current QASM corpus hash still matches the contract provenance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .map_inputs import canonical_hash, read_json, sha256, validate_jobs


AUDIT_COLUMNS = (
    "topology", "mapping_algorithm", "workload", "mapping_seed", "route_policy",
    "placement_sha256", "migration_trace_sha256", "request_trace_sha256",
    "logical_migrations", "physical_hops", "timeslices", "qubits", "valid",
)


def write_csv(path: Path, rows: list[dict[str, object]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def placement_signature(payload: dict[str, Any]) -> str:
    return canonical_hash({"initial": payload["initial_assignment"], "assignments": payload["assignments"]})


def audit(root: Path, jobs: dict[str, Any]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    from tools.mapper_ace.placement_contract import build_architecture

    inputs, units = validate_jobs(root, jobs)
    rows: list[dict[str, object]] = []
    partitions: dict[tuple[str, str, str], list[tuple[int, str]]] = defaultdict(list)
    failures: list[str] = []
    for unit in units:
        target = root / "traces" / "placements" / unit["topology"] / unit["algorithm"] / unit["workload"] / f"seed_{unit['seed']}"
        contract_path = target / "placement.json"
        if not contract_path.is_file():
            failures.append(f"missing placement contract: {contract_path.relative_to(root)}")
            continue
        payload = read_json(contract_path)
        provenance = payload.get("provenance", {})
        required = {
            "kind": "golden-study-fresh-mapper", "mapper_partition_exact": True,
            "workload": unit["workload"], "mapping_algorithm": unit["algorithm"],
            "qasm_sha256": inputs[unit["workload"]]["qasm_sha256"],
        }
        for key, expected in required.items():
            if provenance.get(key) != expected:
                failures.append(f"{contract_path.relative_to(root)} has {key!r}={provenance.get(key)!r}; expected {expected!r}")
        if payload.get("topology") != unit["topology"] or payload.get("seed") != unit["seed"]:
            failures.append(f"{contract_path.relative_to(root)} does not match its declared topology/seed")
        route_architecture = build_architecture(
            tuple(int(value) for value in payload["dimensions"]),
            int(payload["qubits_per_core"]),
            int(payload["seed"]),
            float(payload["reliability_min"]),
            float(payload.get("reliability_max", 1.0)),
            str(payload["topology"]),
        )
        signature = placement_signature(payload)
        partitions[(unit["topology"], unit["algorithm"], unit["workload"])].append((unit["seed"], signature))
        for policy in unit["routes"]:
            route = target / "routes" / policy
            manifest_path = route / "manifest.json"
            migration = route / "migrations.jsonl"
            requests = route / "requests.txt"
            if not all(path.is_file() for path in (manifest_path, migration, requests)):
                failures.append(f"missing route artifact for {target.relative_to(root)} policy={policy}")
                continue
            manifest = read_json(manifest_path)
            if manifest.get("routing_policy") != policy:
                failures.append(f"{manifest_path.relative_to(root)} has wrong routing policy")
            if manifest.get("input_sha256") != sha256(contract_path):
                failures.append(f"{manifest_path.relative_to(root)} does not reference its placement hash")
            if manifest.get("golden_study", {}).get("placement_contract_sha256") != sha256(contract_path):
                failures.append(f"{manifest_path.relative_to(root)} lacks matching Golden-study placement hash")
            placement = manifest.get("placement", {})
            records = [json.loads(line) for line in migration.read_text(encoding="utf-8").splitlines() if line]
            if len(records) != placement.get("logical_migrations"):
                failures.append(f"{migration.relative_to(root)} migration count differs from its manifest")
            actual_hops = 0
            for record in records:
                path = record.get("path", [])
                if not path or path[0] != record.get("source_core") or path[-1] != record.get("destination_core"):
                    failures.append(f"{migration.relative_to(root)} has a path endpoint mismatch")
                    break
                for source, destination in zip(path, path[1:], strict=False):
                    if not (0 <= source < route_architecture.n_cores and 0 <= destination < route_architecture.n_cores):
                        failures.append(f"{migration.relative_to(root)} has an out-of-range core")
                        break
                    if not route_architecture.graph.has_edge(
                        route_architecture.coordinate_of(source), route_architecture.coordinate_of(destination)
                    ):
                        failures.append(f"{migration.relative_to(root)} has a non-adjacent hop {source}->{destination}")
                        break
                actual_hops += len(path) - 1
            if actual_hops != placement.get("physical_hops"):
                failures.append(f"{migration.relative_to(root)} hop count differs from its manifest")
            rows.append({
                "topology": unit["topology"], "mapping_algorithm": unit["algorithm"],
                "workload": unit["workload"], "mapping_seed": unit["seed"], "route_policy": policy,
                "placement_sha256": sha256(contract_path), "migration_trace_sha256": sha256(migration),
                "request_trace_sha256": sha256(requests),
                "logical_migrations": placement.get("logical_migrations"), "physical_hops": placement.get("physical_hops"),
                "timeslices": placement.get("timeslices"), "qubits": placement.get("qubits"), "valid": True,
            })
    variation_rows: list[dict[str, object]] = []
    for (topology, algorithm, workload), values in sorted(partitions.items()):
        variation_rows.append({
            "topology": topology, "mapping_algorithm": algorithm, "workload": workload,
            "mapping_seed_count": len(values), "distinct_partition_count": len({signature for _, signature in values}),
            "seed_to_partition_sha256": json.dumps({str(seed): signature for seed, signature in sorted(values)}, sort_keys=True),
        })
    if failures:
        raise ValueError("mapping audit failed:\n- " + "\n- ".join(failures))
    return rows, variation_rows


def write_summary(root: Path, rows: list[dict[str, object]], variation: list[dict[str, object]]) -> tuple[Path, Path]:
    validation = root / "validation"
    write_csv(validation / "mapping_audit.csv", rows, AUDIT_COLUMNS)
    variation_columns = ("topology", "mapping_algorithm", "workload", "mapping_seed_count", "distinct_partition_count", "seed_to_partition_sha256")
    write_csv(validation / "mapping_partition_variation.csv", variation, variation_columns)
    summary: list[dict[str, object]] = []
    groups: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["topology"]), str(row["mapping_algorithm"]), str(row["workload"]), str(row["route_policy"]))].append(row)
    for key, values in sorted(groups.items()):
        migrations = {int(value["logical_migrations"]) for value in values}
        hops = {int(value["physical_hops"]) for value in values}
        summary.append({
            "topology": key[0], "mapping_algorithm": key[1], "workload": key[2], "route_policy": key[3],
            "mapping_seed_count": len(values), "logical_migrations_values": ";".join(map(str, sorted(migrations))),
            "physical_hops_values": ";".join(map(str, sorted(hops))),
        })
    summary_path = validation / "mapping_summary.csv"
    write_csv(summary_path, summary, tuple(summary[0]) if summary else ("topology",))
    return validation / "mapping_audit.csv", summary_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, help="defaults to <root>/mapping_jobs.json")
    args = parser.parse_args()
    root = args.root.resolve()
    jobs = read_json((args.jobs or root / "mapping_jobs.json").resolve())
    rows, variation = audit(root, jobs)
    audit_path, summary_path = write_summary(root, rows, variation)
    print(f"validated {len(rows)} route artifacts")
    print(f"wrote {audit_path}")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
