#!/usr/bin/env python3
"""Plot the complete validated QFT-96 metric set incrementally.

The input is the validated aggregate progress CSV.  No result is selected as
an optimum: memory plots average over all legal compiler allocations and say so
explicitly; matched-route plots require the requested M/C cell.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean, stdev


METRICS = (
    ("request_latency_mean_ms_mean", "Mean latency", "ms"),
    ("request_latency_p95_ms_mean", "p95 latency", "ms"),
    ("end_to_end_latency_ms_mean", "Makespan", "s"),
    ("average_admission_wait_ms_mean", "Admission wait", "ms"),
    ("average_delivered_epr_fidelity_mean", "Delivered fidelity", ""),
    ("protocol_waste_percentage_mean", "Protocol waste", "%"),
    ("compiler_waste_percentage_mean", "Compiler waste", "%"),
    ("intended_request_hit_rate_mean", "Intended compiler hit rate", "%"),
    ("on_demand_fallback_rate_mean", "On-demand fallback rate", "%"),
    ("compiler_not_ready_requests_mean", "Compiler-not-ready requests", "count"),
    ("total_retries_mean", "Retries", "count"),
)
POLICY_ORDER = ("ODG", "CGP", "ACGP", "Dynamic-full-chain", "Dynamic-first-hop")
COLORS = {"ODG": "#111111", "CGP": "#e69f00", "ACGP": "#cc79a7",
          "Dynamic-full-chain": "#0072b2", "Dynamic-first-hop": "#56b4e9"}


def number(value: str, metric: str) -> float:
    if value in ("", None): return math.nan
    value = float(value)
    return value / 1000 if metric == "end_to_end_latency_ms_mean" else value


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if float(row["completion_rate_mean"]) == 1.0]


def aggregate(rows: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows: groups[tuple(row.get(k, "") for k in keys)].append(row)
    output = []
    for key, group in sorted(groups.items()):
        result = {k: v for k, v in zip(keys, key)}
        for metric, _, _ in METRICS:
            values = [number(row.get(metric, ""), metric) for row in group]
            values = [v for v in values if not math.isnan(v)]
            result[metric] = fmean(values) if values else math.nan
            result[metric.replace("_mean", "_sd")] = stdev(values) if len(values) > 1 else 0.0
        result["observations"] = len(group)
        output.append(result)
    return output


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows: return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(rows)


def plot_metric_grid(rows: list[dict[str, object]], output: Path, *, title: str, x_key: str,
                     x_values: list[str], group_keys: tuple[str, ...], prefix: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for metric, label, unit in METRICS:
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        axes = axes.flat
        groups = sorted({tuple(str(r[k]) for k in group_keys) for r in rows})
        for ax, group in zip(axes, groups[:6]):
            subset = [r for r in rows if tuple(str(r[k]) for k in group_keys) == group]
            for policy in POLICY_ORDER:
                points = [r for r in subset if r.get("policy") == policy]
                points.sort(key=lambda r: x_values.index(str(r[x_key])) if str(r[x_key]) in x_values else 999)
                if not points: continue
                x = [x_values.index(str(r[x_key])) for r in points]
                y = [float(r[metric]) for r in points]
                e = [float(r[metric.replace("_mean", "_sd")]) for r in points]
                ax.errorbar(x, y, yerr=e, marker="o", linewidth=1.4, capsize=2,
                            label=policy, color=COLORS[policy])
            ax.set_title(" / ".join(group)); ax.set_xticks(range(len(x_values)), x_values)
            ax.set_xlabel("Total memories/core"); ax.set_ylabel(f"{label} ({unit})" if unit else label)
            ax.grid(alpha=.25)
        for ax in axes[len(groups[:6]):]: ax.axis("off")
        axes[0].legend(fontsize=7)
        fig.suptitle(f"{title}: {label}")
        fig.savefig(output / f"{prefix}_{metric}.png", dpi=180); fig.savefig(output / f"{prefix}_{metric}.pdf")
        plt.close(fig)


def plot_matched(rows: list[dict[str, object]], output: Path, m: int, c: int) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    metrics = METRICS
    groups = sorted({(str(r["topology"]), str(r["route_policy"])) for r in rows})
    fig, axes = plt.subplots(4, 3, figsize=(16, 16), constrained_layout=True)
    for ax, (metric, label, unit) in zip(axes.flat, metrics):
        for policy in POLICY_ORDER:
            subset = [r for r in rows if r["policy"] == policy]
            x, y, e, names = [], [], [], []
            for i, group in enumerate(groups):
                hit = [r for r in subset if (str(r["topology"]), str(r["route_policy"])) == group]
                if hit:
                    x.append(i); y.append(float(hit[0][metric])); e.append(float(hit[0][metric.replace("_mean", "_sd")]))
                    names.append("/".join(group))
            if y: ax.errorbar(x, y, yerr=e, marker="o", capsize=2, label=policy, color=COLORS[policy])
        ax.set_title(label); ax.set_xticks(range(len(groups)), ["/".join(g) for g in groups], rotation=35, ha="right")
        ax.grid(alpha=.25); ax.set_ylabel(unit)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(f"QFT-96 matched memory cell: M={m}; cached policies C={c}, ODG C=0")
    fig.savefig(output / f"matched_m{m}_c{c}_metrics.png", dpi=180); fig.savefig(output / f"matched_m{m}_c{c}_metrics.pdf")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matched-m", type=int, default=4)
    parser.add_argument("--matched-c", type=int, default=3)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    rows = read_rows(args.input)
    memory = aggregate(rows, ("topology", "route_policy", "total_memories_per_core", "policy"))
    # ODG has no compiler-reserved memory.  A fair fixed-total-memory comparison
    # therefore uses C=0 for ODG and the requested C for every cached policy.
    # Filtering every policy to C=args.matched_c accidentally removed ODG from
    # the headline comparison even though it is the required baseline.
    matched = aggregate([r for r in rows if int(r["total_memories_per_core"]) == args.matched_m
                         and ((r["policy"] == "ODG" and int(r["compiler_memories_per_core"]) == 0)
                              or (r["policy"] != "ODG" and int(r["compiler_memories_per_core"]) == args.matched_c))],
                        ("topology", "route_policy", "policy"))
    write_csv(args.output / "metrics_by_route_memory_policy.csv", memory)
    write_csv(args.output / f"metrics_matched_m{args.matched_m}_c{args.matched_c}.csv", matched)
    import matplotlib
    matplotlib.use("Agg")
    plot_metric_grid(memory, args.output, title="QFT-96 allocation-averaged metrics", x_key="total_memories_per_core",
                     x_values=["2", "3", "4", "6", "8", "16", "32", "64"],
                     group_keys=("topology", "route_policy"), prefix="memory")
    plot_matched(matched, args.output, args.matched_m, args.matched_c)
    (args.output / "README.md").write_text(
        "# QFT-96 metric plots\n\nGenerated only from validated rows in `" + str(args.input) + "`. "
        "Memory curves average over all legal compiler allocations; matched plots use the exact M/C cell "
        "for cached policies and C=0 for ODG, which has no compiler cache. "
        "Metrics include latency, p95, makespan, admission wait, fidelity, protocol/compiler waste, hit/fallback rates, "
        "compiler-not-ready requests, and retries. Empty/incomplete cells are omitted.\n", encoding="utf-8")
    print(f"validated input rows: {len(rows)}; memory groups: {len(memory)}; matched groups: {len(matched)}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
