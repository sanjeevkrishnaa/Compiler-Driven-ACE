"""Run explicit full-chain alternatives on selection seeds; preserve each run's evidence."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    "handoff-c1-l2": ["--compiler-pair-consumption", "handoff", "--admission-priority", "ready-first", "--planner-lead-layers", "2", "--compiler-memories", "1", "--generation-capacity", "1"],
    "handoff-c2-l2": ["--compiler-pair-consumption", "handoff", "--admission-priority", "ready-first", "--planner-lead-layers", "2"],
    "handoff-c3-l2": ["--compiler-pair-consumption", "handoff", "--admission-priority", "ready-first", "--planner-lead-layers", "2", "--compiler-memories", "3", "--generation-capacity", "3"],
    "handoff-c4-l2": ["--compiler-pair-consumption", "handoff", "--admission-priority", "ready-first", "--planner-lead-layers", "2", "--compiler-memories", "4", "--generation-capacity", "4"],
    "fifo-c2-l2": ["--planner-lead-layers", "2", "--admission-priority", "fifo"],
    "ready-c2-l2": ["--planner-lead-layers", "2", "--admission-priority", "ready-first"],
    "fifo-c3-l2": ["--planner-lead-layers", "2", "--compiler-memories", "3", "--generation-capacity", "3", "--admission-priority", "fifo"],
    "ready-c3-l2": ["--planner-lead-layers", "2", "--compiler-memories", "3", "--generation-capacity", "3", "--admission-priority", "ready-first"],
    "odg": ["--strategies", "on-demand"],
    "offline-c2": [],
    "offline-c3": ["--compiler-memories", "3", "--generation-capacity", "3"],
    "lead2-c2": ["--planner-lead-layers", "2"],
    "lead3-c2": ["--planner-lead-layers", "3"],
    "capacity3-c2": ["--generation-capacity", "3"],
    "demand-first-c2": ["--demand-first", "--refill-on-release"],
    "runtime-c2": ["--planning-mode", "runtime", "--refill-on-release"],
    "runtime-c3": ["--planning-mode", "runtime", "--refill-on-release",
                   "--compiler-memories", "3", "--generation-capacity", "3"],
    "runtime-demand-c2": ["--planning-mode", "runtime", "--refill-on-release", "--demand-first"],
    "runtime-lead2-c2": ["--planning-mode", "runtime", "--refill-on-release", "--planner-lead-layers", "2"],
    "lead2-demand-c2": ["--planner-lead-layers", "2", "--demand-first", "--refill-on-release"],
    "lead2-borrow-c2": ["--planner-lead-layers", "2", "--borrow-compiler-pairs", "--refill-on-release"],
    "lead2-borrow-c3": ["--planner-lead-layers", "2", "--borrow-compiler-pairs", "--refill-on-release",
                       "--compiler-memories", "3", "--generation-capacity", "3"],
    "borrow-c2": ["--borrow-compiler-pairs", "--refill-on-release"],
    "lead4-c2": ["--planner-lead-layers", "4"],
    "lead2-c1": ["--planner-lead-layers", "2", "--compiler-memories", "1", "--generation-capacity", "1"],
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    p.add_argument("--seeds", default="30,31")
    p.add_argument("--variants", default=",".join(VARIANTS))
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    names = args.variants.split(",")
    if any(n not in VARIANTS for n in names):
        p.error("unknown variant")
    if args.output.exists() and any(args.output.iterdir()):
        p.error("output must be empty")
    args.output.mkdir(parents=True, exist_ok=True)
    base = [sys.executable, "-u", str(ROOT / "run_trace_comparison.py"),
            "--trace", str(args.trace.resolve()), "--config", str(args.config.resolve()),
            "--topology", args.topology, "--mesh", "4x4", "--strategies", "dynamic",
            "--seeds", args.seeds, "--total-memories", "4", "--compiler-memories", "2",
            "--generation-capacity", "2", "--scheduler", "per-qubit", "--admission", "event",
            "--admission-priority", "fifo",
            "--compiler-pair-consumption", "swap",
            "--all-chain-hops", "--no-congestion-threshold", "--pregeneration-buffer-ms", "0",
            "--stop-after-workload", "--audit-events"]
    commands = {n: base + VARIANTS[n] + ["--output", str((args.output / n).resolve())] for n in names}
    (args.output / "commands.json").write_text(json.dumps(commands, indent=2))

    def run(name):
        with (args.output / f"{name}.log").open("w") as log:
            subprocess.run(commands[name], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (args.output / name / "summary.csv").open() as f:
            rows = [{"variant": name, **row} for row in csv.DictReader(f)]
        print(name, [(r["seed"], r["request_latency_mean_ms"]) for r in rows], flush=True)
        return rows

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run, name) for name in names]):
            rows.extend(future.result())
    with (args.output / "all_seeds.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["variant"], int(r["seed"]))))


if __name__ == "__main__":
    main()
