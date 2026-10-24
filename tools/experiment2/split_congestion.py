#!/usr/bin/env python3
"""Experiment 2: split each core's congestion into its own endpoint demand and its relay demand.

Definitions (docs/plans/ace-correctness-and-congestion-program.md, B2)

* A *route* is the consecutive hops of one qubit within one layer, each hop starting where the previous one ended.
  The first source and the final destination of a route are its *endpoints*; every core between them is a *relay*.
* Variant ``hop`` (the archive's counting).  For a core and a layer, D is the number of hops touching the core.
  D_end counts the touches that are a route endpoint (the source side of the route's first hop, the destination side of
  its last hop); D_relay counts the rest, so a relay contributes two (one arriving hop, one leaving hop).
  D = D_end + D_relay.
* Variant ``route`` (qubits in flight under per-qubit ordering).  The hops of a route run one after another, so a route
  needs at most one memory at a core at a time.  R is the number of routes touching the core, R_end those for which the
  core is an endpoint (also if it is a relay of the same route too), R_relay = R - R_end.
* With capacity C a layer is *overloaded* for the core when D > C (R > C for ``route``).  It is *own* overload when
  D_end > C, and *relay-only* overload when D_end <= C < D.  The two sets are disjoint and together are exactly the
  overloaded layers, so own% + relay-only% is the heatmap's overloaded%.
* Percentages are over communication-active layers (at least one hop), per mapping seed, then the equal-weight mean.
* Also reported for the overloaded layers: the mean share of demand that is relay, and the relay share of the excess,
  (max(0, D - C) - max(0, D_end - C)) / max(0, D - C) summed over layers: the part of the excess that endpoint demand
  alone would not have caused.

    python tools/experiment2/split_congestion.py --output out/exp2 --capacity 4
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "congestion_study"))
sys.path.insert(0, str(REPO / "tools" / "heatmap"))
from hotspot_analysis import read_trace                                   # noqa: E402
import regenerate_heatmap as heatmap                                      # noqa: E402

ARCHIVE, PREFIX, SEEDS, ORDER = heatmap.ARCHIVE, heatmap.PREFIX, heatmap.SEEDS, heatmap.ORDER
CORES = 16
VARIANTS = ("hop", "route")


def routes_of_layer(hops) -> list[list[int]]:
    """Cores each route of one layer visits, in order.  A route continues while the same qubit's next hop starts where
    the previous one ended (the archive's rule; such hops are adjacent in the layer's listing)."""
    chains: list[tuple[int, list[int]]] = []
    for hop in hops:
        if chains and chains[-1][0] == hop.qubit and chains[-1][1][-1] == hop.source:
            chains[-1][1].append(hop.target)
        else:
            chains.append((hop.qubit, [hop.source, hop.target]))
    return [path for _, path in chains]


def layer_demand(hops, variant: str) -> dict[int, tuple[int, int]]:
    """core -> (demand, endpoint demand) of one layer."""
    total, end = Counter(), Counter()
    for path in routes_of_layer(hops):
        last = len(path) - 1
        if variant == "hop":
            for index, core in enumerate(path):
                at_end = index in (0, last)
                total[core] += 1 if at_end else 2           # an end touches one hop, a relay two
                end[core] += 1 if at_end else 0
        elif variant == "route":
            for core in set(path):
                total[core] += 1
                end[core] += core in (path[0], path[-1])
        else:
            raise ValueError(variant)
    return {core: (total[core], end[core]) for core in total}


def split_trace(trace, capacity: int, variant: str) -> dict:
    """Per-core counts for one trial."""
    by_layer = defaultdict(list)
    for hop in trace.hops:
        by_layer[hop.layer].append(hop)
    active = len(by_layer)
    stats = {core: Counter() for core in range(trace.cores)}
    for hops in by_layer.values():
        for core, (demand, endpoint) in layer_demand(hops, variant).items():
            s = stats[core]
            s["demand_sum"] += demand
            s["relay_sum"] += demand - endpoint
            if demand > capacity:
                s["over"] += 1
                s["relay_share_sum"] += (demand - endpoint) / demand
                if endpoint > capacity:
                    s["own"] += 1
                else:
                    s["relay_only"] += 1
            s["excess"] += max(0, demand - capacity)
            s["excess_from_relay"] += max(0, demand - capacity) - max(0, endpoint - capacity)
            s["peak_demand"] = max(s["peak_demand"], demand)
    rows = {}
    for core, s in stats.items():
        pct = lambda n: 100.0 * n / active if active else 0.0
        rows[core] = {
            "active_layers": active, "overloaded_layers": s["over"], "own_layers": s["own"],
            "relay_only_layers": s["relay_only"], "overloaded_percent": pct(s["over"]),
            "own_percent": pct(s["own"]), "relay_only_percent": pct(s["relay_only"]),
            "mean_relay_share_when_overloaded": s["relay_share_sum"] / s["over"] if s["over"] else None,
            "relay_share_of_excess": s["excess_from_relay"] / s["excess"] if s["excess"] else None,
            "incident_hops": s["demand_sum"], "relay_incidences": s["relay_sum"], "peak_demand": s["peak_demand"],
        }
    return rows


def compute(capacity: int = 4, variant: str = "hop", directory: Path | None = None, topology: str = "mesh",
            traces_dir: Path | None = None) -> dict:
    """workload -> seed -> core -> row, from the archive's raw traces."""
    own = tempfile.TemporaryDirectory() if directory is None else None
    base = Path(own.name) if own else directory
    out: dict = {}
    archive = zipfile.ZipFile(ARCHIVE) if traces_dir is None else None
    try:
        for key, _ in ORDER:
            out[key] = {}
            for seed in SEEDS:
                if traces_dir is None:
                    path = Path(archive.extract(f"{PREFIX}/{key}/seed_{seed}/requests.txt", base))
                else:
                    path = Path(traces_dir) / key / f"seed_{seed}" / "requests.txt"
                out[key][seed] = split_trace(read_trace(path, 4, 4, topology), capacity, variant)
    finally:
        if archive is not None:
            archive.close()
        if own:
            own.cleanup()
    return out


def mean_over_seeds(data: dict, workload: str, core: int, field: str):
    values = [data[workload][s][core][field] for s in SEEDS]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


FIELDS = ["overloaded_percent", "own_percent", "relay_only_percent", "mean_relay_share_when_overloaded",
          "relay_share_of_excess"]


def write_csv(data: dict, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["workload", "core", "row", "column"] + [f"mean_{f}" for f in FIELDS] +
                        [f"seed{s}_{f}" for s in SEEDS for f in ("overloaded_percent", "own_percent", "relay_only_percent")] +
                        [f"seed{s}_relay_incidences" for s in SEEDS] + [f"seed{s}_incident_hops" for s in SEEDS])
        for key, _ in ORDER:
            for core in range(CORES):
                means = [mean_over_seeds(data, key, core, f) for f in FIELDS]
                writer.writerow([key, core, core // 4, core % 4] +
                                ["" if m is None else f"{m:.6f}" for m in means] +
                                [f"{data[key][s][core][f]:.6f}" for s in SEEDS
                                 for f in ("overloaded_percent", "own_percent", "relay_only_percent")] +
                                [data[key][s][core]["relay_incidences"] for s in SEEDS] +
                                [data[key][s][core]["incident_hops"] for s in SEEDS])


def draw(data: dict, capacity: int, variant: str, path: Path, workloads=None, figwidth=8.2, rowheight=3.4, text=6, title_size=8, dpi=130) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shown = workloads or [k for k, _ in ORDER if max(mean_over_seeds(data, k, c, "overloaded_percent") for c in range(CORES)) > 0.5]
    titles = dict(ORDER)
    panels = [("own_percent", "Overloaded by the core's own endpoint demand (%)"),
              ("relay_only_percent", "Overloaded only because of relay traffic (%)")]
    figure, axes = plt.subplots(len(shown), 2, figsize=(figwidth, rowheight * len(shown)), squeeze=False)
    image = None
    for r, key in enumerate(shown):
        for c, (field, title) in enumerate(panels):
            axis = axes[r][c]
            grid = [[mean_over_seeds(data, key, row * 4 + col, field) for col in range(4)] for row in range(4)]
            image = axis.imshow(grid, cmap="YlOrRd", vmin=0, vmax=100)
            axis.set_xticks(range(4)); axis.set_yticks(range(4))
            axis.set_title(f"{titles[key]}: " + ("own demand" if c == 0 else "relay only"), fontsize=title_size)
            for row in range(4):
                for col in range(4):
                    v = grid[row][col]
                    axis.text(col, row, f"C{row * 4 + col}\n{v:.1f}%", ha="center", va="center", fontsize=text,
                              color="white" if v > 60 else "black")
    figure.suptitle(f"Own demand vs relay demand per core ({variant} counting, capacity {capacity})", fontsize=11)
    figure.colorbar(image, ax=axes, fraction=0.03, pad=0.03, label="% of communication-active layers")
    figure.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)


def draw_overview(data: dict, capacity: int, variant: str, path: Path, figsize=(16, 9.4), text=12, title_size=13, dpi=200) -> None:
    """One page: every workload that has overload, its own-demand heatmap beside its relay-only heatmap (numbers are percentages)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    titles = dict(ORDER)
    shown = [k for k, _ in ORDER if max(mean_over_seeds(data, k, c, "overloaded_percent") for c in range(CORES)) > 0.5]
    per_row = 3
    rows = -(-len(shown) // per_row)
    figure = plt.figure(figsize=figsize)
    grid = figure.add_gridspec(rows, per_row * 3, width_ratios=[1, 1, 0.28] * per_row, hspace=0.34, wspace=0.10)
    image = None
    for index, key in enumerate(shown):
        r, block = divmod(index, per_row)
        for c, field in enumerate(("own_percent", "relay_only_percent")):
            axis = figure.add_subplot(grid[r, block * 3 + c])
            values = [[mean_over_seeds(data, key, row * 4 + col, field) for col in range(4)] for row in range(4)]
            image = axis.imshow(values, cmap="YlOrRd", vmin=0, vmax=100)
            axis.set_xticks([]); axis.set_yticks([])
            axis.set_title(f"{titles[key]}\n{'own demand' if c == 0 else 'relay only'}" if c == 0 else "relay only", fontsize=title_size)
            for row in range(4):
                for col in range(4):
                    v = values[row][col]
                    axis.text(col, row, f"{v:.0f}" if v >= 10 else f"{v:.1f}", ha="center", va="center", fontsize=text, color="white" if v > 60 else "black")
    counting = "hop counting" if variant == "hop" else "route counting (qubits in flight)"
    figure.suptitle(f"Per-core overload at capacity {capacity}, {counting}: % of communication-active layers (mean of three mapping seeds)", fontsize=title_size + 2)
    colorbar_axis = figure.add_axes([0.93, 0.15, 0.012, 0.7])
    figure.colorbar(image, cax=colorbar_axis, label="% of active layers")
    figure.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capacity", type=int, default=4)
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    parser.add_argument("--traces-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        data = compute(args.capacity, variant, topology=args.topology, traces_dir=args.traces_dir)
        write_csv(data, args.output / f"split_{variant}.csv")
        draw(data, args.capacity, variant, args.output / f"split_{variant}.png")
        print(f"wrote {args.output / f'split_{variant}.csv'} and .png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
