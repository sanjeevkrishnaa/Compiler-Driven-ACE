"""Map and route the ten 224-qubit benchmarks for the benchmark study (2026-11-04).

Inputs: benchmarks/<name>/<name>_224.qasm (verified, see benchmarks/README.md).
Mapping: tools/congestion_study/run_study.py --mapping-only (T-HQA placer, OEE initial placement, mapping seed 42) on a
4x4 mesh with 16 data slots per core (14 occupied, 2 spare), 224 logical qubits.  One mapping per benchmark.
Routing: tools/routing_research/heavy_routing.py, XY and history, from that one frozen mapping, with routing capacity 8
(the history router balances load against this per-core capacity; 8 matches the 8-memory architecture and Sanjeev's
traces, which our pipeline reproduces exactly with capacity 8; XY ignores it).
Output: results/benchmark_study_2026-11-04/traces/<name>/<route>/requests.txt and traces_manifest.json.

The memory count does not enter the trace (simulation takes it from --total-memories), so one trace per benchmark and
route serves every memory setting K.

    <MQT Bench venv>/bin/python tools/benchmark_study/build_traces.py [--jobs 6]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "routing_research"))
import heavy_routing as routing     # noqa: E402

BENCHMARKS = ("qft", "bv", "ghz", "dj", "qpeexact", "qaoa", "draper_qft_adder", "graphstate",
              "bmw_quark_cardinality", "bmw_quark_copula")
ROUTES = ("xy", "history")
SIZE = 224
ROUTING_CAPACITY = 8
HISTORY_WINDOW = 0       # 0 = history routing counts ALL past layers (cumulative); the branch default of 2 is not used
WORK = ROOT / "output" / "benchmark_study"
OUTPUT = ROOT / "results" / "benchmark_study_2026-11-04" / "traces"


def map_one(name: str) -> tuple[str, int, str]:
    out = WORK / "mapping" / name
    cmd = [sys.executable, "-B", str(ROOT / "tools" / "congestion_study" / "run_study.py"), "--mapping-only",
           "--mapper-dir", str(ROOT / "mapper"), "--qasm", str(ROOT / "benchmarks" / name / f"{name}_{SIZE}.qasm"), "--output", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    (WORK / f"map_{name}.log").write_text(result.stdout + result.stderr)
    return name, result.returncode, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr[-300:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--remap", action="store_true", help="map again even if output/benchmark_study/inputs exists")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    inputs = WORK / "inputs"
    committed = OUTPUT.parent / "mapped_inputs"       # frozen mappings kept in git, so a fresh clone needs no mapper run
    for n in BENCHMARKS:
        if (committed / n / "seed_42" / "requests.txt").exists() and not (inputs / n / "seed_42" / "requests.txt").exists():
            shutil.copytree(committed / n / "seed_42", inputs / n / "seed_42")
    todo = [n for n in BENCHMARKS if args.remap or not (inputs / n / "seed_42" / "requests.txt").exists()]
    print("already mapped (reused):", [n for n in BENCHMARKS if n not in todo], "| to map:", todo, flush=True)
    with ThreadPoolExecutor(args.jobs) as pool:
        for name, code, last in pool.map(map_one, todo):
            print(f"mapped {name}: exit {code}: {last}", flush=True)
            if code:
                raise SystemExit(f"mapping failed for {name}; see {WORK / f'map_{name}.log'}")
    for name in todo:
        found = sorted((WORK / "mapping" / name).glob(f"{name}_{SIZE}_*/seed_42"))
        if len(found) != 1:
            raise SystemExit(f"{name}: expected one mapping folder, found {found}")
        target = inputs / name / "seed_42"
        target.mkdir(parents=True, exist_ok=True)
        for item in ("requests.txt", "mapping.npz", "manifest.json"):
            shutil.copy(found[0] / item, target / item)
    routing.ROOT = WORK.resolve()
    routing.build(WORK / "routed", inputs.resolve(), ROUTES, BENCHMARKS, capacity=ROUTING_CAPACITY,
                  history_window_layers=HISTORY_WINDOW)
    manifest = []
    for name in BENCHMARKS:
        mapping = json.loads((inputs / name / "seed_42" / "manifest.json").read_text())
        for route in ROUTES:
            data = (WORK / "routed" / "traces" / name / "seed_42" / route / "requests.txt").read_bytes().replace(b"\r\n", b"\n")
            target = OUTPUT / name / route / "requests.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest.append(dict(benchmark=name, route=route, routing_capacity=ROUTING_CAPACITY, history_window_layers=HISTORY_WINDOW,
                                 sha256=hashlib.sha256(data).hexdigest(),
                                 hops=mapping.get("hops"), layers=mapping.get("layers"),
                                 qasm_sha256=mapping["source"].get("sha256"), mapping_trace_sha256=mapping.get("trace_sha256")))
    (OUTPUT.parent / "traces_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(len(manifest), "traces written to", OUTPUT)


if __name__ == "__main__":
    main()
