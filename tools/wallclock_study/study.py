"""The fixed setup of the wall-clock study, and a runner for it.

Architecture: 4x4 mesh, 16 data slots per core (14 occupied at the start, 2 reserved for migrations) and 4
communication memories per core, so 224 logical qubits.  Memory efficiency is 0.8 (config/final_config).
Strategies: ODG (on-demand), CGP (continuous), ACGP (adaptive-continuous) and Dynamic; the compiler-driven strategies
use all four memories.  CGP and ACGP are autonomous: they keep the cache limit of their configuration file (3).
Routes: XY and history.  Latency is eligibility to EPR delivery; data teleportation is not simulated.

    python tools/wallclock_study/study.py --workloads draper_qft_adder --routes xy --seeds 60 --jobs 4
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TRACES = ROOT / "results" / "wallclock_2026-11-03" / "traces"
RUNS = ROOT / "output" / "wallclock_study" / "runs"
CONFIG = ROOT / "config" / "final_config" / "grid_4x4_ace_3.json"

WORKLOADS = ("qft", "qpeexact", "qaoa", "draper_qft_adder")
SETUP_ONLY = ("quantum_volume",)        # mapped and routed, deliberately not simulated for now
ROUTES = ("xy", "history")
STRATEGIES = ("on-demand", "continuous", "adaptive-continuous", "dynamic")
MEMORIES = 4

COMMON = ["--config", str(CONFIG), "--total-memories", str(MEMORIES), "--compiler-memories", str(MEMORIES),
          "--generation-capacity", str(MEMORIES), "--planner-lead-layers", "2", "--scheduler", "per-qubit",
          "--admission", "event", "--admission-priority", "ready-first", "--all-chain-hops", "--no-congestion-threshold",
          "--pregeneration-buffer-ms", "0", "--stop-after-workload", "--audit-events", "--compiler-pair-consumption", "handoff"]


def command(workload: str, route: str, strategy: str, seeds: str, output: Path, extra: tuple[str, ...] = ()) -> list[str]:
    trace = TRACES / workload / route / "requests.txt"
    return [sys.executable, "-B", str(ROOT / "run_trace_comparison.py"), "--trace", str(trace), "--strategies", strategy,
            "--seeds", seeds, *COMMON, *extra, "--output", str(output)]


def run_job(job) -> tuple[str, int]:
    workload, route, strategy, seeds, extra, folder = job
    output = RUNS / folder / f"{workload}_{route}_{strategy}"
    if (output / "summary.csv").exists():
        return output.name, 0
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("SEQUENCE_ENGINE", ""), str(ROOT), env.get("PYTHONPATH", "")]))
    with (output / "run.log").open("w") as log:
        code = subprocess.run(command(workload, route, strategy, seeds, output, extra), cwd=ROOT, env=env,
                              stdout=log, stderr=subprocess.STDOUT).returncode
    return output.name, code


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=WORKLOADS)
    p.add_argument("--routes", nargs="+", default=list(ROUTES), choices=ROUTES)
    p.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    p.add_argument("--seeds", default="60,61,62,63")
    p.add_argument("--folder", default="baseline", help="subfolder of output/wallclock_study/runs")
    p.add_argument("--extra", nargs="*", default=[], help="extra run_trace_comparison.py flags, e.g. --extra --dynamic-planner time")
    p.add_argument("--jobs", type=int, default=8)
    a = p.parse_args()
    jobs = [(w, r, s, a.seeds, tuple(a.extra), a.folder) for w in a.workloads for r in a.routes for s in a.strategies]
    with ThreadPoolExecutor(a.jobs) as pool:
        for name, code in pool.map(run_job, jobs):
            print(("ok     " if code == 0 else f"FAILED({code}) ") + name, flush=True)


if __name__ == "__main__":
    main()
