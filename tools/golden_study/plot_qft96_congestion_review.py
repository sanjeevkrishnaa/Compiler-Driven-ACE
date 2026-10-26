#!/usr/bin/env python3
"""Create review-only QFT-96 congestion comparisons and grouped heatmap sheets.

This tool consumes the committed trace-level congestion CSV and existing
per-cell heatmaps. It does not run ACE or change any simulation output.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import fmean, stdev


ROUTES = (
    ("mesh", "xy"),
    ("mesh", "yx"),
    ("mesh", "shortest_reliable"),
    ("mesh", "max_reliability"),
    ("torus", "dijkstra"),
)
VARIANTS = ("route", "hop")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def route_label(topology: str, route: str) -> str:
    return f"{topology.title()} {route.replace('_', '-') }"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["topology"], row["route_policy"], int(row["capacity"]), row["variant"])].append(row)
    output = []
    metrics = ("overloaded_layer_percent", "overloaded_core_layers", "excess_demand")
    for (topology, route, capacity, variant), group in sorted(grouped.items()):
        result: dict[str, object] = {
            "topology": topology, "route_policy": route, "capacity": capacity,
            "variant": variant, "mapping_seed_observations": len(group),
        }
        for name in metrics:
            values = [float(row[name]) for row in group]
            result[f"{name}_mean"] = fmean(values)
            result[f"{name}_sd"] = stdev(values) if len(values) > 1 else 0.0
        output.append(result)
    return output


def plot_routing_comparison(rows: list[dict[str, object]], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = [row for row in rows if row["variant"] == "route"]
    capacities = sorted({int(row["capacity"]) for row in selected})
    panels = (
        ("overloaded_layer_percent", "Overloaded active layers", "%"),
        ("overloaded_core_layers", "Overloaded core-layers", "count"),
        ("excess_demand", "Excess route demand", "count"),
    )
    fig, axes = plt.subplots(1, len(panels), figsize=(15, 4.2), constrained_layout=True)
    for axis, (metric, title, unit) in zip(axes, panels):
        for topology, route in ROUTES:
            group = [row for row in selected if row["topology"] == topology and row["route_policy"] == route]
            lookup = {int(row["capacity"]): row for row in group}
            x = [capacity for capacity in capacities if capacity in lookup]
            y = [float(lookup[capacity][f"{metric}_mean"]) for capacity in x]
            e = [float(lookup[capacity][f"{metric}_sd"]) for capacity in x]
            axis.errorbar(x, y, yerr=e, marker="o", linewidth=1.5, capsize=3,
                          label=route_label(topology, route))
        axis.set_xscale("symlog", linthresh=2)
        axis.set_xticks(capacities, labels=[str(capacity) for capacity in capacities])
        axis.set_xlabel("Communication memories per core")
        axis.set_ylabel(unit)
        axis.set_title(title)
        axis.grid(alpha=0.25)
    axes[0].legend(fontsize=7)
    fig.suptitle("QFT-96 routing congestion: route occupancy (mean $\\pm$ sample SD across mapping seeds)")
    fig.savefig(output / "routing_congestion_by_memory.png", dpi=200)
    fig.savefig(output / "routing_congestion_by_memory.pdf")
    plt.close(fig)


def contact_sheets(root: Path, output: Path, capacities: list[int]) -> list[dict[str, object]]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    heatmaps = root / "congestion/heatmaps"
    rows: list[dict[str, object]] = []
    for topology, route in ROUTES:
        for variant in VARIANTS:
            fig, axes = plt.subplots(3, len(capacities), figsize=(25, 11), constrained_layout=True)
            for row, seed in enumerate((42, 43, 44)):
                for column, capacity in enumerate(capacities):
                    axis = axes[row][column]
                    name = f"{topology}__{route}__seed{seed}__cap{capacity}__{variant}.png"
                    path = heatmaps / name
                    if not path.is_file():
                        raise FileNotFoundError(path)
                    axis.imshow(mpimg.imread(path))
                    axis.axis("off")
                    if row == 0:
                        axis.set_title(f"M={capacity}", fontsize=13)
                    if column == 0:
                        axis.text(-0.05, 0.5, f"mapping seed {seed}", rotation=90,
                                  va="center", ha="right", transform=axis.transAxes, fontsize=12)
            fig.suptitle(f"QFT-96 congestion heatmaps: {route_label(topology, route)} / {variant} counting", fontsize=18)
            filename = f"sheet_{topology}__{route}__{variant}.png"
            fig.savefig(output / filename, dpi=180)
            plt.close(fig)
            rows.append({"topology": topology, "route_policy": route, "variant": variant,
                         "mapping_seeds": "42;43;44", "capacities": ";".join(map(str, capacities)),
                         "heatmaps_per_sheet": len(capacities) * 3, "sheet": filename})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = read_csv(root / "congestion/trace_congestion_summary.csv")
    aggregate_rows = aggregate(rows)
    write_csv(output / "routing_congestion_by_memory.csv", aggregate_rows)
    plot_routing_comparison(aggregate_rows, output)
    capacities = sorted({int(row["capacity"]) for row in rows})
    sheets = contact_sheets(root, output / "sheets", capacities)
    write_csv(output / "heatmap_sheet_index.csv", sheets)
    (output / "README.md").write_text(
        "# QFT-96 congestion review pack\n\n"
        "Review-only derivative artifacts. `routing_congestion_by_memory.csv` aggregates the route-occupancy "
        "congestion CSV across conceptual mapping seeds. The ten sheets each contain 21 original heatmaps: "
        "three mapping seeds by seven official memory capacities, for one route and counting definition.\n",
        encoding="utf-8",
    )
    print(f"wrote {len(sheets)} grouped sheets covering {sum(int(row['heatmaps_per_sheet']) for row in sheets)} heatmaps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
