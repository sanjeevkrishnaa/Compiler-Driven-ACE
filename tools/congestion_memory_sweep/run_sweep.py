"""Congestion memory-budget sweep on the native SeQUeNCe backend.

Case 1: communication_memories in {2,3,4}  -> congestion present
Case 2: communication_memories = 32 (64 saturation check) -> congestion removed

Only the congested workloads from the ten-workload characterization are swept,
plus GHZ as a zero-congestion control.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

SCRATCH = Path("/private/tmp/claude-501/-Users-dhruvrpansuriya-Documents-IITG-Acad-Sem-7-BTP/e28b2ce3-a808-45df-b069-3699d0957705/scratchpad")
ZIP = SCRATCH / "mqt_zip" / "mqt_ten_workload_study"
SEQ = Path("/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/SeQUeNCe")
RUNNER = SEQ / "example" / "multicore_entanglement" / "run_native_compiler_trace.py"
PY = Path("/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE/.venv/bin/python")

OUT = SCRATCH / "sweep"
RUNS = OUT / "runs"
RESULTS = OUT / "results.csv"

# congested workloads identified by the characterization, plus a control
CONGESTED = ["qft", "qaoa", "draper_qft_adder", "graphstate"]
CONTROL = ["ghz"]
MAPPING_SEEDS = [42, 43, 44]
BUDGETS = [2, 3, 4, 32]
SATURATION = {"qft": 64}  # extra arm to confirm 32 already removes congestion
STRATEGIES = ["odg", "dynamic"]
PHYSICS_SEEDS = 3

FIELDS = [
    "workload", "congested", "mapping_seed", "comm_memories", "strategy",
    "pregeneration_memories", "demand_bank", "requests", "physics_seeds",
    "completion_rate", "latency_ms", "latency_sd", "pending_ms", "generating_ms",
    "fidelity_at_teleportation", "fidelity_sd", "pregenerated_success_rate",
    "expiry_percent", "compiler_fallbacks", "prep_attempts", "failed_prep_attempts",
    "trace_sha256", "status",
]


def config_for(strategy: str, comm: int) -> dict:
    # ODG uses the whole bank for demand; dynamic reserves one slot for demand,
    # which reproduces the project's established 3+1 split at comm == 4.
    prege = 0 if strategy == "odg" else max(1, comm - 1)
    return {"communication_memories": comm, "pregeneration_memories": prege}


def run_one(workload: str, mseed: int, comm: int, strategy: str) -> dict:
    trace = ZIP / workload / f"seed_{mseed}" / "requests.txt"
    tag = f"{workload}_m{mseed}_c{comm}_{strategy}"
    outdir = RUNS / tag
    cfg_path = RUNS / f"cfg_{tag}.json"
    cfg = config_for(strategy, comm)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    cmd = [
        str(PY), str(RUNNER), str(trace),
        "--mesh", "4x4",
        "--strategies", strategy,
        "--seeds", str(PHYSICS_SEEDS),
        "--config", str(cfg_path),
        "--output-dir", str(outdir),
        "--overwrite",
    ]
    env = {"PYTHONPATH": str(SEQ), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    row = {
        "workload": workload,
        "congested": workload in CONGESTED,
        "mapping_seed": mseed,
        "comm_memories": comm,
        "strategy": strategy,
        "pregeneration_memories": cfg["pregeneration_memories"],
        "demand_bank": comm - cfg["pregeneration_memories"],
        "physics_seeds": PHYSICS_SEEDS,
    }
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(RUNNER.parent), env=env, timeout=3600)
    if proc.returncode != 0:
        row["status"] = "FAILED: " + (proc.stderr.strip().splitlines() or ["?"])[-1][:200]
        return row

    study = json.loads((outdir / "study.json").read_text(encoding="utf-8"))
    agg = study["aggregates"][0]
    row.update({
        "requests": agg.get("requests_per_trial"),
        "completion_rate": agg.get("completion_rate_mean"),
        "latency_ms": agg.get("average_latency_ms_mean"),
        "latency_sd": agg.get("average_latency_ms_stdev"),
        "pending_ms": agg.get("average_pending_ms_mean"),
        "generating_ms": agg.get("average_generating_ms_mean"),
        "fidelity_at_teleportation": agg.get("average_epr_fidelity_at_teleportation_mean"),
        "fidelity_sd": agg.get("average_epr_fidelity_at_teleportation_stdev"),
        "pregenerated_success_rate": agg.get("pregenerated_transfer_success_rate_mean"),
        "expiry_percent": agg.get("expiry_percentage_mean"),
        "compiler_fallbacks": agg.get("compiler_on_demand_fallbacks_mean"),
        "prep_attempts": agg.get("compiler_preparation_attempts_mean"),
        "failed_prep_attempts": agg.get("compiler_failed_preparation_attempts_mean"),
        "trace_sha256": study.get("trace_sha256"),
        "status": "ok",
    })
    return row


def main() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    jobs = []
    for workload in CONGESTED + CONTROL:
        budgets = list(BUDGETS)
        if workload in SATURATION:
            budgets.append(SATURATION[workload])
        for mseed in MAPPING_SEEDS:
            for comm in budgets:
                for strategy in STRATEGIES:
                    jobs.append((workload, mseed, comm, strategy))

    print(f"{len(jobs)} runs queued", flush=True)
    rows = []
    started = time.time()
    for index, job in enumerate(jobs, 1):
        t0 = time.time()
        row = run_one(*job)
        rows.append(row)
        with RESULTS.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for item in rows:
                writer.writerow({k: item.get(k) for k in FIELDS})
        print(f"[{index}/{len(jobs)}] {job} -> {row['status']} "
              f"({time.time() - t0:.1f}s, total {(time.time() - started) / 60:.1f}m)",
              flush=True)
    failures = [r for r in rows if r["status"] != "ok"]
    print(f"done. {len(rows) - len(failures)} ok, {len(failures)} failed")
    for f in failures:
        print("  FAIL", f["workload"], f["mapping_seed"], f["comm_memories"], f["strategy"], f["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
