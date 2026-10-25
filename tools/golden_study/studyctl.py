#!/usr/bin/env python3
"""Validate and render the Golden ACE study contract without launching simulations.

The tool deliberately has no hidden experiment defaults.  A run-ready validation
fails until an explicit workload inventory, hashes, and disjoint seed sets exist.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


REGISTRY_COLUMNS = (
    "study_id", "experiment_id", "workload", "mapping_algorithm", "mapping_seed", "physics_seed",
    "topology", "route_policy", "route_parameters", "scheduler_policy", "scheduler_parameters",
    "total_memories_per_core", "compiler_memories_per_core", "trace_path", "trace_sha256",
    "config_sha256", "git_sha", "raw_output_path", "completion_rate", "accepted", "notes",
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_contract(contract: dict[str, Any], *, run_ready: bool) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    budgets = contract.get("memory_experiment", {}).get("total_memories_per_core")
    if not isinstance(budgets, list) or not budgets or any(not isinstance(x, int) or x <= 0 for x in budgets):
        errors.append("memory_experiment.total_memories_per_core must be a non-empty list of positive integers")
    elif budgets != sorted(set(budgets)):
        errors.append("memory capacities must be unique and increasing")
    routes = contract.get("routing", {})
    if routes.get("torus") != ["dijkstra"]:
        errors.append("torus routing must be exactly ['dijkstra'] under the approved study contract")
    policies = contract.get("policy_definitions", {})
    required = {"ODG", "CGP", "ACGP", "Dynamic-full-chain", "Dynamic-first-hop", "Dynamic-congestion-adaptive"}
    missing = required - set(policies)
    if missing:
        errors.append(f"missing required policy definitions: {', '.join(sorted(missing))}")
    if run_ready:
        seeds = contract.get("seeds", {})
        mapping = seeds.get("mapping", [])
        training = seeds.get("physics_training", [])
        evaluation = seeds.get("physics_evaluation", [])
        if not mapping or not training or not evaluation:
            errors.append("run-ready contract requires non-empty mapping, training, and evaluation seed lists")
        if set(training) & set(evaluation):
            errors.append("physics_training and physics_evaluation seeds must be disjoint")
        adaptive = policies.get("Dynamic-congestion-adaptive", {}).get("parameters", {}).get("congestion_threshold")
        if not isinstance(adaptive, int) or adaptive < 0:
            errors.append("run-ready contract requires a non-negative preregistered Dynamic congestion_threshold")
    return errors


def validate_inventory(root: Path, contract: dict[str, Any]) -> list[str]:
    path = root / contract["workloads"]["inventory"]
    if not path.is_file():
        return [f"missing workload inventory: {path}"]
    inventory = read_json(path)
    workloads = inventory.get("workloads")
    if not isinstance(workloads, list):
        return ["workload inventory needs a 'workloads' list"]
    errors: list[str] = []
    if len(workloads) != contract["workloads"]["required_count"]:
        errors.append(f"inventory contains {len(workloads)} workloads; expected {contract['workloads']['required_count']}")
    names: set[str] = set()
    for entry in workloads:
        if not isinstance(entry, dict):
            errors.append("every workload inventory entry must be an object")
            continue
        name, trace, expected = entry.get("id"), entry.get("trace_path"), entry.get("trace_sha256")
        if not isinstance(name, str) or not name:
            errors.append("workload entry missing non-empty id")
        elif name in names:
            errors.append(f"duplicate workload id: {name}")
        else:
            names.add(name)
        if not isinstance(trace, str) or not isinstance(expected, str):
            errors.append(f"workload {name!r} needs trace_path and trace_sha256")
            continue
        trace_path = (root / trace).resolve()
        try:
            trace_path.relative_to(root.resolve())
        except ValueError:
            errors.append(f"workload {name!r} trace path escapes the study root")
            continue
        if not trace_path.is_file():
            errors.append(f"workload {name!r} trace does not exist: {trace}")
        elif sha256(trace_path) != expected:
            errors.append(f"workload {name!r} trace hash does not match inventory")
    return errors


def initialize(root: Path, contract: dict[str, Any]) -> None:
    for name in ("manifests", "traces", "raw", "summaries", "tables", "figures", "validation"):
        (root / name).mkdir(parents=True, exist_ok=True)
    registry = root / "registry.csv"
    if not registry.exists():
        with registry.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=REGISTRY_COLUMNS).writeheader()
    snapshot = root / "manifests" / "study_contract.sha256"
    snapshot.write_text(sha256(root / "study_contract.json") + "  study_contract.json\n", encoding="utf-8")
    print(f"initialized {root} for {contract['study_id']}")


def render_latex(contract: dict[str, Any], target: Path) -> None:
    budgets = ", ".join(str(x) for x in contract["memory_experiment"]["total_memories_per_core"])
    policies = ", ".join(contract["policy_definitions"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "% Generated by tools/golden_study/studyctl.py; do not edit by hand.\n"
        "\\begin{table}[H]\n\\centering\n"
        "\\caption{Golden-study contract at report build time.}\n"
        "\\begin{tabular}{p{0.30\\linewidth}p{0.62\\linewidth}}\n\\toprule\n"
        f"Study identifier & \\texttt{{{contract['study_id']}}} \\\\\n"
        f"Memory capacities/core & {budgets} \\\\\n"
        f"Policies registered & {policies} \\\\\n"
        "Torus routing & Dijkstra only \\\\\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "validate", "render-latex"))
    parser.add_argument("--root", type=Path, required=True, help="Golden-study directory containing study_contract.json")
    parser.add_argument("--run-ready", action="store_true", help="also require seeds, a threshold, and a validated inventory")
    parser.add_argument("--latex-output", type=Path, help="path for generated LaTeX contract table")
    args = parser.parse_args()
    root = args.root.resolve()
    contract_path = root / "study_contract.json"
    contract = read_json(contract_path)
    errors = validate_contract(contract, run_ready=args.run_ready)
    if args.command == "validate" and args.run_ready:
        errors.extend(validate_inventory(root, contract))
    if errors:
        raise SystemExit("study contract validation failed:\n- " + "\n- ".join(errors))
    if args.command == "init":
        initialize(root, contract)
    elif args.command == "validate":
        print(f"valid contract: {contract['study_id']}")
    else:
        if args.latex_output is None:
            raise SystemExit("render-latex needs --latex-output")
        render_latex(contract, args.latex_output)
        print(f"wrote {args.latex_output}")


if __name__ == "__main__":
    main()
