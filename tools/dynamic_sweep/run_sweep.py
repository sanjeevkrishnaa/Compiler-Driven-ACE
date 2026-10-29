#!/usr/bin/env python3
"""Step 6: sweep the Dynamic policy's parameters on one fixed trace, one factor at a time.

Every point runs ``run_trace_comparison.py`` with the baseline settings below and ONE value changed, so a point's
difference from the baseline is attributable to that parameter.  The baseline is the setting of
``results/qft96_physical_per_qubit_30seed_2026-10-25``.  On-demand (ODG) is run once per trace as the reference.

What each parameter does (read in compiler_trace.py / request_scheduler.py; see docs/plans/post-mapping-research-plan.md):

* compiler-memories  how many of a core's ``total-memories`` the compiler may hold at once (planner cap per core and layer).
* generation-capacity  preparations a core may start in one layer (planner cap).
* dynamic-lookahead-layers  how many layers back the planner may place a preparation.  The planner tries layer L-1 first, so
  this is expected to change nothing (checked on 210 configurations before); it is swept to confirm on the new traces.
* delta-layers  used ONLY by the ``fixed`` strategy (prepare exactly delta layers ahead).  Meaningless for ``dynamic``.
* coherence-time-layers  the PLANNER's window: a preparation older than this many layers is not planned and the hold length
  is capped by it.  It is not the memory's physical coherence time (ACE config, 1 s).
* admission / starvation guard  how the per-qubit scheduler decides which waiting request to start.

    python tools/dynamic_sweep/run_sweep.py --trace results/routing_study_2026-10-25/qft96/xy/requests.txt \\
        --output results/dynamic_sweep_<date>/xy --seeds 0,1,2,3,4 --jobs 4 [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT.parent / "Compiler-Driven-ACE" / ".venv" / "bin" / "python"

BASELINE = {
    "total-memories": 4, "compiler-memories": 3, "generation-capacity": 3, "delta-layers": 6,
    "dynamic-lookahead-layers": 8, "coherence-time-layers": 10, "admission": "event", "starvation-guard": "on",
}
# (strategy, parameter, values).  Baseline values are included so every sweep line contains its own anchor point.
SWEEPS = [
    ("dynamic", "compiler-memories", [1, 2, 3]),
    ("dynamic", "total-memories", [4, 6, 8]),
    ("dynamic", "generation-capacity", [1, 2, 3, 4]),
    ("dynamic", "dynamic-lookahead-layers", [1, 2, 4, 8, 16]),
    ("dynamic", "coherence-time-layers", [2, 4, 6, 10, 20, 40]),
    ("dynamic", "admission", ["event", "poll"]),
    ("dynamic", "starvation-guard", ["on", "off"]),
    ("fixed", "delta-layers", [1, 2, 4, 6, 8, 12]),
]


def point_args(strategy: str, setting: dict) -> list[str]:
    s = dict(setting)
    # compiler memories can never exceed total - 1 (one memory is the demand bank)
    s["compiler-memories"] = min(s["compiler-memories"], s["total-memories"] - 1)
    args = ["--strategies", strategy, "--total-memories", str(s["total-memories"]),
            "--compiler-memories", str(s["compiler-memories"]), "--generation-capacity", str(s["generation-capacity"]),
            "--delta-layers", str(s["delta-layers"]), "--dynamic-lookahead-layers", str(s["dynamic-lookahead-layers"]),
            "--coherence-time-layers", str(s["coherence-time-layers"]), "--admission", s["admission"]]
    if s["starvation-guard"] == "off":
        args.append("--no-starvation-guard")
    return args


def enumerate_points() -> list[dict]:
    points, seen = [], set()
    for strategy, parameter, values in SWEEPS:
        for value in values:
            setting = dict(BASELINE, **{parameter: value})
            key = (strategy, json.dumps(setting, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            points.append({"id": f"{strategy}__{parameter}={value}", "strategy": strategy, "parameter": parameter,
                           "value": value, "setting": setting})
    return points


def run_point(point: dict, trace: Path, output: Path, seeds: str, stop_time: int, dry: bool) -> dict:
    directory = output / point["id"]
    command = [str(PYTHON), "run_trace_comparison.py", "--trace", str(trace), "--seeds", seeds,
               "--scheduler", "per-qubit", "--pregeneration-buffer-ms", "0", "--stop-after-workload",
               "--stop-time-s", str(stop_time), "--output", str(directory)] + point_args(point["strategy"], point["setting"])
    if dry:
        return {**point, "command": " ".join(command), "status": "dry-run"}
    if (directory / "summary.csv").exists():
        return {**point, "status": "kept"}
    directory.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (directory / "run.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    return {**point, "status": "ok" if done.returncode == 0 else f"failed({done.returncode})"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="0,1,2,3,4")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--stop-time-s", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    points = enumerate_points()
    reference = {"id": "on-demand__reference", "strategy": "on-demand", "parameter": "-", "value": "-", "setting": BASELINE}
    points = [reference] + points
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "design.json").write_text(json.dumps({"baseline": BASELINE, "points": points, "trace": str(args.trace),
                                                         "seeds": args.seeds}, indent=2), encoding="utf-8")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda p: run_point(p, args.trace, args.output, args.seeds, args.stop_time_s, args.dry_run), points))
    if args.dry_run:
        for r in results:
            print(r["id"], "\n   ", r["command"])
        print(f"{len(results)} points")
        return 0
    rows = []
    for r in results:
        summary = args.output / r["id"] / "summary.csv"
        if not summary.exists():
            continue
        for row in csv.DictReader(summary.open(encoding="utf-8")):
            rows.append({"point": r["id"], "parameter": r["parameter"], "value": r["value"], **row})
    if rows:
        with (args.output / "sweep.csv").open("w", newline="", encoding="utf-8") as handle:
            w = csv.DictWriter(handle, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    bad = [r for r in results if r["status"] not in ("ok", "kept")]
    print(f"{len(results)} points, {len(bad)} not ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
