"""Generate, route and simulate one workload using the pinned engine."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ace.compiler.settings import DEFAULT_COMPILER_RESERVATION_MS



def module_available(name):
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def empty_failed_generation(inputs):
    """Retry only metadata-only failed attempts; never overwrite generated data."""
    if {p.name for p in inputs.iterdir()} - {"study.json", "summary.csv"}:
        return False
    try:
        study = json.loads((inputs / "study.json").read_text())
        return study.get("status") == "partial_failure" and study.get("trials") == []
    except (OSError, ValueError):
        return False


def ensure_engine(root: Path) -> Path:
    """Initialize only a missing engine; preserve an existing checkout."""
    engine = root / "third_party" / "SeQUeNCe"
    if (engine / "sequence" / "__init__.py").is_file():
        return engine
    print("Initializing pinned SeQUeNCe engine...", flush=True)
    try:
        subprocess.run(["git", "submodule", "update", "--init", "--recursive", "--", "third_party/SeQUeNCe"],
                       cwd=root, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Could not initialize SeQUeNCe. Ensure Git and network access are available, "
                           "then run: git submodule update --init --recursive -- third_party/SeQUeNCe") from exc
    if not (engine / "sequence" / "__init__.py").is_file():
        raise RuntimeError("SeQUeNCe source is still missing after initialization. Use a Git clone of ACE, "
                           "rather than a downloaded source ZIP.")
    return engine


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("run", "trace", "route", "simulate"), nargs="?", default="run")
    p.add_argument("--workload", choices=("qaoa", "qft", "draper_qft_adder", "bv"), default="qaoa")
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
    if not a.dry_run:
        missing = [name for name in ("numpy", "scipy", "networkx", "matplotlib", "qiskit", "qutip", "mqt.bench")
                   if not module_available(name)]
        if missing:
            p.error("Missing Python dependencies: " + ", ".join(missing) +
                    ". Run make setup with the same PYTHON, or: " +
                    subprocess.list2cmdline([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-workload.txt")]))
        try:
            engine = ensure_engine(ROOT)
        except RuntimeError as exc:
            p.error(str(exc))
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
    if not a.dry_run and "trace" in stages and inputs.exists() and any(inputs.iterdir()) and not empty_failed_generation(inputs):
        p.error("input folder already exists; choose a fresh --output, or use route/simulate stages")
    for stage in stages:
        print(stage + ": " + subprocess.list2cmdline(commands[stage]), flush=True)
        if not a.dry_run:
            try:
                subprocess.run(commands[stage], cwd=ROOT, env=env, check=True)
            except subprocess.CalledProcessError as exc:
                detail = ""
                if stage == "trace" and (inputs / "study.json").is_file():
                    failures = json.loads((inputs / "study.json").read_text()).get("errors", [])
                    detail = "; ".join(str(e.get("error", e)) for e in failures)
                p.error(f"{stage} stage failed (exit {exc.returncode}). {detail} See output logs above.")
    print("Results: " + str(out / "simulation" / a.workload / "seed_42" / a.routing / "summary.csv"))


if __name__ == "__main__":
    main()
