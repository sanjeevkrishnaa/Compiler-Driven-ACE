#!/usr/bin/env python3
"""Experiment 1: latency, fidelity and congestion of all ten benchmarks across communication-memory budgets.

Question: how much does communication-memory congestion cost each benchmark, and how does the number of memory
slots per core change it?  Everything runs on the corrected (per-qubit) scheduler; results of the legacy scheduler
are never mixed in (its serialization made the budget unable to bind).

* Workloads: the ten MQT circuits of the committed characterization, three mapping seeds each (42, 43, 44),
  three physics seeds (0, 1, 2).  Traces come from the archive, unmodified.
* Budgets (communication memories per core): 1, 2, 3, 4, 6, 8, 16, 32.  The ACGP paper's Table I gives four
  communication qubits per core, so 1 to 4 are modelled values and 6 to 32 are counterfactual (what-if capacity).
  QFT also runs 64: if it reproduces 32, 32 is saturated.
* Policies: on-demand (isolates contention: nothing is pre-generated) and dynamic compiler pre-generation, with
  one memory held back for demand (compiler memories = budget - 1), as in the budget study.  Dynamic needs at least
  two memories.
* Physical parameters are ACE's current ones, undecided (docs/reports/ace-physical-parameters.md).

    python tools/experiment1/run_experiment1.py --output results/<dir>
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "ace_budget_rerun"))
import run_budget_sweep as sweep                                   # noqa: E402  (shared single-run machinery)

WORKLOADS = ["ghz", "bv", "graphstate", "vqe_real_amp", "cdkm_ripple_carry_adder", "bmw_quark_cardinality",
             "draper_qft_adder", "qft", "qaoa", "randomcircuit"]
MAPPING_SEEDS = [42, 43, 44]
BUDGETS = [1, 2, 3, 4, 6, 8, 16, 32]
MODELLED_MAX = 4                    # communication qubits per core in the ACGP paper's Table I
SATURATION = {"qft": 64}
POLICIES = ["on-demand", "dynamic"]
SCHEDULER = "per-qubit"


def enumerate_jobs(budgets_wanted=None, mapping_seeds=None) -> list[tuple[str, int, int, str]]:
    jobs = []
    for workload in WORKLOADS:
        budgets = BUDGETS + ([SATURATION[workload]] if workload in SATURATION else [])
        if budgets_wanted is not None:
            budgets = [b for b in budgets if b in budgets_wanted]
        for mapping_seed in (MAPPING_SEEDS if mapping_seeds is None else mapping_seeds):
            for budget in budgets:
                for policy in POLICIES:
                    if policy == "dynamic" and budget < 2:
                        continue                # a compiler bank needs a memory besides the one held for demand
                    jobs.append((workload, mapping_seed, budget, policy))
    return jobs


def extract_traces(directory: Path) -> Path:
    with zipfile.ZipFile(sweep.ARCHIVE) as archive:
        for workload in WORKLOADS:
            for mapping_seed in MAPPING_SEEDS:
                archive.extract(f"{sweep.PREFIX}/{workload}/seed_{mapping_seed}/requests.txt", directory)
    return directory / sweep.PREFIX


def source_constants() -> dict:
    """Constants the simulator reads from code rather than config, parsed from the source so the record cannot drift."""
    topo = (REPO_ROOT / "router_net_topo_adaptive.py").read_text(encoding="utf-8")
    delay = re.search(r"hop_count \* (\d+) \* MICROSECOND \+ (\d+) \* MICROSECOND", topo)
    scheduler = (REPO_ROOT / "request_scheduler.py").read_text(encoding="utf-8")
    pick = lambda name: float(re.search(rf"^{name}\s*=\s*([0-9.]+)", scheduler, re.M).group(1))
    runner = (REPO_ROOT / "run_trace_comparison.py").read_text(encoding="utf-8")
    return {
        "classical_delay_per_hop_us": int(delay.group(1)), "classical_delay_base_us": int(delay.group(2)),
        "classical_delay_formula": "distance / c + hops * per_hop + base (router_net_topo_adaptive.py)",
        "empty_layer_gap_ms": pick("EMPTY_LAYER_GAP_MS"), "admission_grace_ps": pick("GRACE_PS"),
        "wait_threshold_ms": float(re.search(r"^WAIT_THRESHOLD_MS\s*=\s*([0-9.e-]+)", runner, re.M).group(1)),
        "retry_period": "1 ms (request_scheduler.RETRY_PERIOD)",
    }


def ace_physics(config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    template = config["templates"]["adaptive_protocol"]
    node = next(n for n in config["nodes"] if n.get("type") == "QuantumRouter")
    qchannels = {(q["distance"], q["attenuation"]) for q in config["qchannels"]}
    return {
        "config_file": str(config_path.relative_to(REPO_ROOT)) if config_path.is_relative_to(REPO_ROOT) else str(config_path),
        "memory_fidelity": template["MemoryArray"]["fidelity"], "memory_efficiency": template["MemoryArray"]["efficiency"],
        "memory_coherence_time_s": template["MemoryArray"]["coherence_time"],
        "bsm_detector_efficiencies": [d["efficiency"] for d in template["SingleHeraldedBSM"]["detectors"]],
        "encoding": template["encoding_type"], "adaptive_max_memory_in_file": template["adaptive_max_memory"],
        "gate_fidelity": node["gate_fidelity"], "measurement_fidelity": node["measurement_fidelity"],
        "router_to_bsm_links": [{"distance_m": d, "attenuation_db_per_m": a} for d, a in sorted(qchannels)],
        "note": "memo_size and the compiler memory limit are set per run from the budget",
    }


def git_state() -> dict:
    run = lambda *a: subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "uncommitted_changes": bool(run("status", "--porcelain", "--untracked-files=no"))}


def runner_parameters(output: Path) -> dict:
    """The full argument set of one run, as the runner itself recorded it (defaults included)."""
    for path in sorted((output / "runs").glob("*/metadata.json")):
        parameters = json.loads(path.read_text(encoding="utf-8"))["parameters"]
        return {k: v for k, v in parameters.items() if k not in ("trace", "output", "strategies", "total_memories",
                                                                  "compiler_memories", "generation_capacity", "seeds")}
    return {}


def write_timings(rows: list[dict], output: Path, jobs: int, wall_total: float) -> dict:
    """One line per invocation (three physics seeds run in one process), plus per-workload totals."""
    seen, lines = set(), []
    for r in rows:
        key = (r["workload"], r["mapping_seed"], r["total_memories"], r["strategy"])
        if key in seen or r.get("invocation_wall_seconds") in (None, ""):
            continue
        seen.add(key)
        lines.append({"workload": r["workload"], "mapping_seed": r["mapping_seed"], "budget": r["total_memories"],
                      "strategy": r["strategy"], "invocation_wall_seconds": r["invocation_wall_seconds"],
                      "seconds_per_run": f"{float(r['invocation_wall_seconds']) / 3:.2f}", "parallel_jobs": jobs})
    with (output / "timings.csv").open("w", newline="", encoding="utf-8") as handle:
        import csv
        writer = csv.DictWriter(handle, fieldnames=list(lines[0]) if lines else ["workload"])
        writer.writeheader()
        writer.writerows(lines)
    by_workload: dict = {}
    for line in lines:
        entry = by_workload.setdefault(line["workload"], {"invocations": 0, "sum_invocation_seconds": 0.0})
        entry["invocations"] += 1
        entry["sum_invocation_seconds"] += float(line["invocation_wall_seconds"])
    return {"per_workload_sum_of_invocation_seconds": {k: round(v["sum_invocation_seconds"], 1) for k, v in by_workload.items()},
            "invocations_timed": len(lines), "parallel_jobs": jobs,
            "total_wall_clock_seconds": round(wall_total, 1),
            "note": "an invocation is one process running three physics seeds; with parallel_jobs > 1 each includes contention "
                    "from the other jobs, so the sum exceeds the total wall clock"}


def label(row: dict) -> dict:
    budget = int(row["total_memories"])
    row["capacity_status"] = "modelled" if budget <= MODELLED_MAX else "counterfactual"
    row.pop("congested", None)          # the sweep driver's flag is specific to the budget study's workloads
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only-workloads", nargs="+", default=None, choices=WORKLOADS)
    parser.add_argument("--budgets", nargs="+", type=int, default=None, help="restrict the memory budgets")
    parser.add_argument("--mapping-seeds", nargs="+", type=int, default=None, choices=MAPPING_SEEDS)
    parser.add_argument("--config", type=Path, default=None, help="topology/physics config (default: ACE's)")
    parser.add_argument("--parameter-set", default="ace-default", help="label recorded in every row")
    parser.add_argument("--resume", action="store_true", help="keep invocations already on disk")
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    parser.add_argument("--traces-dir", type=Path, default=None,
                        help="directory <workload>/seed_<n>/requests.txt (default: the committed mesh archive)")
    args = parser.parse_args(argv)

    jobs = [j for j in enumerate_jobs(args.budgets, args.mapping_seeds)
            if args.only_workloads is None or j[0] in args.only_workloads]
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    if args.topology == "torus" and args.config is None:
        args.config = REPO_ROOT / "config" / "final_config" / "grid_4x4_torus_ace_3.json"
    if args.topology == "torus" and args.traces_dir is None:
        parser.error("--topology torus needs --traces-dir (the mapped torus traces)")
    traces = args.traces_dir.resolve() if args.traces_dir else extract_traces(args.output / "_traces")
    print(f"{len(jobs)} invocations ({3 * len(jobs)} runs), scheduler {SCHEDULER}", flush=True)

    def work(job):
        try:
            return job, [label(dict(r, parameter_set=args.parameter_set))
                         for r in sweep.run_one(job, traces, args.output, SCHEDULER, args.config, args.resume,
                                                ['--topology', args.topology])]
        except subprocess.TimeoutExpired:
            return job, [label({"workload": job[0], "mapping_seed": job[1], "total_memories": job[2],
                                "run_status": "TIMEOUT"})]

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for done, (job, new) in enumerate(pool.map(work, jobs), 1):
            rows.extend(new)
            if done % 10 == 0 or new[0].get("run_status") != "ok":
                print(f"[{done}/{len(jobs)}] {job} -> {new[0].get('run_status')} ({(time.time() - started) / 60:.1f} min)", flush=True)
    sweep.write_results(args.output / "results.csv", rows)
    finished = time.time()
    config_path = (args.config or (REPO_ROOT / "config" / "final_config" / "grid_4x4_ace_3.json")).resolve()
    record = {
        "experiment": "experiment1", "parameter_set": args.parameter_set, "topology": args.topology,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(finished)),
        "design": {"workloads": args.only_workloads or WORKLOADS, "mapping_seeds": args.mapping_seeds or MAPPING_SEEDS,
                   "budgets": args.budgets or BUDGETS, "saturation_arms": SATURATION, "policies": POLICIES,
                   "physics_seeds": [int(x) for x in sweep.PHYSICS_SEEDS.split(",")], "scheduler": SCHEDULER,
                   "modelled_capacity_max": MODELLED_MAX, "invocations": len(jobs), "runs": 3 * len(jobs),
                   "compiler_memories_rule": "budget - 1 (on-demand: forced to 0 at run time)",
                   "generation_capacity_rule": "equal to the compiler memories requested"},
        "runner_flags": sweep.RUNNER_FLAGS, "runner_parameters": runner_parameters(args.output),
        "ace_physics": ace_physics(config_path), "source_constants": source_constants(),
        "trace_sha256": {f"{r['workload']}/seed_{r['mapping_seed']}": r["trace_sha256"] for r in rows if r.get("trace_sha256")},
        "code": git_state(),
        "machine": {"platform": platform.platform(), "python": platform.python_version(), "cpus": os.cpu_count()},
        "timing": write_timings(rows, args.output, args.jobs, finished - started),
    }
    (args.output / "run_parameters.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    bad = [r for r in rows if r.get("run_status") != "ok"]
    print(f"done in {(finished - started) / 60:.1f} min ({finished - started:.0f} s wall clock, {args.jobs} jobs): "
          f"{len(rows) - len(bad)} rows ok, {len(bad)} not")
    for r in bad[:20]:
        print("  NOT OK", r.get("workload"), r.get("mapping_seed"), r.get("total_memories"), r.get("run_status"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
