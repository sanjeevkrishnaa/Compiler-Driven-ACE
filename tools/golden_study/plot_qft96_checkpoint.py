#!/usr/bin/env python3
"""Validate and plot the paired QFT-96 four-memory mesh/torus checkpoint."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .run_execution import read_jobs
from .summarize_execution import collect, policy_label


POLICIES = ("ODG", "CGP", "ACGP", "Dynamic-full-chain", "Dynamic-first-hop")
ROUTES = (("mesh", "xy"), ("torus", "dijkstra"))
REPOSITORY_CSV = (
    "https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE/blob/"
    "codex/ace-scheduler-correctness/results/qft96_2seed_2026-10-26/"
    "summaries/qft96_m4_checkpoint.csv"
)
REPOSITORY_SEED_CSV = REPOSITORY_CSV.replace(
    "qft96_m4_checkpoint.csv", "qft96_m4_seed_rows.csv"
)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def f(row: dict, key: str) -> float:
    value = row[key]
    return float(value) if value not in (None, "") else float("nan")


def latex_mean_sd(row: dict, metric: str, scale: float = 1.0, digits: int = 3) -> str:
    return (
        f"{f(row, metric + '_mean') * scale:.{digits}f}"
        r" $\pm$ "
        f"{f(row, metric + '_sd') * scale:.{digits}f}"
    )


def checkpoint(root: Path, jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    aggregate, _ = collect(root, jobs)
    selected: list[dict] = []
    for topology, route in ROUTES:
        for policy in POLICIES:
            matches = [
                row for row in aggregate
                if row["workload"] == "qft96"
                and row["topology"] == topology
                and row["route_policy"] == route
                and "42" in row["mapping_seeds"].split(";")
                and row["total_memories_per_core"] == 4
                and row["compiler_memories_per_core"] == (0 if policy == "ODG" else 3)
                and row["policy"] == policy
            ]
            if len(matches) != 1:
                raise ValueError(f"expected one complete checkpoint cell for {topology}/{policy}, got {len(matches)}")
            row = matches[0]
            if row["physics_seed_count"] != 2 or row["completion_rate_mean"] != 1.0:
                raise ValueError(f"incomplete physics seeds for {topology}/{policy}")
            selected.append(row)
    for topology, _ in ROUTES:
        traces = {row["trace_sha256"] for row in selected if row["topology"] == topology}
        if len(traces) != 1:
            raise ValueError(f"{topology} checkpoint policies use different request traces")
    by_id = {job["job_id"]: job for job in jobs}
    seed_rows: list[dict] = []
    for row in selected:
        job = by_id[row["job_id"]]
        with (root / job["output_path"] / "summary.csv").open(newline="", encoding="utf-8") as handle:
            raw = list(csv.DictReader(handle))
        matching = [
            item for item in raw
            if policy_label(job["execution_group"], item["strategy"]) == row["policy"]
        ]
        if sorted(int(item["seed"]) for item in matching) != [0, 1]:
            raise ValueError(f"seed-pair mismatch for {row['job_id']}/{row['policy']}")
        for item in matching:
            seed_rows.append({
                "job_id": row["job_id"],
                "topology": row["topology"],
                "route_policy": row["route_policy"],
                "mapping_seeds": row["mapping_seeds"],
                "trace_sha256": row["trace_sha256"],
                "policy": row["policy"],
                "physics_seed": item["seed"],
                "request_latency_mean_ms": item["request_latency_mean_ms"],
                "request_latency_p95_ms": item["request_latency_p95_ms"],
                "makespan_ms": item["end_to_end_latency_ms"],
                "average_admission_wait_ms": item["average_admission_wait_ms"],
                "pregenerated_success_rate": item["pregenerated_success_rate"],
                "protocol_waste_percentage": item["protocol_waste_percentage"],
                "average_delivered_epr_fidelity": item["average_delivered_epr_fidelity"],
                "completion_rate": item["completion_rate"],
                "raw_output_path": job["output_path"],
            })
    return selected, seed_rows


def plot(path: Path, rows: list[dict]) -> None:
    lookup = {(row["topology"], row["policy"]): row for row in rows}
    x = np.arange(len(POLICIES))
    width = 0.37
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.0))
    colors = {"mesh": "#4263a9", "torus": "#d58036"}
    for axis, (metric, scale, title, ylabel) in zip(
        axes,
        (
            ("request_latency_mean_ms", 1.0, "Hop-request latency", "Mean (ms)"),
            ("end_to_end_latency_ms", 0.001, "Workload makespan", "Mean (s)"),
        ),
    ):
        for index, (topology, route) in enumerate(ROUTES):
            cells = [lookup[(topology, policy)] for policy in POLICIES]
            offset = (-0.5 if index == 0 else 0.5) * width
            axis.bar(
                x + offset,
                [f(row, metric + "_mean") * scale for row in cells],
                width,
                yerr=[f(row, metric + "_sd") * scale for row in cells],
                capsize=2.5,
                color=colors[topology],
                label=f"{topology.title()} {route.upper() if route == 'xy' else 'Dijkstra'}",
            )
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.set_xticks(x)
        axis.set_xticklabels(("ODG", "CGP", "ACGP", "Dyn full", "Dyn first"), rotation=25, ha="right")
        axis.grid(axis="y", color="#dcdcdc", linewidth=0.6)
        axis.set_axisbelow(True)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("QFT-96: T-HQA, 4 shared memories, 2 physics seeds", fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def latex(path: Path, rows: list[dict]) -> None:
    body = [
        "% Generated by tools/golden_study/plot_qft96_checkpoint.py; do not edit by hand.",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.9\linewidth]{../../../results/qft96_2seed_2026-10-26/figures/qft96_m4_checkpoint.pdf}",
        r"\caption{Validated QFT-96 four-memory checkpoint. Bars show means and standard deviations across physics seeds 0 and 1, not uncertainty across mapping placements. Mesh XY and torus Dijkstra use the same logical migration endpoints. Exact values are in Table~\ref{tab:qft96-m4-timing} and the \href{" + REPOSITORY_CSV + r"}{aggregate CSV}; \href{" + REPOSITORY_SEED_CSV + r"}{per-seed rows} are also archived.}",
        r"\label{fig:qft96-m4-checkpoint}",
        r"\end{figure}",
        r"\begin{table}[H]",
        r"\centering\scriptsize",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Route & Policy & Latency (ms) & p95 (ms) & Makespan (s) & Admission (ms) \\",
        r"\midrule",
    ]
    for row in rows:
        route = "Mesh XY" if row["topology"] == "mesh" else "Torus Dijkstra"
        policy = row["policy"].replace("Dynamic-", "Dyn ").replace("-chain", "")
        body.append(
            f"{route} & {policy} & "
            f"{latex_mean_sd(row, 'request_latency_mean_ms')} & "
            f"{f(row, 'request_latency_p95_ms_mean'):.3f} & "
            f"{latex_mean_sd(row, 'end_to_end_latency_ms', 0.001)} & "
            f"{f(row, 'average_admission_wait_ms_mean'):.3f} " + r"\\"
        )
    body.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Complete matched timing values for Figure~\ref{fig:qft96-m4-checkpoint}. ODG has $C=0$; other policies have $C=3$. Latency and makespan show mean $\pm$ sample SD across two physics seeds. The full precision and raw job identifiers are in the \href{" + REPOSITORY_CSV + r"}{source CSV}.}",
        r"\label{tab:qft96-m4-timing}",
        r"\end{table}",
        r"\begin{table}[H]",
        r"\centering\scriptsize",
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Route & Policy & Pre-generated hit rate & Protocol waste (\%) & Fidelity \\",
        r"\midrule",
    ])
    for row in rows:
        route = "Mesh XY" if row["topology"] == "mesh" else "Torus Dijkstra"
        policy = row["policy"].replace("Dynamic-", "Dyn ").replace("-chain", "")
        readiness = float("nan") if row["policy"] == "ODG" else f(row, "pregenerated_success_rate_mean")
        waste = f(row, "protocol_waste_percentage_mean")
        body.append(
            f"{route} & {policy} & "
            f"{'N/A' if np.isnan(readiness) else f'{readiness:.3f}'} & "
            f"{'N/A' if np.isnan(waste) else f'{waste:.2f}'} & "
            f"{f(row, 'average_delivered_epr_fidelity_mean'):.4f} " + r"\\"
        )
    body.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Readiness, waste and delivered-pair fidelity for the same validated checkpoint; ODG has no pre-generated cache. \href{" + REPOSITORY_CSV + r"}{Source CSV}.}",
        r"\label{tab:qft96-m4-quality}",
        r"\end{table}",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--latex-output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    rows, seed_rows = checkpoint(root, read_jobs(args.manifest.resolve()))
    write_csv(root / "summaries/qft96_m4_checkpoint.csv", rows)
    write_csv(root / "summaries/qft96_m4_seed_rows.csv", seed_rows)
    plot(root / "figures/qft96_m4_checkpoint.pdf", rows)
    plot(root / "figures/qft96_m4_checkpoint.png", rows)
    latex(args.latex_output.resolve(), rows)
    print(f"validated {len(rows)} paired policy cells and {len(seed_rows)} seed rows")


if __name__ == "__main__":
    main()
