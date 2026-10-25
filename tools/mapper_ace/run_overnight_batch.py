#!/usr/bin/env python3
"""Everything left in the post-mapping plan that can run unattended, queued as one job list.

Phases (see docs/plans/post-mapping-research-plan.md and docs/plans/why-xy-wins-test-design.md):
  P1  30-seed confirmation of first-hop-only (today's screening winner) on the three main routes, dynamic only.
      ODG references for these routes already exist (results/routing_study_2026-10-25/runs/<arm>/summary.csv).
  P2  Dynamic parameter grid WITH first-hop-only on the XY route: compiler-memories x total-memories, plus
      admission mode and the starvation guard. 10-seed screening (step 6 of the original plan, combined with
      today's redesign). Each point is a full, independent flag set — nothing is patched after the fact.
  P3  Generalisation (test T5 / prediction P6 of the why-XY design): ten benchmarks, original vs XY routing,
      on-demand / dynamic / dynamic+first-hop-only, mapping seed 42, physics seeds 0-2.

Every job writes its own summary.csv; nothing here mutates an already-written result, so the batch is safe to
resume after an interruption. Progress and a running index are written to <output>/INDEX.md as jobs complete.

    python tools/mapper_ace/run_overnight_batch.py --output results/overnight_2026-10-25 --jobs 4
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT.parent / "Compiler-Driven-ACE" / ".venv" / "bin" / "python"
R = ROOT / "results/routing_study_2026-10-25/qft96"
QFT96_ROUTES = {"original": ROOT.parent / "qft_requests.txt", "xy": R / "xy/requests.txt", "yx": R / "yx/requests.txt"}
WORKLOADS = ["ghz", "bv", "graphstate", "vqe_real_amp", "cdkm_ripple_carry_adder", "bmw_quark_cardinality",
             "draper_qft_adder", "qft", "qaoa", "randomcircuit"]

SEEDS_30 = ",".join(str(i) for i in range(30))
SEEDS_10 = ",".join(str(i) for i in range(10))
SEEDS_GEN = "0,1,2"

# Every flag ACE's runner needs, with no default omitted, so each job's command is self-contained and auditable.
BASE_FLAGS = {"--generation-capacity": "3", "--scheduler": "per-qubit", "--pregeneration-buffer-ms": "0",
              "--stop-after-workload": None, "--stop-time-s": "200"}


def flags(seeds: str, total_memories: int, compiler_memories: int, admission: str = "event",
          starvation_guard: bool = True) -> list[str]:
    out = ["--seeds", seeds, "--total-memories", str(total_memories), "--compiler-memories", str(compiler_memories),
           "--admission", admission]
    for flag, value in BASE_FLAGS.items():
        out += [flag] if value is None else [flag, value]
    if not starvation_guard:
        out.append("--no-starvation-guard")
    return out


def job(label: str, trace: Path, directory: Path, strategy_flags: list[str], common: list[str]) -> tuple[str, Path, list[str]]:
    return label, directory, ["--trace", str(trace), *strategy_flags, *common, "--output", str(directory)]


def build_jobs(output: Path) -> list[tuple[str, Path, list[str]]]:
    jobs = []

    # P1: first-hop-only, 30 seeds, dynamic, on each main route (the ODG side of these routes is already run)
    for route, trace in QFT96_ROUTES.items():
        jobs.append(job(f"P1_first-hop-only_{route}", trace, output / "P1_confirm" / route,
                        ["--strategies", "dynamic", "--chain-hops-prepared", "1"],
                        flags(SEEDS_30, total_memories=4, compiler_memories=3)))

    # P2: parameter grid with first-hop-only, on XY, 10-seed screening
    xy = QFT96_ROUTES["xy"]
    for compiler_memories in (1, 2, 3):
        for total_memories in (4, 6, 8):
            if compiler_memories > total_memories - 1:
                continue
            name = f"P2_cm{compiler_memories}_tm{total_memories}"
            jobs.append(job(name, xy, output / "P2_grid" / name, ["--strategies", "dynamic", "--chain-hops-prepared", "1"],
                            flags(SEEDS_10, total_memories=total_memories, compiler_memories=compiler_memories)))
    jobs.append(job("P2_admission_poll", xy, output / "P2_grid" / "P2_admission_poll",
                    ["--strategies", "dynamic", "--chain-hops-prepared", "1"],
                    flags(SEEDS_10, total_memories=4, compiler_memories=3, admission="poll")))
    jobs.append(job("P2_no_starvation_guard", xy, output / "P2_grid" / "P2_no_starvation_guard",
                    ["--strategies", "dynamic", "--chain-hops-prepared", "1"],
                    flags(SEEDS_10, total_memories=4, compiler_memories=3, starvation_guard=False)))

    # P3: generalisation across ten benchmarks, original vs xy, three strategies, mapping seed 42, physics 0-2
    original_root = ROOT / "results/generalization_2026-10-25/original_traces/mqt_ten_workload_study"
    xy_root = ROOT / "results/xy_ten_benchmarks_2026-10-25/traces/xy"
    for workload in WORKLOADS:
        for route, root in (("original", original_root), ("xy", xy_root)):
            trace = root / workload / "seed_42" / "requests.txt"
            if not trace.exists():
                continue
            for strategy, strategy_flags in (("on-demand", ["--strategies", "on-demand"]),
                                             ("dynamic", ["--strategies", "dynamic"]),
                                             ("dynamic-first-hop", ["--strategies", "dynamic", "--chain-hops-prepared", "1"])):
                jobs.append(job(f"P3_{workload}_{route}_{strategy}", trace,
                                output / "P3_generalisation" / workload / f"{route}_{strategy}",
                                strategy_flags, flags(SEEDS_GEN, total_memories=4, compiler_memories=3)))
    return jobs


def run(entry: tuple[str, Path, list[str]]) -> tuple[str, str]:
    label, directory, args = entry
    if (directory / "summary.csv").exists():
        return label, "kept"
    directory.mkdir(parents=True, exist_ok=True)
    command = [str(PYTHON), "run_trace_comparison.py", *args]
    (directory / "command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (directory / "run.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    return label, "ok" if done.returncode == 0 else f"failed({done.returncode})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs(output)
    (output / "job_list.txt").write_text("\n".join(j[0] for j in jobs) + "\n", encoding="utf-8")
    started = time.time()
    index = output / "INDEX.md"
    index.write_text(f"# Overnight batch, started {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{len(jobs)} jobs, {args.jobs} parallel\n\n",
                     encoding="utf-8")
    done_count = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for label, status in pool.map(run, jobs):
            done_count += 1
            with index.open("a", encoding="utf-8") as handle:
                handle.write(f"- [{done_count}/{len(jobs)}] `{label}`: {status}  ({(time.time() - started) / 60:.1f} min elapsed)\n")
            print(f"[{done_count}/{len(jobs)}] {label}: {status}", flush=True)
    with index.open("a", encoding="utf-8") as handle:
        handle.write(f"\nAll {len(jobs)} jobs finished in {(time.time() - started) / 60:.1f} min.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
