#!/usr/bin/env python3
"""Rerun the ACE congestion budget study under a chosen request scheduler (Gate 6).

Same design as ``tools/ace_congestion_budget/run_budget_sweep.py``, which produced the published
378 runs and is left untouched as the record of that study: workloads qft, qaoa, draper_qft_adder,
graphstate (congested) and ghz (control), mapping seeds 42 to 44, total memories 2, 3, 4, 32
(and 64 on qft), strategies on-demand and dynamic, physics seeds 0 to 2, compiler slots =
budget - 1, generation capacity scaled with the budget.

What differs: paths are relative to the repository, the traces come from the committed archive,
invocations run in parallel, and ``--scheduler`` selects the request manager.  Run with
``--scheduler legacy`` to confirm the driver reproduces the published ``results.csv``.

    python tools/ace_budget_rerun/run_budget_sweep.py --scheduler per-qubit --output results/<dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "run_trace_comparison.py"
ARCHIVE = REPO_ROOT / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
PREFIX = "mqt_ten_workload_study"

CONGESTED = ["qft", "qaoa", "draper_qft_adder", "graphstate"]
CONTROL = ["ghz"]
MAPPING_SEEDS = [42, 43, 44]
BUDGETS = [2, 3, 4, 32]
SATURATION = {"qft": 64}
STRATEGIES = ["on-demand", "dynamic"]
PHYSICS_SEEDS = "0,1,2"
CONTEXT = ["workload", "congested", "mapping_seed", "total_memories", "compiler_memories", "demand_bank",
           "scheduler", "trace_sha256", "run_status"]


def compiler_memories(strategy: str, budget: int) -> int:
    """Compiler slots requested, holding one slot back for demand (3+1 at a budget of four)."""
    return max(1, budget - 1)


def runtime_compiler_cap(strategy: str, budget: int) -> int:
    """The cap the simulator actually applies: zero for on-demand."""
    return 0 if strategy == "on-demand" else compiler_memories(strategy, budget)


def enumerate_jobs() -> list[tuple[str, int, int, str]]:
    jobs = []
    for workload in CONGESTED + CONTROL:
        budgets = list(BUDGETS) + ([SATURATION[workload]] if workload in SATURATION else [])
        for mapping_seed in MAPPING_SEEDS:
            for budget in budgets:
                for strategy in STRATEGIES:
                    jobs.append((workload, mapping_seed, budget, strategy))
    return jobs


def extract_traces(directory: Path) -> Path:
    wanted = [f"{PREFIX}/{w}/seed_{m}/requests.txt" for w in CONGESTED + CONTROL for m in MAPPING_SEEDS]
    with zipfile.ZipFile(ARCHIVE) as archive:
        for name in wanted:
            archive.extract(name, directory)
    return directory / PREFIX


def run_one(job, traces: Path, output: Path, scheduler: str, config: Path | None = None,
            reuse: bool = False) -> list[dict]:
    """Run one invocation (three physics seeds).  ``reuse`` keeps an invocation already on disk; its metadata is
    still checked against the request, so a stale folder cannot pass for a different configuration."""
    workload, mapping_seed, budget, strategy = job
    trace = traces / workload / f"seed_{mapping_seed}" / "requests.txt"
    comp, cap = compiler_memories(strategy, budget), runtime_compiler_cap(strategy, budget)
    outdir = output / "runs" / f"{workload}_m{mapping_seed}_c{budget}_{strategy}"
    base = {"workload": workload, "congested": workload in CONGESTED, "mapping_seed": mapping_seed,
            "total_memories": budget, "compiler_memories": cap, "demand_bank": budget - cap,
            "scheduler": scheduler, "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}
    command = [sys.executable, "-B", str(RUNNER), "--trace", str(trace), "--mesh", "4x4",
               "--strategies", strategy, "--seeds", PHYSICS_SEEDS, "--total-memories", str(budget),
               "--compiler-memories", str(comp), "--generation-capacity", str(comp),
               "--delta-layers", "6", "--dynamic-lookahead-layers", "8", "--coherence-time-layers", "10",
               "--compiler-reservation-ms", "1000", "--stop-time-s", "300", "--scheduler", scheduler,
               "--output", str(outdir)]
    if config is not None:
        command += ["--config", str(config)]
    if not (reuse and (outdir / "summary.csv").exists() and (outdir / "metadata.json").exists()):
        process = subprocess.run(command, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=7200)
        if process.returncode != 0:
            tail = (process.stderr.strip().splitlines() or ["?"])[-1][:200]
            return [dict(base, run_status="FAILED: " + tail)]
    meta = json.loads((outdir / "metadata.json").read_text(encoding="utf-8"))
    got = (meta["parameters"]["total_memories"], meta["parameters"]["compiler_memories"], meta["parameters"]["scheduler"])
    if got != (budget, comp, scheduler):
        return [dict(base, run_status=f"CONFIG-MISMATCH: asked {(budget, comp, scheduler)}, ran {got}")]
    rows = []
    with (outdir / "summary.csv").open(encoding="utf-8") as handle:
        for result in csv.DictReader(handle):
            row = dict(base, run_status="ok", **result)
            if float(row.get("completion_rate", 0)) != 1.0:
                row["run_status"] = f"INCOMPLETE: completion_rate={row.get('completion_rate')}"
            rows.append(row)
    return rows


def write_results(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    ordered = CONTEXT + [f for f in fields if f not in CONTEXT]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in ordered})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scheduler", choices=("legacy", "per-qubit"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only-workloads", nargs="+", default=None, help="restrict, for a quick check")
    args = parser.parse_args(argv)

    jobs = [j for j in enumerate_jobs() if args.only_workloads is None or j[0] in args.only_workloads]
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    traces = extract_traces(args.output / "_traces")
    print(f"{len(jobs)} invocations ({len(jobs) * len(PHYSICS_SEEDS.split(','))} runs), scheduler {args.scheduler}", flush=True)

    def work(job):
        try:
            return job, run_one(job, traces, args.output, args.scheduler)
        except subprocess.TimeoutExpired:
            return job, [{"workload": job[0], "mapping_seed": job[1], "total_memories": job[2], "run_status": "TIMEOUT"}]

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for done, (job, new) in enumerate(pool.map(work, jobs), 1):
            rows.extend(new)
            print(f"[{done}/{len(jobs)}] {job} -> {new[0].get('run_status')} (total {(time.time() - started) / 60:.1f} min)", flush=True)
    write_results(args.output / "results.csv", rows)
    bad = [r for r in rows if r.get("run_status") != "ok"]
    print(f"done in {(time.time() - started) / 60:.1f} min: {len(rows) - len(bad)} rows ok, {len(bad)} not")
    for r in bad:
        print("  NOT OK", r.get("workload"), r.get("mapping_seed"), r.get("total_memories"), r.get("run_status"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
