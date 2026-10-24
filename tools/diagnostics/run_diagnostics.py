#!/usr/bin/env python3
"""Run the diagnostic experiments (tools/diagnostics/occupancy.py) in parallel and record one JSON per job.

Groups
  mechanism  QFT (mapping seed 42, physics seed 0) at 2/3/4/6/8/16 memories: on-demand, dynamic, CGP, ACGP
  ablation   QFT at 4 memories: dynamic and on-demand with one setting changed from the baseline
             (generation capacity, request duration = booking window, compiler reservation window, compiler cap)
  workloads  the other benchmarks at 4 memories: on-demand, dynamic, CGP, ACGP
  seeds      QFT at 4 memories on mapping seeds 43 and 44 (the others use 42)
Every job runs physics seeds 0, 1 and 2; the summary averages them.
Baseline settings are those of Experiment 1 (see tools/ace_budget_rerun/run_budget_sweep.RUNNER_FLAGS).
Ablations change a setting to find out which one the effect depends on; they are not proposed parameter values.

    python tools/diagnostics/run_diagnostics.py --output results/<dir> [--jobs 4] [--groups mechanism ablation workloads]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ace_budget_rerun"))
import run_budget_sweep as sweep                                    # noqa: E402

AUTONOMOUS = {"continuous": "CGP", "adaptive-continuous": "ACGP"}
POLICIES = ["on-demand", "dynamic", "continuous", "adaptive-continuous"]
BASE = {"delta-layers": "6", "dynamic-lookahead-layers": "8", "coherence-time-layers": "10",
        "compiler-reservation-ms": "1000", "stop-time-s": "300", "request-duration-ms": "50"}
OTHER_WORKLOADS = ["qaoa", "graphstate", "draper_qft_adder", "randomcircuit", "vqe_real_amp", "cdkm_ripple_carry_adder"]


def jobs_for(groups):
    jobs = []
    def add(group, name, workload, policy, memories, cap=None, mapping_seed=42, diag=(), **override):
        jobs.append({"group": group, "name": name, "workload": workload, "policy": policy, "memories": memories,
                     "cap": memories - 1 if cap is None else cap, "override": override, "mapping_seed": mapping_seed,
                     "diag": list(diag)})
    if "mechanism" in groups:
        for memories in (2, 3, 4, 6, 8, 16):
            for policy in POLICIES:
                add("mechanism", f"qft_m{memories}_{policy}", "qft", policy, memories)
    if "ablation" in groups:
        for policy in ("dynamic", "on-demand"):
            for gc in (1, 2):
                if policy == "dynamic":
                    add("ablation", f"qft_m4_{policy}_gencap{gc}", "qft", policy, 4, **{"generation-capacity": str(gc)})
            for rd in (10, 20, 100):
                add("ablation", f"qft_m4_{policy}_duration{rd}", "qft", policy, 4, **{"request-duration-ms": str(rd)})
        for crm in (100, 300):
            add("ablation", f"qft_m4_dynamic_reservation{crm}", "qft", "dynamic", 4, **{"compiler-reservation-ms": str(crm)})
        for cap in (1, 2):
            add("ablation", f"qft_m4_dynamic_cap{cap}", "qft", "dynamic", 4, cap=cap)
        for look in (1, 2, 4):
            add("ablation", f"qft_m4_dynamic_lookahead{look}", "qft", "dynamic", 4, **{"dynamic-lookahead-layers": str(look)})
        for hops in (1, 2):
            add("ablation", f"qft_m4_dynamic_first{hops}hops", "qft", "dynamic", 4, diag=("--only-chain-hops-below", str(hops)))
    if "seeds" in groups:
        for mapping_seed in (43, 44):
            for policy in POLICIES:
                add("seeds", f"qft_m4_{policy}_map{mapping_seed}", "qft", policy, 4, mapping_seed=mapping_seed)
    if "workloads" in groups:
        for workload in OTHER_WORKLOADS:
            for policy in POLICIES:
                add("workloads", f"{workload}_m4_{policy}", workload, policy, 4)
    return jobs


def run_job(job, traces: Path, output: Path):
    out_json = output / f"{job['name']}.json"
    if out_json.exists():
        return job["name"], 0.0, "kept"
    trace = traces / job["workload"] / f"seed_{job['mapping_seed']}" / "requests.txt"
    flags = dict(BASE, **job["override"])
    flags.setdefault("generation-capacity", str(job["cap"]))
    cap = job["cap"]                         # the runner itself applies zero compiler memories to on-demand
    command = [sys.executable, "-B", str(ROOT / "tools/diagnostics/occupancy.py"), "--out", str(out_json), *job["diag"], "--",
               "--trace", str(trace), "--mesh", "4x4", "--strategies", job["policy"], "--seeds", "0,1,2",
               "--total-memories", str(job["memories"]), "--compiler-memories", str(cap),
               *[x for k, v in flags.items() for x in (f"--{k}", v)],
               "--scheduler", "per-qubit", "--output", str(output / "_runs" / job["name"])]
    if job["policy"] in AUTONOMOUS:
        command += ["--autonomous-cache-follows-compiler-memories", "--stop-after-workload"]
    started = time.perf_counter()
    process = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT), timeout=7200)
    wall = time.perf_counter() - started
    if process.returncode != 0:
        return job["name"], wall, "FAILED: " + (process.stderr.strip().splitlines() or ["?"])[-1][:200]
    data = json.loads(out_json.read_text())
    data["job"] = job
    data["wall_seconds"] = round(wall, 2)
    out_json.write_text(json.dumps(data, indent=1, default=str))
    return job["name"], wall, "ok"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--groups", nargs="+", default=["mechanism", "ablation", "workloads", "seeds"],
                        choices=["mechanism", "ablation", "workloads", "seeds"])
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    traces = args.output / "_traces"
    with zipfile.ZipFile(sweep.ARCHIVE) as archive:
        for workload in ["qft"] + OTHER_WORKLOADS:
            for mapping_seed in (42, 43, 44):
                if not (traces / sweep.PREFIX / workload / f"seed_{mapping_seed}" / "requests.txt").exists():
                    archive.extract(f"{sweep.PREFIX}/{workload}/seed_{mapping_seed}/requests.txt", traces)
    jobs = jobs_for(args.groups)
    print(f"{len(jobs)} diagnostic jobs", flush=True)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for done, (name, wall, status) in enumerate(pool.map(lambda j: run_job(j, traces / sweep.PREFIX, args.output), jobs), 1):
            print(f"[{done}/{len(jobs)}] {name}: {status} ({wall:.0f} s, {(time.time() - started) / 60:.1f} min)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
