#!/usr/bin/env python3
"""Run the registered Dynamic launch-policy variants on the QFT-96 route corpus.

This is a separate phase from the frozen base matrix.  It uses the same QFT-96
trace hashes, topology configurations, physical timing, and evaluation seeds,
but varies only the Dynamic preparation trigger/delay/chain-depth rule.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .plan_execution import canonical_hash, read_json, sha256
from .run_execution import read_jobs, repository_root, sequence_identity, verify_sequence_lock, verify_source_lock


VARIANTS: dict[str, dict[str, Any]] = {
    "baseline-layer-start": {},
    "layer-delay-1ms": {"preparation_delay_ms": 1.0},
    "layer-delay-2ms": {"preparation_delay_ms": 2.0},
    "layer-delay-3ms": {"preparation_delay_ms": 3.0},
    "layer-delay-4ms": {"preparation_delay_ms": 4.0},
    "layer-delay-6ms": {"preparation_delay_ms": 6.0},
    "predecessor-start": {"preparation_trigger": "predecessor-start"},
    "predecessor-start-first-delay-2ms": {"preparation_trigger": "predecessor-start", "preparation_delay_ms": 2.0},
    "predecessor-start-first-delay-4ms": {"preparation_trigger": "predecessor-start", "preparation_delay_ms": 4.0},
    "first-hop-only": {"chain_hops_prepared": 1},
    "first-hop-only-delay-2ms": {"chain_hops_prepared": 1, "preparation_delay_ms": 2.0},
    "first-hop-only-delay-4ms": {"chain_hops_prepared": 1, "preparation_delay_ms": 4.0},
    "two-hops-predecessor-start": {"chain_hops_prepared": 2, "preparation_trigger": "predecessor-start"},
}


def clean_tree(repository: Path) -> bool:
    return subprocess.run(["git", "diff", "--quiet"], cwd=repository).returncode == 0 and subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repository
    ).returncode == 0


def variant_job_hash(job: dict[str, Any]) -> str:
    return canonical_hash(job)


def load_aliases(root: Path) -> list[dict[str, Any]]:
    audit = root / "validation" / "mapping_audit.csv"
    with audit.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    aliases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = row["request_trace_sha256"]
        if key in seen:
            continue
        seen.add(key)
        trace = root / "traces" / "placements" / row["topology"] / row["mapping_algorithm"] / row["workload"]
        trace = trace / f"seed_{row['mapping_seed']}" / "routes" / row["route_policy"] / "requests.txt"
        if not trace.is_file() or sha256(trace) != key:
            raise ValueError(f"route trace missing or hash-mismatched: {trace}")
        aliases.append({
            "topology": row["topology"], "mapping_algorithm": row["mapping_algorithm"],
            "workload": row["workload"], "mapping_seed": int(row["mapping_seed"]),
            "route_policy": row["route_policy"], "trace_path": str(trace.relative_to(root)),
            "trace_sha256": key, "physical_hops": int(row["physical_hops"]),
        })
    if len(aliases) != 11:
        raise ValueError(f"expected 11 distinct QFT-96 trace hashes, found {len(aliases)}")
    return sorted(aliases, key=lambda row: (row["topology"], row["route_policy"], row["mapping_seed"]))


def make_jobs(root: Path, spec: dict[str, Any], aliases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seeds = [int(value) for value in spec["physics_seeds"]["evaluation"]]
    base = dict(spec["runner_parameters"])
    for alias in aliases:
        config = spec["topology_configs"][alias["topology"]]
        config_path = Path(repository_root(root, spec) / config)
        if not config_path.is_file():
            raise ValueError(f"missing topology config: {config_path}")
        for name, overrides in VARIANTS.items():
            params = dict(base)
            params.update({key: value for key, value in overrides.items() if key in params})
            chain_hops = overrides.get("chain_hops_prepared")
            params["total_memories"] = 4
            params["compiler_memories"] = 3
            params["generation_capacity"] = 3
            job = {
                "schema": "qft96-dynamic-variant-job-v1",
                "study_id": spec["study_id"],
                "phase": "dynamic-variants",
                "variant": name,
                "variant_parameters": overrides,
                "runner_parameters": params,
                "topology": alias["topology"],
                "route_policy": alias["route_policy"],
                "mapping_algorithm": alias["mapping_algorithm"],
                "mapping_seed": alias["mapping_seed"],
                "workload": alias["workload"],
                "trace_path": alias["trace_path"],
                "trace_sha256": alias["trace_sha256"],
                "physical_hops": alias["physical_hops"],
                "config_path": str(config_path.relative_to(repository_root(root, spec))),
                "config_sha256": sha256(config_path),
                "physics_seeds": seeds,
                "chain_hops_prepared": chain_hops,
            }
            jobs.append({"job_id": variant_job_hash(job)[:24], "output_path": f"raw/dynamic-variants/{variant_job_hash(job)[:24]}", **job})
    return sorted(jobs, key=lambda row: row["job_id"])


def command_for(python: Path, repository: Path, root: Path, job: dict[str, Any], output: Path) -> list[str]:
    p = job["runner_parameters"]
    cmd = [
        str(python), str(repository / "run_trace_comparison.py"),
        "--trace", str(root / job["trace_path"]), "--config", str(repository / job["config_path"]),
        "--mesh", str(p["mesh"]), "--topology", job["topology"], "--strategies", "dynamic",
        "--seeds", ",".join(map(str, job["physics_seeds"])), "--total-memories", str(p["total_memories"]),
        "--compiler-memories", str(p["compiler_memories"]), "--generation-capacity", str(p["generation_capacity"]),
        "--delta-layers", str(p["delta_layers"]), "--preparation-trigger", str(p["preparation_trigger"]),
        "--preparation-delay-ms", str(p["preparation_delay_ms"]), "--planner-lead-layers", str(p["planner_lead_layers"]),
        "--predecessor-distance", str(p["predecessor_distance"]), "--dynamic-lookahead-layers", str(p["dynamic_lookahead_layers"]),
        "--coherence-time-layers", str(p["coherence_time_layers"]), "--fidelity-threshold", str(p["fidelity_threshold"]),
        "--pregeneration-buffer-ms", str(p["pregeneration_buffer_ms"]), "--compiler-reservation-ms", str(p["compiler_reservation_ms"]),
        "--request-duration-ms", str(p["request_duration_ms"]), "--stop-time-s", str(p["stop_time_s"]),
        "--scheduler", str(p["scheduler"]), "--admission", str(p["admission"]),
    ]
    if job["chain_hops_prepared"] is None:
        cmd.append("--all-chain-hops")
    else:
        cmd.extend(["--chain-hops-prepared", str(job["chain_hops_prepared"])])
    cmd.extend(["--no-congestion-threshold", "--autonomous-cache-follows-compiler-memories", "--stop-after-workload"])
    cmd.append("--starvation-guard" if p["starvation_guard"] else "--no-starvation-guard")
    cmd.append("--all-layers" if p["max_layers"] is None else "--max-layers")
    if p["max_layers"] is not None:
        cmd.append(str(p["max_layers"]))
    cmd.extend(["--output", str(output)])
    return cmd


def validate_output(output: Path, job: dict[str, Any]) -> None:
    summary = output / "summary.csv"
    metadata = output / "metadata.json"
    execution = output / "execution.json"
    if not summary.is_file() or not metadata.is_file() or not execution.is_file():
        raise ValueError(f"incomplete output: {output}")
    with summary.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = {( "dynamic", str(seed)) for seed in job["physics_seeds"]}
    actual = {(row.get("strategy"), row.get("seed")) for row in rows}
    if actual != expected or any(float(row["completion_rate"]) != 1.0 for row in rows):
        raise ValueError(f"invalid dynamic seed rows in {output}")
    record = read_json(execution)
    if record.get("job_sha256") != variant_job_hash(job):
        raise ValueError(f"execution record does not match {job['job_id']}")


def run_one(python: Path, repository: Path, root: Path, job: dict[str, Any], commit: str, sequence: dict[str, Any]) -> tuple[str, str]:
    output = root / job["output_path"]
    if output.exists():
        validate_output(output, job)
        return job["job_id"], "validated-existing"
    trace = root / job["trace_path"]
    if sha256(trace) != job["trace_sha256"]:
        raise ValueError(f"trace hash changed for {job['job_id']}")
    partial = Path(tempfile.mkdtemp(prefix=f"{job['job_id']}.", dir=root / "raw" / ".partial"))
    command = command_for(python, repository, root, job, partial)
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, cwd=repository, capture_output=True, text=True)
    (partial / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (partial / "stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{job['job_id']} failed with {result.returncode}: {result.stderr[-500:]}")
    (partial / "execution.json").write_text(json.dumps({
        "schema": "qft96-dynamic-variant-execution-v1", "job_id": job["job_id"],
        "job_sha256": variant_job_hash(job), "git_sha": commit, "sequence": sequence,
        "command": command, "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_output(partial, job)
    output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, output)
    return job["job_id"], "completed"


def write_manifest(path: Path, jobs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "qft96-dynamic-variant-manifest-v1", "jobs": jobs}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    spec = read_json(root / "execution_spec.json")
    repository = repository_root(root, spec)
    if not clean_tree(repository):
        raise SystemExit("refusing variant execution with tracked changes; commit first")
    # Preserve a virtualenv's executable symlink: resolving it can bypass the
    # environment's site-packages (including SeQUeNCe).
    python = args.python.expanduser()
    if not python.is_absolute():
        python = (Path.cwd() / python).absolute()
    lock = read_json(root / spec["source_lock"])
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, text=True, capture_output=True).stdout.strip()
    verify_source_lock(repository, lock)
    sequence = verify_sequence_lock(python, lock)
    aliases = load_aliases(root)
    jobs = make_jobs(root, spec, aliases)
    manifest = (args.manifest or root / "manifests/dynamic-variants_jobs.json").resolve()
    write_manifest(manifest, jobs)
    print(f"prepared {len(jobs)} variant jobs across {len(aliases)} distinct traces and {len(VARIANTS)} variants")
    if not args.run:
        return 0
    (root / "raw" / ".partial").mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, python, repository, root, job, commit, sequence): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                print(*future.result(), flush=True)
            except Exception as exc:
                failures.append(f"{job['job_id']}: {exc}")
                print(f"FAILED {job['job_id']}: {exc}", flush=True)
    if failures:
        raise SystemExit("variant execution failures:\n- " + "\n- ".join(failures))
    print(f"completed {len(jobs)} variant jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
