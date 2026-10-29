#!/usr/bin/env python3
"""Generate fresh, validated mapper placements and ACE route traces.

Every value that changes a mapping is read from ``mapping_jobs.json``.  This
module has no fallback circuit list, seed range, placement algorithm, topology,
or route policy.  It is intentionally separate from ACE execution: a placement
is generated once, made immutable by hash, then every scheduler sees precisely
the same derived adjacent-hop trace.

``--plan`` is dependency-free and prints the exact units that would be mapped.
``--execute`` requires the mapper's optional QASM dependency (pytket) and fails
before writing partial mappings if it is unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ensure_relative(root: Path, value: str, label: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes study root: {value}") from exc
    return candidate


def validate_jobs(root: Path, jobs: dict[str, Any]) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    if jobs.get("schema") != "golden-study-mapping-jobs-v1":
        raise ValueError("mapping jobs needs schema golden-study-mapping-jobs-v1")
    inputs_path = ensure_relative(root, jobs.get("input_manifest", ""), "input_manifest")
    inputs = read_json(inputs_path).get("inputs")
    if not isinstance(inputs, list):
        raise ValueError("input manifest needs an inputs list")
    indexed: dict[str, dict[str, str]] = {}
    for row in inputs:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("id", "qasm_path", "qasm_sha256")):
            raise ValueError("input manifest has an invalid input record")
        if row["id"] in indexed:
            raise ValueError(f"duplicate input workload {row['id']!r}")
        qasm = ensure_relative(root, row["qasm_path"], f"QASM for {row['id']}")
        if not qasm.is_file() or sha256(qasm) != row["qasm_sha256"]:
            raise ValueError(f"QASM hash mismatch for {row['id']!r}; rerun prepare_inputs")
        indexed[row["id"]] = {k: row[k] for k in ("id", "qasm_path", "qasm_sha256")}

    architecture = jobs.get("architecture")
    algorithms = jobs.get("mapping_algorithms")
    mapping_seeds = jobs.get("mapping_seeds")
    routes = jobs.get("routing")
    required_architecture = {"grid", "data_qubits_per_core", "reserved_ancilla", "initial_placement", "reliability_min", "reliability_max", "seed_derivation"}
    if not isinstance(architecture, dict) or required_architecture - architecture.keys():
        raise ValueError("mapping jobs architecture is incomplete")
    if not isinstance(algorithms, list) or not algorithms or not all(isinstance(v, str) and v for v in algorithms):
        raise ValueError("mapping_algorithms must be a non-empty string list")
    if len(set(algorithms)) != len(algorithms):
        raise ValueError("mapping_algorithms must not contain duplicates")
    if not isinstance(mapping_seeds, list) or not mapping_seeds or not all(isinstance(v, int) and v >= 0 for v in mapping_seeds):
        raise ValueError("mapping_seeds must be a non-empty list of non-negative integers")
    if len(set(mapping_seeds)) != len(mapping_seeds):
        raise ValueError("mapping_seeds must not contain duplicates")
    if not isinstance(routes, dict) or not routes:
        raise ValueError("routing must be a non-empty object")
    units: list[dict[str, Any]] = []
    selected = jobs.get("workloads", sorted(indexed))
    if not isinstance(selected, list) or not selected or not all(isinstance(v, str) and v in indexed for v in selected):
        raise ValueError("workloads must name inputs from the input manifest")
    if len(set(selected)) != len(selected):
        raise ValueError("workloads must not contain duplicates")
    for topology, policies in routes.items():
        if topology not in {"mesh", "torus"}:
            raise ValueError(f"unsupported mapping topology {topology!r}")
        if not isinstance(policies, list) or not policies or not all(isinstance(v, str) and v for v in policies):
            raise ValueError(f"routing.{topology} must be a non-empty string list")
        if topology == "torus" and policies != ["dijkstra"]:
            raise ValueError("torus policy must be exactly ['dijkstra']")
        for workload in selected:
            for algorithm in algorithms:
                for seed in mapping_seeds:
                    units.append({"workload": workload, "algorithm": algorithm, "seed": seed, "topology": topology, "routes": policies})
    return indexed, units


def print_plan(units: list[dict[str, Any]]) -> None:
    print(f"mapping units: {len(units)}")
    for unit in units:
        print("{topology} {algorithm} {workload} seed={seed} routes={routes}".format(**unit))


def require_mapper() -> None:
    try:
        import qmap  # noqa: F401
        from qmap.circuit.loader import load_qasm  # noqa: F401
        from pytket import qasm  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "mapping execution needs qmap on PYTHONPATH and its optional QASM parser dependency pytket; "
            "use --plan to inspect jobs without executing them"
        ) from exc


def mapper_seed(seed: int, workload: str, topology: str, grid: str, derivation: str):
    from qmap.rng import SeedSequence
    root = SeedSequence.from_seed(seed)
    if derivation == "mapper-cli-trial-v1":
        return root.for_trial(workload, topology, grid, 0)
    if derivation == "root-seed-v1":
        return root
    raise ValueError(f"unsupported explicit seed_derivation {derivation!r}")


def map_one(root: Path, jobs: dict[str, Any], input_row: dict[str, str], unit: dict[str, Any]) -> list[Path]:
    from qmap.architecture.reliability import ReliabilityBand
    from qmap.circuit.loader import load_qasm
    from qmap.experiments.runner import prepare_trial, run_trial
    from qmap.placement.base import PlacerConfig
    from qmap.validation import validate_partition
    from tools.mapper_ace.export import export
    from tools.mapper_ace.placement_contract import contract

    architecture = jobs["architecture"]
    grid = architecture["grid"]
    topology = unit["topology"]
    workload = unit["workload"]
    qasm = ensure_relative(root, input_row["qasm_path"], f"QASM for {workload}")
    target = root / "traces" / "placements" / topology / unit["algorithm"] / workload / f"seed_{unit['seed']}"
    contract_path = target / "placement.json"
    if target.exists():
        raise FileExistsError(
            f"refusing to replace existing mapping {target}; Golden-study artifacts are immutable. "
            "Create a new study root for a changed mapping job."
        )
    circuit = load_qasm(qasm)
    if circuit.name != qasm.stem:
        raise ValueError(f"mapper loaded unexpected circuit name {circuit.name!r} for {qasm}")
    seed = mapper_seed(unit["seed"], workload, topology, grid, architecture["seed_derivation"])
    band = ReliabilityBand(float(architecture["reliability_min"]), float(architecture["reliability_max"]))
    setup = prepare_trial(
        grid=grid,
        benchmark=workload,
        seed=seed,
        reliability_band=band,
        qubits_per_core=int(architecture["data_qubits_per_core"]),
        reserved_ancilla=int(architecture["reserved_ancilla"]),
        topology=topology,
        circuit=circuit,
    )
    result = run_trial(
        setup,
        unit["algorithm"],
        PlacerConfig(initial_placement=str(architecture["initial_placement"]), strict=True),
        benchmark=workload,
        reliability_band=band.label,
        keep_partition=True,
    )
    if result.partition is None:
        raise RuntimeError("mapper did not retain its placement partition")
    validation = validate_partition(result.partition, setup.sliced, setup.architecture)
    if not validation.is_complete:
        raise RuntimeError(f"mapper left {validation.uncolocated_operations} two-qubit operations unplaced")
    target.mkdir(parents=True, exist_ok=False)
    payload = contract(
        result.partition,
        dimensions=tuple(int(v) for v in setup.architecture.dimensions),
        qubits_per_core=int(architecture["data_qubits_per_core"]),
        seed=unit["seed"],
        reliability_min=float(architecture["reliability_min"]),
        reliability_max=float(architecture["reliability_max"]),
        topology=topology,
        provenance={
            "kind": "golden-study-fresh-mapper",
            "mapper_partition_exact": True,
            "workload": workload,
            "qasm_path": input_row["qasm_path"],
            "qasm_sha256": input_row["qasm_sha256"],
            "mapping_algorithm": result.placer,
            "mapping_record": result.as_record(),
            "mapping_configuration": {
                "architecture": architecture,
                "configuration_sha256": canonical_hash(architecture),
            },
            "validation": {
                "maximum_data_occupancy": validation.max_occupancy,
                "uncolocated_operations": validation.uncolocated_operations,
            },
        },
    )
    contract_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    outputs = [contract_path]
    for policy in unit["routes"]:
        route_output = target / "routes" / policy
        manifest = export(contract_path, route_output, policy)
        manifest["golden_study"] = {
            "mapping_job_sha256": canonical_hash({"architecture": architecture, "unit": unit}),
            "placement_contract_sha256": sha256(contract_path),
            "input_qasm_sha256": input_row["qasm_sha256"],
        }
        (route_output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        outputs.extend([route_output / "migrations.jsonl", route_output / "requests.txt", route_output / "manifest.json"])
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, help="defaults to <root>/mapping_jobs.json")
    parser.add_argument("--plan", action="store_true", help="validate and list jobs without importing qmap")
    parser.add_argument("--execute", action="store_true", help="generate fresh placement and route artifacts")
    args = parser.parse_args()
    if args.plan == args.execute:
        raise SystemExit("choose exactly one of --plan or --execute")
    root = args.root.resolve()
    jobs = read_json((args.jobs or root / "mapping_jobs.json").resolve())
    inputs, units = validate_jobs(root, jobs)
    if args.plan:
        print_plan(units)
        return 0
    require_mapper()
    for index, unit in enumerate(units, start=1):
        print(f"[{index}/{len(units)}] mapping {unit['topology']} {unit['algorithm']} {unit['workload']} seed={unit['seed']}", flush=True)
        outputs = map_one(root, jobs, inputs[unit["workload"]], unit)
        print(f"  wrote {len(outputs)} artifacts", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
