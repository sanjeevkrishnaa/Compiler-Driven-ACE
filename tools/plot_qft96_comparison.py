"""Generate reproducible QFT-96 comparison figures from summary.csv."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load(path: Path) -> dict[str, list[dict[str, float]]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return {
        strategy: [
            {
                key: float(value) if value else float("nan")
                for key, value in row.items()
                if key not in {"strategy"}
            }
            for row in rows
            if row["strategy"] == strategy
        ]
        for strategy in ("on-demand", "dynamic")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = load(args.summary)
    labels = ["ODG", "Dynamic"]
    colors = ["#2f6f9f", "#d97736"]
    args.output.mkdir(parents=True, exist_ok=True)

    def values(field: str, scale: float = 1.0):
        return [np.array([row[field] for row in data[key]]) * scale for key in ("on-demand", "dynamic")]

    latency = values("average_arrival_latency_ms")
    makespan = values("end_to_end_latency_ms", 1 / 1000)
    wait = values("average_admission_wait_ms")
    service = values("avg_entanglement_generation_time_ms")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    for ax, series, title, ylabel in (
        (axes[0], latency, "Fair request latency", "milliseconds"),
        (axes[1], makespan, "Whole-trace makespan", "seconds"),
    ):
        means = [float(np.mean(item)) for item in series]
        stds = [float(np.std(item, ddof=1)) for item in series]
        bars = ax.bar(labels, means, yerr=stds, capsize=5, color=colors, alpha=0.9)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
        for bar, mean, std in zip(bars, means, stds):
            ax.text(bar.get_x() + bar.get_width() / 2, mean, f"{mean:.3f}\n±{std:.3f}",
                    ha="center", va="bottom", fontsize=9)
    fig.suptitle("QFT-96: corrected per-qubit scheduler, 30 seeds")
    fig.savefig(args.output / "latency-makespan.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
    x = np.arange(2)
    wait_mean = [float(np.mean(item)) for item in wait]
    service_mean = [float(np.mean(item)) for item in service]
    guard_mean = [
        float(np.mean(latency[index])) - wait_mean[index] - service_mean[index]
        for index in range(2)
    ]
    ax.bar(x, wait_mean, color="#c95f5f", label="Admission wait")
    ax.bar(x, guard_mean, bottom=wait_mean, color="#d4a72c", label="RSVP/control guard")
    ax.bar(x, service_mean, bottom=np.array(wait_mean) + np.array(guard_mean),
           color="#5c9e6e", label="Generation/service")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Milliseconds per request")
    ax.set_title("Why Dynamic is slower: waiting outweighs faster generation")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    for index, total in enumerate(np.array(wait_mean) + np.array(service_mean)):
        ax.text(index, total, f"{total:.3f} ms", ha="center", va="bottom", fontsize=9)
    fig.savefig(args.output / "latency-decomposition.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
    positions = [1, 2]
    violin = ax.violinplot(latency, positions=positions, showmeans=True, showextrema=True)
    for body, color in zip(violin["bodies"], colors):
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_alpha(0.65)
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Fair request latency (ms)")
    ax.set_title("Latency distribution across 30 physics seeds")
    ax.grid(axis="y", alpha=0.25)
    fig.savefig(args.output / "latency-distribution.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
