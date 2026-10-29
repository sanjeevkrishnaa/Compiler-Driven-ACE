"""Compare routing arms run through identical ACE settings.

Reads ``<runs>/<arm>/summary.csv`` (one row per strategy and physics seed) and writes

* ``comparison.csv``  mean, sample sd and 95% confidence half-width of every metric, per arm and strategy;
* ``differences.csv`` each arm minus the control arm, with a Welch 95% interval on the difference of means;
* ``comparison.md``   the same, as the tables of the report.

Arms differ in their request trace, so the same physics seed does not mean the same random draws in the same
places; the seeds are treated as independent samples (Welch), not as pairs.

    python -m tools.mapper_ace.compare_routing results/routing_study_2026-10-25/runs --control original
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import fmean, stdev

from scipy import stats

METRICS = [
    ("request_latency_mean_ms", "fair request latency, mean (ms)"),
    ("request_latency_median_ms", "request latency, median (ms)"),
    ("request_latency_p95_ms", "request latency, p95 (ms)"),
    ("request_latency_max_ms", "request latency, max (ms)"),
    ("average_admission_wait_ms", "admission wait (ms)"),
    ("avg_entanglement_generation_time_ms", "generation / service (ms)"),
    ("end_to_end_latency_ms", "makespan"),
    ("intended_request_hit_rate", "EPR hit rate (intended)"),
    ("pregenerated_success_rate", "pre-generated success rate"),
    ("compiler_waste_percentage", "compiler EPR waste (%)"),
    ("compiler_expiry_percentage", "compiler EPR expiry (%)"),
    ("protocol_waste_percentage", "protocol EPR waste (%)"),
    ("average_storage_time_ms", "cached-pair storage time (ms)"),
    ("average_fidelity_at_creation", "fidelity at creation"),
    ("average_fidelity_at_utilization", "fidelity at use"),
    ("average_delivered_epr_fidelity", "delivered fidelity"),
    ("requests_that_waited_fraction", "requests that waited (fraction)"),
]
STRATEGIES = ("on-demand", "dynamic")


def load(runs: Path) -> dict[str, list[dict]]:
    return {d.name: list(csv.DictReader((d / "summary.csv").open(encoding="utf-8")))
            for d in sorted(runs.iterdir()) if (d / "summary.csv").exists()}


def values(rows: list[dict], strategy: str, metric: str) -> list[float]:
    out = []
    for row in rows:
        if row["strategy"] == strategy and row.get(metric) not in (None, ""):
            out.append(float(row[metric]))
    return out


def summary(v: list[float]) -> tuple[float, float, float]:
    if not v:
        return math.nan, math.nan, math.nan
    sd = stdev(v) if len(v) > 1 else 0.0
    half = stats.t.ppf(0.975, len(v) - 1) * sd / math.sqrt(len(v)) if len(v) > 1 else math.nan
    return fmean(v), sd, half


def welch(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """Difference of means a - b with a 95% Welch interval and the p-value."""
    if len(a) < 2 or len(b) < 2:
        return math.nan, math.nan, math.nan
    va, vb = stdev(a) ** 2 / len(a), stdev(b) ** 2 / len(b)
    se = math.sqrt(va + vb)
    if se == 0:
        return fmean(a) - fmean(b), 0.0, 0.0 if fmean(a) == fmean(b) else 1.0
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    half = stats.t.ppf(0.975, df) * se
    p = 2 * stats.t.sf(abs(fmean(a) - fmean(b)) / se, df)
    return fmean(a) - fmean(b), half, p


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--control", default="original")
    args = parser.parse_args()
    data = load(args.runs)
    arms = [a for a in data if a != args.control]
    arms = ([args.control] if args.control in data else []) + arms
    with (args.runs / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["arm", "strategy", "metric", "n", "mean", "sd", "ci95_half"])
        for arm in arms:
            for strategy in STRATEGIES:
                for metric, _ in METRICS:
                    v = values(data[arm], strategy, metric)
                    if v:
                        m, sd, h = summary(v)
                        w.writerow([arm, strategy, metric, len(v), m, sd, h])
    with (args.runs / "differences.csv").open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["arm", "control", "strategy", "metric", "difference", "ci95_half", "p_welch"])
        for arm in arms:
            if arm == args.control or args.control not in data:
                continue
            for strategy in STRATEGIES:
                for metric, _ in METRICS:
                    a, b = values(data[arm], strategy, metric), values(data[args.control], strategy, metric)
                    if a and b:
                        d, h, p = welch(a, b)
                        w.writerow([arm, args.control, strategy, metric, d, h, p])
    lines = [f"# Routing arms, identical ACE settings (control: {args.control})", ""]
    for strategy in STRATEGIES:
        lines += [f"## {strategy}: mean ± sample sd over physics seeds", "",
                  "| metric | " + " | ".join(arms) + " |", "|---|" + "---:|" * len(arms)]
        for metric, label in METRICS:
            cells = []
            for arm in arms:
                v = values(data[arm], strategy, metric)
                if not v:
                    cells.append("n/a")
                    continue
                m, sd, _ = summary(v)
                cells.append(f"{m / 1000:.4f} ± {sd / 1000:.4f}" if metric == "end_to_end_latency_ms" else f"{m:.4f} ± {sd:.4f}")
            if any(c != "n/a" for c in cells):
                lines.append(f"| {label}{' (s)' if metric == 'end_to_end_latency_ms' else ''} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Dynamic against on-demand, per arm", "",
              "| arm | latency ODG | latency dynamic | dynamic / ODG | makespan ODG (s) | makespan dynamic (s) | dynamic / ODG |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in arms:
        lo, ld = (fmean(values(data[arm], s, "request_latency_mean_ms")) for s in STRATEGIES)
        mo, md = (fmean(values(data[arm], s, "end_to_end_latency_ms")) / 1000 for s in STRATEGIES)
        lines.append(f"| {arm} | {lo:.4f} | {ld:.4f} | {ld / lo:.3f} | {mo:.3f} | {md:.3f} | {md / mo:.3f} |")
    lines.append("")
    (args.runs / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
