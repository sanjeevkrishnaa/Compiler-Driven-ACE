"""Generate, route and simulate one workload using the pinned engine."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ace.compiler.settings import DEFAULT_COMPILER_RESERVATION_MS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("run", "trace", "route", "simulate"), nargs="?", default="run")
    p.add_argument("--workload", choices=("qaoa", "qft", "draper_qft_adder"), default="qaoa")
    p.add_argument("--routing", choices=("xy", "yx", "greedy", "history", "minexcess", "minhop", "detour2"), default="greedy")
    p.add_argument("--qubits", type=int, default=96)
    p.add_argument("--mapping-seed", type=int, choices=(42,), default=42,
                   help="current routing study supports mapping seed 42")
    p.add_argument("--seeds", default="60,61,62,63")
    p.add_argument("--reservation-ms", type=float, default=DEFAULT_COMPILER_RESERVATION_MS)
    p.add_argument("--output", type=Path)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    if a.qubits <= 0 or a.qubits > 112 or a.reservation_ms <= 0:
        p.error("qubits must be 1..112 and reservation-ms must be positive")
    out = (a.output or ROOT / "output" / (a.workload + "-" + a.routing)).resolve()
    inputs = out / "inputs"
    engine = ROOT / "third_party" / "SeQUeNCe"
    if not a.dry_run and not (engine / "sequence" / "__init__.py").is_file():
        p.error("initialize engine first: git submodule update --init --recursive")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(engine), str(ROOT / "mapper"), str(ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    temporary = ROOT / "output" / "runtime_temp"
    if not a.dry_run:
        temporary.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = env["TMP"] = str(temporary)
    base = [sys.executable, "-B"]
    commands = {
        "trace": base + ["tools/congestion_study/run_study.py", "--mapper-dir", "mapper",
            "--workloads", a.workload, "--logical-qubits", str(a.qubits), "--total-qubits", "192",
            "--memory-slots", "4", "--placer", "T-HQA", "--seeds", str(a.mapping_seed),
            "--mapping-only", "--output", str(inputs)],
        "route": base + ["tools/routing_research/heavy_routing.py", "build", "--inputs", str(inputs),
            "--workloads", a.workload, "--algorithms", a.routing, "--output", str(out)],
        "simulate": base + ["tools/routing_research/heavy_routing.py", "simulate", "--output", str(out),
            "--workloads", a.workload, "--algorithms", a.routing, "--seeds", a.seeds,
            "--compiler-pair-consumption", "handoff", "--compiler-reservation-ms", str(a.reservation_ms)],
    }
    stages = ("trace", "route", "simulate") if a.stage == "run" else (a.stage,)
    if not a.dry_run and "trace" in stages and inputs.exists() and any(inputs.iterdir()):
        p.error("input folder already exists; choose a fresh --output, or use route/simulate stages")
    for stage in stages:
        print(stage + ": " + subprocess.list2cmdline(commands[stage]), flush=True)
        if not a.dry_run:
            subprocess.run(commands[stage], cwd=ROOT, env=env, check=True)
    print("Results: " + str(out / "simulation" / a.workload / "seed_42" / a.routing / "summary.csv"))


if __name__ == "__main__":
    main()
