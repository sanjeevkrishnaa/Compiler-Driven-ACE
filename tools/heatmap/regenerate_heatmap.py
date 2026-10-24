#!/usr/bin/env python3
"""Regenerate the per-core congestion heatmap from the raw mapped traces.

For every trace and layer, a core's demand is the number of hops that touch it (every trace hop joins
two adjacent cores, so a hop is an endpoint incidence at both).  A core is overloaded in a layer when its
demand exceeds the slot capacity (default 4).  The percentage is overloaded layers over communication-active
layers (layers with at least one request), averaged with equal weight over the mapping seeds.

Traces come from the committed archive; parsing uses the validated reader in ``tools/congestion_study``.
Nothing is read from the archive's precomputed CSVs, so the result is an independent check of them.

    python tools/heatmap/regenerate_heatmap.py --output out/heatmap
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "congestion_study"))
from hotspot_analysis import read_trace                          # noqa: E402

ARCHIVE = REPO / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
PREFIX = "mqt_ten_workload_study"
ROWS = COLUMNS = 4
SEEDS = (42, 43, 44)
ORDER = [("bmw_quark_cardinality", "BMW / QUARK cardinality"), ("qft", "QFT"), ("draper_qft_adder", "Draper QFT adder"),
         ("bv", "Bernstein–Vazirani"), ("qaoa", "QAOA"), ("ghz", "GHZ"), ("cdkm_ripple_carry_adder", "CDKM ripple-carry adder"),
         ("vqe_real_amp", "VQE real amplitudes"), ("graphstate", "Graph state"), ("randomcircuit", "Random circuit")]


def core_percentages(trace, capacity: int) -> tuple[list[float], int, int]:
    """(percent of active layers each core is overloaded, active layers, layers with any overload)."""
    by_layer: dict[int, Counter] = {}
    for hop in trace.hops:
        by_layer.setdefault(hop.layer, Counter()).update([hop.source, hop.target])
    active = len(by_layer)
    over = Counter()
    any_over = 0
    for demand in by_layer.values():
        hot = [core for core, d in demand.items() if d > capacity]
        over.update(hot)
        any_over += bool(hot)
    return [100.0 * over[c] / active if active else 0.0 for c in range(trace.cores)], active, any_over


def compute(capacity: int = 4, directory: Path | None = None, topology: str = 'mesh',
            traces_dir: Path | None = None) -> dict[str, dict]:
    own = tempfile.TemporaryDirectory() if directory is None else None
    base = Path(own.name) if own else directory
    result = {}
    try:
        archive = zipfile.ZipFile(ARCHIVE) if traces_dir is None else None
        try:
            for key, _ in ORDER:
                per_seed = []
                for seed in SEEDS:
                    if traces_dir is None:
                        path = Path(archive.extract(f"{PREFIX}/{key}/seed_{seed}/requests.txt", base))
                    else:
                        path = Path(traces_dir) / key / f"seed_{seed}" / "requests.txt"
                    per_seed.append(core_percentages(read_trace(path, ROWS, COLUMNS, topology), capacity))
                result[key] = {
                    "mean": [sum(s[0][c] for s in per_seed) / len(per_seed) for c in range(ROWS * COLUMNS)],
                    "per_seed": {seed: s[0] for seed, s in zip(SEEDS, per_seed)},
                    "active_layers": {seed: s[1] for seed, s in zip(SEEDS, per_seed)},
                    "overloaded_layers": {seed: s[2] for seed, s in zip(SEEDS, per_seed)},
                }
        finally:
            if archive is not None:
                archive.close()
    finally:
        if own:
            own.cleanup()
    return result


def draw(data: dict[str, dict], capacity: int, path: Path, figsize=(21, 8.2), text=6.5, dpi=130, title_size=10) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(2, 5, figsize=figsize)
    image = None
    for axis, (key, title) in zip(axes.flat, ORDER):
        grid = [data[key]["mean"][r * COLUMNS:(r + 1) * COLUMNS] for r in range(ROWS)]
        image = axis.imshow(grid, cmap="YlOrRd", vmin=0, vmax=100)
        axis.set_title(title, fontsize=title_size)
        axis.set_xticks(range(COLUMNS)); axis.set_yticks(range(ROWS))
        axis.set_xlabel("Mesh column", fontsize=8); axis.set_ylabel("Mesh row", fontsize=8)
        for r in range(ROWS):
            for c in range(COLUMNS):
                value = grid[r][c]
                axis.text(c, r, f"C{r * COLUMNS + c}\n{value:.1f}%", ha="center", va="center", fontsize=text,
                          color="white" if value > 60 else "black")
    figure.suptitle("Per-core congestion across ten workloads", fontsize=15)
    figure.colorbar(image, ax=axes, fraction=0.012, pad=0.02, label="Overloaded communication-active layers (%)")
    figure.text(0.5, 0.01, f"Demand > {capacity} slots/core · equal-weight mean across three mapping seeds · "
                           "common 0–100% scale · zero means no overload, not no traffic", ha="center", fontsize=9)
    figure.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)


def write_csv(data: dict[str, dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["workload", "core", "mean_overloaded_percent"] + [f"seed_{s}" for s in SEEDS])
        for key, _ in ORDER:
            for core in range(ROWS * COLUMNS):
                writer.writerow([key, core, f"{data[key]['mean'][core]:.6f}"] +
                                [f"{data[key]['per_seed'][s][core]:.6f}" for s in SEEDS])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capacity", type=int, default=4)
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    parser.add_argument("--traces-dir", type=Path, default=None, help="<workload>/seed_<n>/requests.txt (default: the committed mesh archive)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    data = compute(args.capacity, topology=args.topology, traces_dir=args.traces_dir)
    write_csv(data, args.output / "per_core_percent.csv")
    draw(data, args.capacity, args.output / "per_core_congestion.png")
    print(f"wrote {args.output / 'per_core_congestion.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
