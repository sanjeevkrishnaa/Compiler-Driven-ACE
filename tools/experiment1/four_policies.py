#!/usr/bin/env python3
"""Compare ODG, Dynamic, CGP and ACGP on all ten benchmarks from the Experiment 1 results.

Inputs: the Experiment 1 results of on-demand and dynamic, and the results of the same grid for CGP (``continuous``)
and ACGP (``adaptive-continuous``).  Every number is the mean over the three mapping seeds of the mean over the three
physics seeds, so each workload and budget carries the same weight per mapping seed.  Corrected (per-qubit) scheduler
only; CGP/ACGP may hold at most budget - 1 pairs per core at once, exactly as for dynamic (cache cap = budget - 1).

Waste = (pairs generated - pairs used) / pairs generated, from the simulator's protocol counters, over the workload's own
duration (CGP/ACGP runs end 1 ms after the last request completes).  A pair still cached when the run stops counts as not used,
as in the compiler's own accounting; the simulator's own figure, ``waste_expired_percent`` = pairs that expired unused / pairs generated,
leaves those out and so understates the waste of short workloads.  Both counters count a pair at each of its two endpoints.

    python tools/experiment1/four_policies.py --base RESULTS.csv --extra RESULTS.csv --output DIR [--label mesh]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

POLICY = {"on-demand": "ODG", "dynamic": "Dynamic", "continuous": "CGP", "adaptive-continuous": "ACGP"}
ORDER = ["ODG", "Dynamic", "CGP", "ACGP"]
STYLE = {"ODG": ("#4d4d4d", "o", "-"), "Dynamic": ("#1f5fbf", "s", "-"), "CGP": ("#d95f02", "^", "--"), "ACGP": ("#1b9e77", "v", "--")}
WORKLOADS = ["ghz", "bv", "graphstate", "vqe_real_amp", "cdkm_ripple_carry_adder", "bmw_quark_cardinality",
             "draper_qft_adder", "qft", "qaoa", "randomcircuit"]
METRICS = {
    "latency_ms": "average_eligible_latency_ms", "fidelity": "average_delivered_epr_fidelity",
    "wait_ms": "avg_retry_wait_time_ms", "generation_ms": "avg_entanglement_generation_time_ms",
    "waste_percent": "protocol_waste_percentage", "generated_pairs": "protocol_generated_pairs",
    "used_pairs": "protocol_used_pairs", "unused_pairs": "protocol_unused_pairs",
    "hit_rate": "intended_request_hit_rate", "makespan_ms": "end_to_end_latency_ms", "requests": "requests",
}


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = frame[frame["run_status"] == "ok"].copy()
    frame["policy"] = frame["strategy"].map(POLICY)
    return frame


def table(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = {k: pd.to_numeric(frame[v], errors="coerce") for k, v in METRICS.items() if v in frame}
    work = frame[["workload", "policy", "total_memories", "mapping_seed", "seed"]].assign(**numeric)
    work["waste_expired_percent"] = numeric["waste_percent"]
    generated = work["generated_pairs"].where(work["generated_pairs"] > 0)
    work["waste_percent"] = 100 * (generated - work["used_pairs"]) / generated
    per_mapping = work.groupby(["workload", "policy", "total_memories", "mapping_seed"], as_index=False).mean(numeric_only=True)
    out = per_mapping.groupby(["workload", "policy", "total_memories"], as_index=False).mean(numeric_only=True)
    out["used_per_request"] = out["used_pairs"] / (2 * out["requests"])
    return out.drop(columns=["mapping_seed", "seed"], errors="ignore")


def plot(t: pd.DataFrame, metric: str, ylabel: str, path: Path, title: str, log_y: bool = False, policies=ORDER):
    shown = [w for w in WORKLOADS if w in set(t.workload)]
    cols_n = 3
    rows_n = (len(shown) + cols_n - 1) // cols_n
    fig, axes = plt.subplots(rows_n, cols_n, figsize=(7.2 * cols_n, 4.1 * rows_n), sharex=True, squeeze=False)
    for ax in axes.ravel()[len(shown):]:
        ax.axis("off")
    for ax, workload in zip(axes.ravel(), shown):
        for policy in policies:
            d = t[(t.workload == workload) & (t.policy == policy)].sort_values("total_memories")
            if d.empty or d[metric].isna().all():
                continue
            color, marker, line = STYLE[policy]
            ax.plot(d.total_memories, d[metric], color=color, marker=marker, ls=line, lw=2.6, ms=8, label=policy)
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 2, 4, 8, 16, 32])
        ax.set_xticklabels(["1", "2", "4", "8", "16", "32"])
        ax.tick_params(labelsize=13)
        if log_y:
            ax.set_yscale("log")
        ax.set_title(workload.replace("_", " "), fontsize=17)
        ax.grid(alpha=0.25)
    for ax in axes[:, 0]:
        ax.set_ylabel(ylabel, fontsize=14)
    for ax in axes[-1]:
        ax.set_xlabel("memories per core", fontsize=14)
    axes[0, 0].legend(fontsize=14)
    fig.suptitle(title, fontsize=20)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--extra", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="mesh")
    parser.add_argument("--exclude", nargs="*", default=[], help="workloads left out of every table and figure")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    frame = pd.concat([load(args.base), load(args.extra)], ignore_index=True)
    frame = frame[~frame.workload.isin(args.exclude)]
    t = table(frame)
    t.round(6).to_csv(args.output / "four_policy_cell_means.csv", index=False)
    title = f"{args.label}, corrected scheduler, mean of 3 mapping x 3 physics seeds"
    plot(t, "latency_ms", "average request latency (ms)", args.output / "latency.png", f"Latency: {title}", log_y=True)
    plot(t, "fidelity", "average delivered EPR fidelity", args.output / "fidelity.png", f"Fidelity: {title}")
    plot(t, "waste_percent", "pairs generated and not used (%)", args.output / "waste.png", f"Wastage: {title}", policies=["Dynamic", "CGP", "ACGP"])
    plot(t, "wait_ms", "average admission wait (ms)", args.output / "wait.png", f"Waiting for a free memory: {title}", log_y=True)
    plot(t, "used_per_request", "pairs used per request (pre-generated pairs consumed)", args.output / "readiness.png",
         f"Readiness (pairs used per request; both endpoints counted): {title}", policies=["Dynamic", "CGP", "ACGP"])
    # who has the lowest latency / highest fidelity / lowest waste at each cell
    wide = t.pivot_table(index=["workload", "total_memories"], columns="policy", values=["latency_ms", "fidelity", "waste_percent"])
    rows = []
    for (workload, memories), r in wide.iterrows():
        lat = r["latency_ms"].dropna()
        rows.append({"workload": workload, "memories": memories, "lowest_latency": lat.idxmin(),
                     "dynamic_vs_odg_percent": 100 * (r["latency_ms"]["ODG"] - r["latency_ms"]["Dynamic"]) / r["latency_ms"]["ODG"]
                     if {"ODG", "Dynamic"} <= set(lat.index) else None,
                     "dynamic_vs_cgp_percent": 100 * (r["latency_ms"]["CGP"] - r["latency_ms"]["Dynamic"]) / r["latency_ms"]["CGP"]
                     if {"CGP", "Dynamic"} <= set(lat.index) else None,
                     "dynamic_vs_acgp_percent": 100 * (r["latency_ms"]["ACGP"] - r["latency_ms"]["Dynamic"]) / r["latency_ms"]["ACGP"]
                     if {"ACGP", "Dynamic"} <= set(lat.index) else None})
    pd.DataFrame(rows).round(3).to_csv(args.output / "who_wins.csv", index=False)
    print(f"{len(t)} cells -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
