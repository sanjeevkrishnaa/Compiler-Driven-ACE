#!/usr/bin/env python3
"""Summarise Experiment 1: per-cell statistics over the nine runs (3 mapping x 3 physics seeds), controls, figures, report.

    python tools/experiment1/analyze.py --results results/<dir>/results.csv --output results/<dir>
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "heatmap"))
import regenerate_heatmap as heatmap                                         # noqa: E402

METRICS = {
    "latency_ms": "average_eligible_latency_ms",
    "makespan_ms": "end_to_end_latency_ms",
    "fidelity": "average_delivered_epr_fidelity",
    "admission_wait_ms": "average_admission_wait_ms",
    "waited_fraction": "requests_that_waited_fraction",
    "retries": "total_retries",
}
TITLES = dict(heatmap.ORDER)
ORDER = [k for k, _ in heatmap.ORDER]
BLUE, ORANGE = "#2a78d6", "#eb6834"                   # validated pair (dataviz skill)
MODELLED_MAX = 4


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def num(row, column):
    value = row.get(column)
    return None if value in (None, "") else float(value)


def cells(rows):
    """(workload, strategy, budget) -> metric -> list of per-run values (one per mapping x physics seed)."""
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key = (r["workload"], r["strategy"], int(r["total_memories"]))
        for name, column in METRICS.items():
            v = num(r, column)
            if v is not None:
                grouped[key][name].append(v)
        grouped[key]["_runs"].append((int(r["mapping_seed"]), int(r["seed"])))
    return grouped


def stats(values):
    if not values:
        return None
    return {"mean": st.fmean(values), "sd": st.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values), "n": len(values)}


def controls(rows, grouped):
    """Each check returns (passed, detail)."""
    out = []
    bad = [r for r in rows if r.get("run_status") != "ok" or float(r["completion_rate"]) != 1.0]
    out.append(("every run completes every request", not bad, f"{len(rows)} rows, {len(bad)} not ok"))
    # GHZ on-demand: one value per (mapping seed, physics seed) across all budgets
    per_run = defaultdict(set)
    for r in rows:
        if r["workload"] == "ghz" and r["strategy"] == "on-demand":
            per_run[(r["mapping_seed"], r["seed"])].add(round(float(r["average_eligible_latency_ms"]), 9))
    varying = sum(len(v) > 1 for v in per_run.values())
    out.append(("zero-congestion control: GHZ on-demand latency does not respond to the budget",
                varying == 0, f"{varying} of {len(per_run)} (mapping, physics) runs vary across budgets"))
    # saturation: QFT 64 == 32, per run
    by = {(r["strategy"], r["mapping_seed"], r["seed"], int(r["total_memories"])): r for r in rows if r["workload"] == "qft"}
    diffs = 0
    pairs = 0
    for (strategy, ms, ps, budget), r in by.items():
        if budget == 64:
            pairs += 1
            other = by[(strategy, ms, ps, 32)]
            diffs += any(r[c] != other[c] for c in ("average_eligible_latency_ms", "end_to_end_latency_ms",
                                                    "average_delivered_epr_fidelity"))
    out.append(("saturation: QFT with 64 memories reproduces 32 run for run", diffs == 0,
                f"{diffs} of {pairs} runs differ" if pairs else "not applicable: no 64-memory runs in this data"))
    # on-demand fidelity independent of budget
    fid = defaultdict(set)
    for r in rows:
        if r["strategy"] == "on-demand":
            fid[(r["workload"], r["mapping_seed"], r["seed"])].add(round(float(r["average_delivered_epr_fidelity"]), 12))
    out.append(("on-demand delivered fidelity does not depend on the budget", all(len(v) == 1 for v in fid.values()),
                f"{sum(len(v) > 1 for v in fid.values())} of {len(fid)} runs vary"))
    # latency never rises with more memory (on-demand), per run
    rises = 0
    total = 0
    series = defaultdict(dict)
    for r in rows:
        if r["strategy"] == "on-demand":
            series[(r["workload"], r["mapping_seed"], r["seed"])][int(r["total_memories"])] = float(r["average_eligible_latency_ms"])
    for budgets in series.values():
        ordered = [budgets[b] for b in sorted(budgets)]
        for a, b in zip(ordered, ordered[1:]):
            total += 1
            rises += b > a + 1e-9
    out.append(("on-demand latency never rises when memory is added (per run)", rises == 0,
                f"{rises} of {total} consecutive budget steps rise"))
    return out


def structural(budget_list):
    """workload -> budget -> % of communication-active layers with any core overloaded, pooled over the three mapping seeds."""
    result = defaultdict(dict)
    for b in budget_list:
        data = heatmap.compute(b)
        for k in ORDER:
            active = sum(data[k]["active_layers"].values())
            result[k][b] = 100.0 * sum(data[k]["overloaded_layers"].values()) / active if active else 0.0
    return result


def figure(grouped, metric, ylabel, path, policies=("on-demand", "dynamic"), log_y=False, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colour = {"on-demand": BLUE, "dynamic": ORANGE}
    figure_, axes = plt.subplots(2, 5, figsize=(17, 6.6), sharex=True)
    budgets = sorted({k[2] for k in grouped})
    for axis, workload in zip(axes.flat, ORDER):
        for policy in policies:
            xs, mean, low, high = [], [], [], []
            for b in budgets:
                s = stats(grouped.get((workload, policy, b), {}).get(metric, []))
                if s:
                    xs.append(b); mean.append(s["mean"]); low.append(s["min"]); high.append(s["max"])
            if xs:
                axis.fill_between(xs, low, high, color=colour[policy], alpha=0.16, linewidth=0)
                axis.plot(xs, mean, color=colour[policy], linewidth=2, marker="o", markersize=4, label=policy)
        axis.axvspan(MODELLED_MAX, max(budgets) * 1.3, color="#888888", alpha=0.08, linewidth=0)
        axis.set_xscale("log", base=2)
        if log_y:
            axis.set_yscale("log")
        axis.set_xticks([1, 2, 4, 8, 16, 32, 64])
        axis.set_xticklabels(["1", "2", "4", "8", "16", "32", "64"], fontsize=7)
        axis.set_title(TITLES[workload], fontsize=9)
        axis.tick_params(labelsize=7)
        axis.grid(True, color="#dddddd", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    for axis in axes[:, 0]:
        axis.set_ylabel(ylabel, fontsize=8)
    for axis in axes[1]:
        axis.set_xlabel("communication memories per core", fontsize=8)
    axes[0][0].legend(fontsize=8, frameon=False)
    figure_.suptitle(title + "  (line: mean of 9 runs; band: min to max; grey: beyond the modelled 4 slots, counterfactual)", fontsize=10)
    figure_.tight_layout()
    figure_.savefig(path, dpi=130)
    plt.close(figure_)


def fmt(s, digits=2):
    return "-" if s is None else f"{s['mean']:.{digits}f} ± {s['sd']:.{digits}f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = load(args.results)
    grouped = cells(rows)
    budgets = sorted({k[2] for k in grouped})
    args.output.mkdir(parents=True, exist_ok=True)

    with (args.output / "cell_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["workload", "strategy", "budget", "capacity_status", "runs"] +
                        [f"{m}_{q}" for m in METRICS for q in ("mean", "sd", "min", "max")])
        for key in sorted(grouped, key=lambda k: (ORDER.index(k[0]), k[1], k[2])):
            row = [key[0], key[1], key[2], "modelled" if key[2] <= MODELLED_MAX else "counterfactual",
                   len(grouped[key]["_runs"])]
            for m in METRICS:
                s = stats(grouped[key].get(m, []))
                row += ["" if s is None else f"{s[q]:.9g}" for q in ("mean", "sd", "min", "max")] if s else ["", "", "", ""]
            writer.writerow(row)

    checks = controls(rows, grouped)
    for name, ok, detail in checks:
        print(("PASS " if ok else "FAIL ") + name + " -- " + detail)
    figure(grouped, "latency_ms", "request latency (ms)", args.output / "latency_vs_budget.png", log_y=True,
           title="Request latency against communication memories per core")
    figure(grouped, "fidelity", "delivered EPR fidelity", args.output / "fidelity_vs_budget.png",
           title="Delivered EPR fidelity against communication memories per core")
    figure(grouped, "waited_fraction", "fraction of requests that waited", args.output / "waiting_vs_budget.png",
           policies=("on-demand", "dynamic"), title="Requests that had to wait for a free memory")
    struct = structural([b for b in budgets if b <= 64])
    import json
    (args.output / "structural_overload.json").write_text(json.dumps(struct, indent=1), encoding="utf-8")
    (args.output / "controls.txt").write_text("\n".join(("PASS " if ok else "FAIL ") + n + " -- " + d for n, ok, d in checks) + "\n")
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
