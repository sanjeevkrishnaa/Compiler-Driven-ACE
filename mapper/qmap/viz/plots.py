
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from qmap.exceptions import DependencyError

__all__ = ["PALETTE", "plot_ablation", "plot_reliability", "plot_runtime", "plot_scaling"]

PALETTE: dict[str, str] = {
    "HQA": "#4C72B0",
    "HQA-NL": "#937860",
    "T-HQA": "#DD8452",
    "T-HQAR": "#8172B2",
    "TR-HQA": "#55A868",
    "GTR-QA": "#C44E52",
}
"""Per-algorithm colours, held constant across every figure."""

_MARKERS: dict[str, str] = {
    "HQA": "o",
    "HQA-NL": "v",
    "T-HQA": "s",
    "T-HQAR": "P",
    "TR-HQA": "D",
    "GTR-QA": "^",
}

def _pyplot() -> Any:
    try:
        import matplotlib
    except ModuleNotFoundError as exc:
        raise DependencyError(
            "matplotlib is required for plotting; install it with "
            "'pip install matplotlib' or 'pip install -e .[viz]'"
        ) from exc

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    return plt

def _style(axis: Any) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="y", alpha=0.3, linewidth=0.6)
    axis.set_axisbelow(True)

def _save(figure: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt = _pyplot()
    plt.close(figure)
    return path

def _by_placer(
    rows: list[dict[str, Any]], x_key: str, y_key: str, filter_key: str | None = None,
    filter_value: Any = None,
) -> dict[str, list[tuple[Any, float]]]:
    series: dict[str, list[tuple[Any, float]]] = defaultdict(list)
    for row in rows:
        if filter_key is not None and row.get(filter_key) != filter_value:
            continue
        if row.get(y_key) is None:
            continue
        series[str(row["placer"])].append((row[x_key], float(row[y_key])))
    return {name: sorted(points) for name, points in series.items()}

def plot_scaling(
    summary: list[dict[str, Any]], directory: Path, *, benchmark: str
) -> Path:
    plt = _pyplot()
    series = _by_placer(summary, "n_cores", "mean_cost", "benchmark", benchmark)

    figure, axis = plt.subplots(figsize=(6.0, 4.0))
    for name, points in series.items():
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        axis.plot(
            xs, ys, marker=_MARKERS.get(name, "o"), color=PALETTE.get(name),
            label=name, linewidth=1.6, markersize=5,
        )
    axis.set_xscale("log", base=2)
    axis.set_yscale("log")
    axis.set_xlabel("Number of cores")
    axis.set_ylabel("Expected inter-core communication cost")
    axis.set_title(f"Strong scaling --- {benchmark}")
    axis.legend(frameon=False, fontsize=9)
    _style(axis)
    return _save(figure, directory / f"scaling_cost_{benchmark}.png")

def plot_runtime(
    summary: list[dict[str, Any]], directory: Path, *, benchmark: str
) -> Path:
    plt = _pyplot()
    series = _by_placer(
        summary, "n_cores", "min_runtime_seconds", "benchmark", benchmark
    )

    figure, axis = plt.subplots(figsize=(6.0, 4.0))
    for name, points in series.items():
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        axis.plot(
            xs, ys, marker=_MARKERS.get(name, "o"), color=PALETTE.get(name),
            label=name, linewidth=1.6, markersize=5,
        )
    axis.set_xscale("log", base=2)
    axis.set_yscale("log")
    axis.set_xlabel("Number of cores")
    axis.set_ylabel("Mapping runtime (s)")
    axis.set_title(f"Mapping runtime --- {benchmark}")
    axis.legend(frameon=False, fontsize=9)
    _style(axis)
    return _save(figure, directory / f"scaling_runtime_{benchmark}.png")

def _grouped_bars(
    summary: list[dict[str, Any]],
    directory: Path,
    *,
    filename: str,
    title: str,
    ylabel: str,
) -> Path:
    plt = _pyplot()

    bands: list[str] = []
    for row in summary:
        band = str(row["reliability_band"])
        if band not in bands:
            bands.append(band)

    placers: list[str] = []
    for row in summary:
        name = str(row["placer"])
        if name not in placers:
            placers.append(name)

    lookup = {
        (str(row["placer"]), str(row["reliability_band"])): float(row["mean_cost"])
        for row in summary
    }

    figure, axis = plt.subplots(figsize=(7.0, 4.0))
    width = 0.8 / max(len(placers), 1)
    for index, name in enumerate(placers):
        offsets = [position + index * width for position in range(len(bands))]
        heights = [lookup.get((name, band), 0.0) for band in bands]
        axis.bar(
            offsets, heights, width=width, label=name,
            color=PALETTE.get(name), edgecolor="white", linewidth=0.5,
        )
    axis.set_xticks([
        position + width * (len(placers) - 1) / 2 for position in range(len(bands))
    ])
    axis.set_xticklabels(bands)
    axis.set_xlabel("Entanglement link reliability")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.legend(frameon=False, fontsize=9)
    _style(axis)
    return _save(figure, directory / filename)

def plot_reliability(summary: list[dict[str, Any]], directory: Path) -> Path:
    return _grouped_bars(
        summary,
        directory,
        filename="reliability_cost.png",
        title="Impact of entanglement link reliability",
        ylabel="Expected inter-core communication cost",
    )

def plot_ablation(summary: list[dict[str, Any]], directory: Path) -> Path:
    return _grouped_bars(
        summary,
        directory,
        filename="ablation_cost.png",
        title="TR-HQA against idealised topology-aware mapping",
        ylabel="Expected inter-core communication cost",
    )
