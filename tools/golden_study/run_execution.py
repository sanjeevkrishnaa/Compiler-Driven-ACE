#!/usr/bin/env python3
"""Execute and validate Golden-study jobs with exact resume semantics.

The launcher never accepts ``summary.csv`` alone as proof of completion.  A
reused output must contain an execution record matching the complete job hash,
trace/config hashes, expected strategy/seed rows, and 100% completion.  Jobs are
written to unique partial directories and atomically promoted only after those
checks pass.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .plan_execution import canonical_hash, read_json, repository_root, sha256


def read_jobs(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        jobs = [json.loads(line) for line in handle if line.strip()]
    if not jobs or any(not isinstance(job, dict) for job in jobs):
        raise ValueError("job manifest must contain JSON objects")
    identifiers = [job.get("job_id") for job in jobs]
    if any(not isinstance(value, str) or not value for value in identifiers) or len(identifiers) != len(set(identifiers)):
        raise ValueError("job ids must be non-empty and unique")
    return jobs


def job_hash(job: dict[str, Any]) -> str:
    return canonical_hash(job)


def _flag(command: list[str], enabled: bool, positive: str, negative: str | None = None) -> None:
    if enabled:
        command.append(positive)
    elif negative is not None:
        command.append(negative)
    else:
        raise ValueError(f"runner has no explicit negative flag for {positive}")


def build_command(python: Path, repository: Path, study_root: Path, job: dict[str, Any], output: Path) -> list[str]:
    parameters = job["runner_parameters"]
    command = [
        str(python), str(repository / "run_trace_comparison.py"),
        "--trace", str(study_root / job["trace_path"]),
        "--config", str(repository / job["config_path"]),
        "--mesh", str(parameters["mesh"]),
        "--topology", str(job["topology"]),
        "--strategies", ",".join(job["runner_strategies"]),
        "--seeds", ",".join(map(str, job["physics_seeds"])),
        "--total-memories", str(job["total_memories_per_core"]),
        "--compiler-memories", str(job["compiler_memories_per_core"]),
        "--generation-capacity", str(job["generation_capacity_per_core"]),
        "--delta-layers", str(parameters["delta_layers"]),
        "--preparation-trigger", str(parameters["preparation_trigger"]),
        "--preparation-delay-ms", str(parameters["preparation_delay_ms"]),
        "--planner-lead-layers", str(parameters["planner_lead_layers"]),
        "--predecessor-distance", str(parameters["predecessor_distance"]),
        "--dynamic-lookahead-layers", str(parameters["dynamic_lookahead_layers"]),
        "--coherence-time-layers", str(parameters["coherence_time_layers"]),
        "--fidelity-threshold", str(parameters["fidelity_threshold"]),
        "--pregeneration-buffer-ms", str(parameters["pregeneration_buffer_ms"]),
        "--compiler-reservation-ms", str(parameters["compiler_reservation_ms"]),
        "--request-duration-ms", str(parameters["request_duration_ms"]),
        "--stop-time-s", str(parameters["stop_time_s"]),
        "--scheduler", str(parameters["scheduler"]),
        "--admission", str(parameters["admission"]),
    ]
    if job["chain_hops_prepared"] is None:
        command.append("--all-chain-hops")
    else:
        command.extend(("--chain-hops-prepared", str(job["chain_hops_prepared"])))
    if job["congestion_threshold"] is None:
        command.append("--no-congestion-threshold")
    else:
        command.extend(("--congestion-threshold", str(job["congestion_threshold"])))
    _flag(command, bool(parameters["autonomous_cache_follows_compiler_memories"]), "--autonomous-cache-follows-compiler-memories")
    _flag(command, bool(parameters["stop_after_workload"]), "--stop-after-workload")
    _flag(command, bool(parameters["starvation_guard"]), "--starvation-guard", "--no-starvation-guard")
    if parameters["max_layers"] is None:
        command.append("--all-layers")
    else:
        command.extend(("--max-layers", str(parameters["max_layers"])))
    command.extend(("--output", str(output)))
    return command


def validate_output(output: Path, job: dict[str, Any], *, require_execution_record: bool) -> None:
    summary_path, metadata_path = output / "summary.csv", output / "metadata.json"
    if not summary_path.is_file() or not metadata_path.is_file():
        raise ValueError(f"incomplete output files in {output}")
    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = {(strategy, str(seed)) for strategy in job["runner_strategies"] for seed in job["physics_seeds"]}
    actual = {(row.get("strategy"), row.get("seed")) for row in rows}
    if len(rows) != len(expected) or actual != expected:
        raise ValueError(f"summary row set does not match job {job['job_id']}")
    bad = [row for row in rows if float(row["completion_rate"]) != 1.0]
    if bad:
        raise ValueError(f"job {job['job_id']} contains {len(bad)} incomplete simulations")
    metadata = read_json(metadata_path)
    arguments = metadata.get("parameters", {})
    checks = {
        "topology": job["topology"],
        "strategies": ",".join(job["runner_strategies"]),
        "seeds": ",".join(map(str, job["physics_seeds"])),
        "total_memories": job["total_memories_per_core"],
        "compiler_memories": job["compiler_memories_per_core"],
        "generation_capacity": job["generation_capacity_per_core"],
        "chain_hops_prepared": job["chain_hops_prepared"],
        "congestion_threshold": job["congestion_threshold"],
    }
    mismatches = {key: (arguments.get(key), expected_value) for key, expected_value in checks.items() if arguments.get(key) != expected_value}
    if mismatches:
        raise ValueError(f"runner metadata differs from job {job['job_id']}: {mismatches}")
    if require_execution_record:
        record = read_json(output / "execution.json")
        if record.get("job_sha256") != job_hash(job):
            raise ValueError(f"execution record does not match job {job['job_id']}")
        if record.get("trace_sha256") != job["trace_sha256"] or record.get("config_sha256") != job["config_sha256"]:
            raise ValueError(f"execution record input hashes differ for job {job['job_id']}")


def verify_inputs(repository: Path, root: Path, job: dict[str, Any]) -> None:
    trace = (root / job["trace_path"]).resolve()
    config = (repository / job["config_path"]).resolve()
    if not trace.is_file() or sha256(trace) != job["trace_sha256"]:
        raise ValueError(f"trace hash mismatch for job {job['job_id']}")
    if not config.is_file() or sha256(config) != job["config_sha256"]:
        raise ValueError(f"config hash mismatch for job {job['job_id']}")


def git_sha(repository: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, text=True, capture_output=True).stdout.strip()


def tracked_tree_clean(repository: Path) -> bool:
    unstaged = subprocess.run(["git", "diff", "--quiet"], cwd=repository).returncode == 0
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repository).returncode == 0
    return unstaged and staged


def run_one(python: Path, repository: Path, root: Path, job: dict[str, Any], commit: str) -> tuple[str, str]:
    verify_inputs(repository, root, job)
    output = root / job["output_path"]
    if output.exists():
        validate_output(output, job, require_execution_record=True)
        return job["job_id"], "validated-existing"
    partial_parent = root / "raw" / ".partial"
    partial_parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(prefix=f"{job['job_id']}.", dir=partial_parent))
    command = build_command(python, repository, root, job, partial)
    started = datetime.now(timezone.utc)
    completed = subprocess.run(command, cwd=repository, text=True, capture_output=True)
    (partial / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (partial / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        (partial / "failed.json").write_text(json.dumps({
            "job_id": job["job_id"], "job_sha256": job_hash(job), "returncode": completed.returncode,
            "command": command, "started_at": started.isoformat(),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(f"job {job['job_id']} failed; evidence retained in {partial}")
    validate_output(partial, job, require_execution_record=False)
    execution = {
        "schema": "golden-study-execution-record-v1",
        "job_id": job["job_id"], "job_sha256": job_hash(job),
        "trace_sha256": job["trace_sha256"], "config_sha256": job["config_sha256"],
        "git_sha": commit, "tracked_tree_clean_at_launch": True,
        "python_executable": str(python),
        "python_version": subprocess.run([str(python), "--version"], check=True, text=True, capture_output=True).stdout.strip(),
        "command": command, "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "stdout_sha256": sha256(partial / "stdout.log"), "stderr_sha256": sha256(partial / "stderr.log"),
    }
    (partial / "execution.json").write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_output(partial, job, require_execution_record=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, output)
    return job["job_id"], "completed"


def select_jobs(jobs: Iterable[dict[str, Any]], job_ids: set[str], limit: int | None) -> list[dict[str, Any]]:
    selected = [job for job in jobs if not job_ids or job["job_id"] in job_ids]
    missing = job_ids - {job["job_id"] for job in selected}
    if missing:
        raise ValueError("unknown requested job ids: " + ", ".join(sorted(missing)))
    return selected if limit is None else selected[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True, help="explicit Python interpreter for ACE")
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--job-id", action="append", default=[])
    args = parser.parse_args()
    if args.workers < 1 or (args.limit is not None and args.limit < 1):
        parser.error("--workers and --limit must be positive")
    root = args.root.resolve()
    spec = read_json(root / "execution_spec.json")
    repository = repository_root(root, spec)
    python = args.python.resolve()
    if not python.is_file():
        parser.error(f"Python interpreter does not exist: {python}")
    if not tracked_tree_clean(repository):
        raise SystemExit("refusing execution with staged or unstaged tracked changes; commit the simulator first")
    jobs = select_jobs(read_jobs(args.manifest.resolve()), set(args.job_id), args.limit)
    commit = git_sha(repository)
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, python, repository, root, job, commit): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                job_id, state = future.result()
                print(f"{state:18} {job_id}", flush=True)
            except Exception as exc:  # preserve and report every failed job
                failures.append(f"{job['job_id']}: {exc}")
                print(f"FAILED             {job['job_id']}: {exc}", flush=True)
    if failures:
        raise SystemExit("execution failures:\n- " + "\n- ".join(failures))
    print(f"validated/completed {len(jobs)} jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
