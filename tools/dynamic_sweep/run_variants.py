#!/usr/bin/env python3
"""Test alternative Dynamic pre-generation launch rules on QFT-96, on one or more route arms.

The planner's schedule (what to prepare, with which per-core caps) is unchanged; the variants change WHEN a planned preparation is
launched (compiler_scheduler.TRIGGERS) and how many hops of a chain are prepared.  Baseline = today's rule: launch when layer L-1
activates.  Each (route, variant) runs the `dynamic` strategy on the given physics seeds; on-demand references come from the
routing study (same trace, same settings, 30 seeds).

    python tools/dynamic_sweep/run_variants.py --output results/dynamic_design_<date> --routes original xy --seeds 0,1,...,9
    python tools/dynamic_sweep/run_variants.py --output ... --report        # aggregate only
"""
from __future__ import annotations

import argparse
import csv
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import fmean, stdev

from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT.parent / "Compiler-Driven-ACE" / ".venv" / "bin" / "python"
ROUTES = {
    "original": ROOT.parent / "qft_requests.txt",
    "xy": ROOT / "results/routing_study_2026-10-25/qft96/xy/requests.txt",
    "yx": ROOT / "results/routing_study_2026-10-25/qft96/yx/requests.txt",
}
COMMON = ["--strategies", "dynamic", "--total-memories", "4", "--compiler-memories", "3", "--generation-capacity", "3",
          "--scheduler", "per-qubit", "--admission", "event", "--pregeneration-buffer-ms", "0",
          "--stop-after-workload", "--stop-time-s", "200"]
# name -> extra flags.  Names say what the rule is.
VARIANTS = {
    "baseline_layer-start": [],
    "layer-delay_1ms": ["--preparation-delay-ms", "1"],
    "layer-delay_2ms": ["--preparation-delay-ms", "2"],
    "layer-delay_3ms": ["--preparation-delay-ms", "3"],
    "layer-delay_4ms": ["--preparation-delay-ms", "4"],
    "layer-delay_6ms": ["--preparation-delay-ms", "6"],
    "predecessor-start": ["--preparation-trigger", "predecessor-start"],
    "predecessor-start+first-delay_2ms": ["--preparation-trigger", "predecessor-start", "--preparation-delay-ms", "2"],
    "predecessor-start+first-delay_4ms": ["--preparation-trigger", "predecessor-start", "--preparation-delay-ms", "4"],
    "first-hop-only": ["--chain-hops-prepared", "1"],
    "first-hop-only+delay_2ms": ["--chain-hops-prepared", "1", "--preparation-delay-ms", "2"],
    "first-hop-only+delay_4ms": ["--chain-hops-prepared", "1", "--preparation-delay-ms", "4"],
    "two-hops+predecessor-start": ["--chain-hops-prepared", "2", "--preparation-trigger", "predecessor-start"],
}


def run(job, output: Path, seeds: str) -> tuple[str, str, str]:
    route, name = job
    directory = output / route / name
    if (directory / "summary.csv").exists():
        return route, name, "kept"
    directory.mkdir(parents=True, exist_ok=True)
    command = [str(PYTHON), "run_trace_comparison.py", "--trace", str(ROUTES[route]), "--seeds", seeds, *COMMON,
               *VARIANTS[name], "--output", str(directory)]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (directory / "run.log").write_text(" ".join(command) + "\n" + done.stdout + done.stderr, encoding="utf-8")
    return route, name, "ok" if done.returncode == 0 else f"failed({done.returncode})"


def column(path: Path, metric: str) -> list[float]:
    return [float(r[metric]) for r in csv.DictReader(path.open(encoding="utf-8")) if r.get(metric) not in (None, "")]


def welch(a, b):
    va, vb = stdev(a) ** 2 / len(a), stdev(b) ** 2 / len(b)
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    return fmean(a) - fmean(b), stats.t.ppf(0.975, df) * se


REPORT_METRICS = [("request_latency_mean_ms", "latency (ms)"), ("request_latency_p95_ms", "p95 (ms)"),
                  ("average_admission_wait_ms", "wait (ms)"), ("end_to_end_latency_ms", "makespan (s)"),
                  ("intended_request_hit_rate", "hit rate"), ("average_storage_time_ms", "storage (ms)"),
                  ("average_fidelity_at_utilization", "fid. at use"), ("average_delivered_epr_fidelity", "fid. delivered"),
                  ("compiler_waste_percentage", "waste %")]


def report(output: Path, routes: list[str]) -> str:
    lines = []
    for route in routes:
        odg = ROOT / f"results/routing_study_2026-10-25/runs/{route}/summary.csv"
        odg_rows = [r for r in csv.DictReader(odg.open(encoding="utf-8")) if r["strategy"] == "on-demand"]
        base = column(output / route / "baseline_layer-start" / "summary.csv", "request_latency_mean_ms")
        lines += [f"## route: {route}  (on-demand reference, 30 seeds: latency {fmean(float(r['request_latency_mean_ms']) for r in odg_rows):.4f} ms, "
                  f"makespan {fmean(float(r['end_to_end_latency_ms']) for r in odg_rows) / 1000:.3f} s, "
                  f"p95 {fmean(float(r['request_latency_p95_ms']) for r in odg_rows):.3f} ms)", "",
                  "| variant | n | " + " | ".join(label for _, label in REPORT_METRICS) + " | latency − baseline (95% CI) | latency / ODG |",
                  "|---|---:|" + "---:|" * (len(REPORT_METRICS) + 2)]
        odg_latency = fmean(float(r["request_latency_mean_ms"]) for r in odg_rows)
        for name in VARIANTS:
            path = output / route / name / "summary.csv"
            if not path.exists():
                continue
            cells = []
            for metric, _ in REPORT_METRICS:
                v = column(path, metric)
                if not v:
                    cells.append("n/a")
                    continue
                m, sd = fmean(v), (stdev(v) if len(v) > 1 else 0.0)
                cells.append(f"{m / 1000:.3f} ± {sd / 1000:.3f}" if metric == "end_to_end_latency_ms" else f"{m:.4f} ± {sd:.4f}")
            lat = column(path, "request_latency_mean_ms")
            d, h = welch(lat, base) if name != "baseline_layer-start" and len(lat) > 1 else (0.0, 0.0)
            lines.append(f"| {name} | {len(lat)} | " + " | ".join(cells) + f" | {d:+.4f} ± {h:.4f} | {fmean(lat) / odg_latency:.3f} |")
        lines.append("")
    text = "\n".join(lines) + "\n"
    (output / "variants.md").write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--routes", nargs="+", default=["original", "xy"], choices=list(ROUTES))
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    parser.add_argument("--seeds", default=",".join(str(i) for i in range(10)))
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if not args.report:
        jobs = [(r, v) for r in args.routes for v in args.variants]
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(lambda j: run(j, output, args.seeds), jobs))
        bad = [r for r in results if r[2] not in ("ok", "kept")]
        print(f"{len(results)} jobs, {len(bad)} not ok", bad)
    print(report(output, args.routes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
