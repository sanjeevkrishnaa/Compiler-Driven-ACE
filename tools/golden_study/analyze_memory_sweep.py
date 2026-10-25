#!/usr/bin/env python3
"""Validate and report one complete Golden-study memory-sweep slice."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


POLICY_ORDER = (
    "ODG", "CGP", "ACGP", "Dynamic-first-hop", "Dynamic-full-chain",
)
POLICY_COLORS = {
    "ODG": "#111111", "CGP": "#e69f00", "ACGP": "#cc79a7",
    "Dynamic-first-hop": "#56b4e9", "Dynamic-full-chain": "#0072b2",
}
METRIC_PANELS = (
    ("request_latency_mean_ms", "Mean request latency", "ms"),
    ("request_latency_p95_ms", "Mean per-seed p95 latency", "ms"),
    ("end_to_end_latency_ms", "Makespan", "ms"),
    ("average_delivered_epr_fidelity", "Delivered EPR fidelity", ""),
)


def read_slice(
    path: Path, *, workload: str, mapping_algorithm: str,
    topology: str, route_policy: str,
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows
        if row["workload"] == workload
        and row["mapping_algorithm"] == mapping_algorithm
        and row["topology"] == topology
        and row["route_policy"] == route_policy
    ]
    if not selected:
        raise ValueError("the requested workload/mapping/topology/route slice is empty")
    return selected


def validate_grid(rows: list[dict[str, str]], expected_seeds: int) -> list[int]:
    policies = set(POLICY_ORDER)
    actual_policies = {row["policy"] for row in rows}
    if actual_policies != policies:
        raise ValueError(f"policy set mismatch: expected {policies}, got {actual_policies}")
    totals = sorted({int(row["total_memories_per_core"]) for row in rows})
    for total in totals:
        subset = [row for row in rows if int(row["total_memories_per_core"]) == total]
        for policy in POLICY_ORDER:
            policy_rows = [row for row in subset if row["policy"] == policy]
            expected_allocations = {0} if policy == "ODG" else set(range(total))
            allocations = {int(row["compiler_memories_per_core"]) for row in policy_rows}
            if allocations != expected_allocations or len(policy_rows) != len(expected_allocations):
                raise ValueError(
                    f"incomplete grid for M={total}, {policy}: expected "
                    f"{sorted(expected_allocations)}, got {sorted(allocations)}"
                )
            counts = {int(row["physics_seed_count"]) for row in policy_rows}
            if counts != {expected_seeds}:
                raise ValueError(
                    f"seed-count mismatch for M={total}, {policy}: {sorted(counts)}"
                )
            incomplete = [row for row in policy_rows if float(row["completion_rate_mean"]) != 1.0]
            if incomplete:
                raise ValueError(f"incomplete simulator requests for M={total}, {policy}")
    return totals


def number(row: dict[str, str], metric: str, suffix: str = "mean") -> float:
    value = row.get(f"{metric}_{suffix}", "")
    return math.nan if value in (None, "") else float(value)


def observed_minima(rows: list[dict[str, str]], totals: list[int]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for total in totals:
        for policy in POLICY_ORDER:
            candidates = [
                row for row in rows
                if int(row["total_memories_per_core"]) == total and row["policy"] == policy
            ]
            minimum = min(number(row, "request_latency_mean_ms") for row in candidates)
            tied = [
                row for row in candidates
                if math.isclose(number(row, "request_latency_mean_ms"), minimum,
                                rel_tol=0.0, abs_tol=1e-12)
            ]
            chosen = min(tied, key=lambda row: int(row["compiler_memories_per_core"]))
            result: dict[str, Any] = {
                "workload": chosen["workload"],
                "mapping_algorithm": chosen["mapping_algorithm"],
                "topology": chosen["topology"],
                "route_policy": chosen["route_policy"],
                "total_memories_per_core": total,
                "policy": policy,
                "selected_compiler_memories_per_core": int(chosen["compiler_memories_per_core"]),
                "latency_tied_compiler_allocations": ";".join(
                    str(int(row["compiler_memories_per_core"]))
                    for row in sorted(tied, key=lambda item: int(item["compiler_memories_per_core"]))
                ),
                "physics_seed_count": int(chosen["physics_seed_count"]),
                "selection_rule": "minimum observed mean request latency; lowest C breaks exact ties",
                "raw_output_path": chosen["raw_output_path"],
            }
            for metric, _, _ in METRIC_PANELS:
                result[f"{metric}_mean"] = number(chosen, metric)
                result[f"{metric}_sd"] = number(chosen, metric, "sd")
            for metric in (
                "average_admission_wait_ms", "requests_that_waited_fraction",
                "intended_request_hit_rate", "on_demand_fallback_rate",
                "protocol_waste_percentage", "compiler_waste_percentage",
                "compiler_expiry_percentage", "average_storage_time_ms",
            ):
                result[f"{metric}_mean"] = number(chosen, metric)
                result[f"{metric}_sd"] = number(chosen, metric, "sd")
            output.append(result)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_envelope(path: Path, minima: list[dict[str, Any]], totals: list[int],
                  figure_title: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    x = list(range(len(totals)))
    for axis, (metric, panel_title, unit) in zip(axes.flat, METRIC_PANELS):
        for policy_index, policy in enumerate(POLICY_ORDER):
            selected = [row for row in minima if row["policy"] == policy]
            y = [float(row[f"{metric}_mean"]) for row in selected]
            error = [float(row[f"{metric}_sd"]) for row in selected]
            offset = (policy_index - (len(POLICY_ORDER) - 1) / 2) * 0.025
            policy_x = [value + offset for value in x]
            axis.errorbar(policy_x, y, yerr=error, marker="o", linewidth=1.8, capsize=2,
                          label=policy, color=POLICY_COLORS[policy])
        axis.set_title(panel_title)
        axis.set_xticks(x, [str(value) for value in totals])
        axis.set_xlabel("Total communication memories per core, M")
        axis.set_ylabel(f"{panel_title} ({unit})" if unit else panel_title)
        axis.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle(f"{figure_title}: observed latency-minimum allocation per policy")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)


def plot_all_allocations(path: Path, rows: list[dict[str, str]], totals: list[int],
                         title: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True, sharex=True)
    non_odg = POLICY_ORDER[1:]
    cmap = plt.get_cmap("viridis")
    for axis, policy in zip(axes.flat, non_odg):
        for index, total in enumerate(totals):
            color = cmap(index / max(1, len(totals) - 1))
            selected = sorted(
                (row for row in rows if row["policy"] == policy
                 and int(row["total_memories_per_core"]) == total),
                key=lambda row: int(row["compiler_memories_per_core"]),
            )
            x = [int(row["compiler_memories_per_core"]) / total for row in selected]
            y = [number(row, "request_latency_mean_ms") for row in selected]
            axis.plot(x, y, marker=".", linewidth=1.2,
                      color=color, label=f"M={total}")
            odg = number(next(
                row for row in rows if row["policy"] == "ODG"
                and int(row["total_memories_per_core"]) == total
            ), "request_latency_mean_ms")
            axis.hlines(odg, 0.0, (total - 1) / total, color=color,
                        linestyle="--", linewidth=0.8, alpha=0.55)
        axis.set_title(policy)
        axis.set_xlabel("Compiler allocation fraction, C/M")
        axis.set_ylabel("Mean request latency (ms)")
        axis.grid(alpha=0.25)
    axes[0, 0].legend(ncol=3, fontsize=7)
    fig.suptitle(f"{title}: every tested compiler-memory allocation")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)


def tex(value: Any, digits: int = 4) -> str:
    number_value = float(value)
    return "--" if math.isnan(number_value) else f"{number_value:.{digits}f}"


def write_latex(path: Path, minima: list[dict[str, Any]], source_url: str,
                optima_url: str, display_name: str, label_prefix: str,
                envelope_graphic: str, allocation_graphic: str,
                expected_seeds: int) -> None:
    lines = [
        "% Generated by tools/golden_study/analyze_memory_sweep.py; do not edit.",
        "\\begin{figure}[H]", "\\centering",
        f"\\includegraphics[width=\\linewidth]{{{envelope_graphic}}}",
        (f"\\caption{{Observed latency-minimum envelope for the complete {display_name} "
         "memory sweep. Error bars are sample standard deviations across "
         f"{expected_seeds} paired physics seeds. \\href{{{source_url}}}{{Source CSV}}.}}"),
        f"\\label{{fig:{label_prefix}-envelope}}", "\\end{figure}", "",
        "\\begin{figure}[H]", "\\centering",
        f"\\includegraphics[width=\\linewidth]{{{allocation_graphic}}}",
        ("\\caption{All tested compiler-memory allocations for the same slice. "
         "Dashed lines are the total-memory-matched ODG baselines. This plot "
         "contains every $C\\in[0,M-1]$, not "
         f"only the observed minima. \\href{{{source_url}}}{{Source CSV}}.}}"),
        f"\\label{{fig:{label_prefix}-all-allocations}}", "\\end{figure}", "",
        "\\begin{landscape}", "\\scriptsize",
        "\\begin{longtable}{rrlrrrrr}",
        ("\\caption{Complete numeric table for the observed latency-minimum envelope. "
         f"\\href{{{optima_url}}}{{Source CSV}}.}}"
         f"\\label{{tab:{label_prefix}-envelope}}\\\\"),
        "\\toprule",
        "$M$ & $C$ & Policy & Latency (ms) & p95 (ms) & Makespan (ms) & Fidelity & Protocol waste (\\%) \\\\",
        "\\midrule", "\\endfirsthead", "\\toprule",
        "$M$ & $C$ & Policy & Latency (ms) & p95 (ms) & Makespan (ms) & Fidelity & Protocol waste (\\%) \\\\",
        "\\midrule", "\\endhead",
    ]
    for row in minima:
        lines.append(
            f"{row['total_memories_per_core']} & {row['selected_compiler_memories_per_core']} & "
            f"{row['policy']} & {tex(row['request_latency_mean_ms_mean'])} & "
            f"{tex(row['request_latency_p95_ms_mean'])} & "
            f"{tex(row['end_to_end_latency_ms_mean'], 2)} & "
            f"{tex(row['average_delivered_epr_fidelity_mean'], 5)} & "
            f"{tex(row['protocol_waste_percentage_mean'], 2)} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{longtable}", "\\end{landscape}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--mapping-algorithm", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--route-policy", required=True)
    parser.add_argument("--expected-seeds", type=int, required=True)
    parser.add_argument("--optima-output", type=Path, required=True)
    parser.add_argument("--figure-prefix", type=Path, required=True)
    parser.add_argument("--latex-output", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--optima-url", required=True)
    parser.add_argument("--latex-figure-prefix", required=True)
    parser.add_argument("--latex-display-name", required=True)
    parser.add_argument("--latex-label-prefix", required=True)
    args = parser.parse_args()

    rows = read_slice(
        args.input.resolve(), workload=args.workload,
        mapping_algorithm=args.mapping_algorithm, topology=args.topology,
        route_policy=args.route_policy,
    )
    totals = validate_grid(rows, args.expected_seeds)
    minima = observed_minima(rows, totals)
    write_csv(args.optima_output.resolve(), minima)
    envelope = args.figure_prefix.resolve().with_name(args.figure_prefix.name + "_envelope.png")
    allocations = args.figure_prefix.resolve().with_name(args.figure_prefix.name + "_all_allocations.png")
    title = f"{args.workload.upper()} / {args.mapping_algorithm} / {args.topology}-{args.route_policy.upper()}"
    plot_envelope(envelope, minima, totals, title)
    plot_all_allocations(allocations, rows, totals, title)
    write_latex(
        args.latex_output.resolve(), minima, args.source_url, args.optima_url,
        args.latex_display_name, args.latex_label_prefix,
        args.latex_figure_prefix + "_envelope.pdf",
        args.latex_figure_prefix + "_all_allocations.pdf",
        args.expected_seeds,
    )
    print(f"validated {len(rows)} aggregate rows; wrote {len(minima)} observed-minimum rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
