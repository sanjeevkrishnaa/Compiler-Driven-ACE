#!/usr/bin/env python3
"""Render the report's figures large: natively bigger fonts and resolution, landscape pages for the wide small-multiples, and the
per-core figures split a few workloads to a page.  Run after make_tables.py and make_full_tables.py (it overwrites the figure files
and wrappers they wrote).

    python tools/latex/make_big_figures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "latex" / "ace_report"
GEN, FIG = OUT / "generated", OUT / "figures"
RES = REPO / "results"
for sub in ("heatmap", "experiment1", "experiment2", "latex"):
    sys.path.insert(0, str(REPO / "tools" / sub))
import analyze as A                                                           # noqa: E402
import regenerate_heatmap as H                                                # noqa: E402
import split_congestion as S                                                  # noqa: E402

MAIN = RES / "experiment1_ten_benchmarks_2026-10-24"
TORUS_TRACES = RES / "torus_traces_2026-10-24"


LANDSCAPE_OPEN = r"\clearpage\newgeometry{margin=12mm}\begin{landscape}"
LANDSCAPE_CLOSE = r"\end{landscape}\clearpage\restoregeometry"


def landscape(name: str, png: str, caption: str, label: str) -> None:
    """One figure on its own landscape page with narrow margins, as large as the page allows."""
    (GEN / name).write_text("\n".join([
        LANDSCAPE_OPEN, r"\begin{figure}[p]", r"\centering",
        rf"\includegraphics[width=\linewidth,height=0.82\textheight,keepaspectratio]{{{png}}}",
        rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{figure}", LANDSCAPE_CLOSE]) + "\n", encoding="utf-8")


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    rows = A.load(MAIN / "results.csv")
    g = A.cells(rows)
    spec = dict(figsize=(17.5, 8.8), scale=1.85, dpi=150)
    A.figure(g, "latency_ms", "request latency (ms)", FIG / "latency_vs_budget.png", log_y=True,
             title="Request latency against communication memories per core", **spec)
    A.figure(g, "fidelity", "delivered EPR fidelity", FIG / "fidelity_vs_budget.png", title="Delivered EPR fidelity against communication memories per core", **spec)
    A.figure(g, "waited_fraction", "fraction of requests that waited", FIG / "waiting_vs_budget.png", title="Requests that had to wait for a free memory", **spec)
    tail = " Line: mean of nine runs; band: minimum to maximum; grey: counterfactual budgets (beyond the modelled four)."
    landscape("fig_latency_vs_budget.tex", "latency_vs_budget.png", "Request latency (ms, log scale) against communication memories per core, on-demand and dynamic." + tail, "fig:exp1-latency")
    landscape("fig_fidelity_vs_budget.tex", "fidelity_vs_budget.png", "Delivered EPR fidelity against communication memories per core. On-demand is constant; dynamic falls as the compiler bank grows." + tail, "fig:exp1-fidelity")
    landscape("fig_waiting_vs_budget.tex", "waiting_vs_budget.png", "Fraction of requests that had to wait for a free memory." + tail, "fig:exp1-waiting")

    big = dict(figsize=(16, 7.6), text=10.5, dpi=150, title_size=13)
    H.draw(H.compute(4), 4, FIG / "per_core_congestion.png", **big)
    landscape("fig_heatmap.tex", "per_core_congestion.png",
              "Per-core congestion on the mesh: percentage of communication-active layers in which a core's demand exceeds 4 slots (mean over three mapping seeds). All 160 cells match the project's earlier figure at 0.1\\% resolution.", "fig:heatmap")
    H.draw(H.compute(4, topology="torus", traces_dir=TORUS_TRACES), 4, FIG / "per_core_congestion_torus.png", **big)
    landscape("fig_heatmap_torus.tex", "per_core_congestion_torus.png",
              "Per-core congestion on the torus (same definition, same capacity 4, mean over three mapping seeds).", "fig:heatmap-torus")

    # Experiment 2: one landscape page per capacity and counting, every workload side by side
    figs = []
    for cap, variant in ((4, "hop"), (4, "route"), (2, "hop"), (1, "hop"), (3, "hop")):
        name = f"exp2_overview_c{cap}_{variant}.png"
        S.draw_overview(S.compute(cap, variant), cap, variant, FIG / name)
        counting = "hop counting" if variant == "hop" else "route counting (qubits in flight)"
        figs.append("\n".join([
            r"\begin{landscape}", r"\begin{figure}[p]", r"\centering",
            rf"\includegraphics[width=\linewidth,height=0.80\textheight,keepaspectratio]{{{name}}}",
            rf"\caption{{Capacity {cap}, {counting}. For each workload with overload, the left heatmap is the percentage of its active layers in which the core is overloaded by its own endpoint demand and the right heatmap the percentage in which it is overloaded only because of relay traffic. Mesh cores are numbered row by row (core 10 is row 2, column 2). Mean of three mapping seeds.}}",
            rf"\label{{fig:exp2-overview-c{cap}-{variant}}}", r"\end{figure}", r"\end{landscape}"]))
    (GEN / "exp2_figs.tex").write_text("\n".join(figs) + "\n", encoding="utf-8")

    # mesh above torus, one page, every workload
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mesh, torus = H.compute(4), H.compute(4, topology="torus", traces_dir=TORUS_TRACES)
    figure = plt.figure(figsize=(16, 8.9))
    grid = figure.add_gridspec(3, 12, width_ratios=[1, 1, 0.3] * 4, hspace=0.36, wspace=0.10)
    image = None
    for i, (key, title) in enumerate(H.ORDER):
        r0, block = divmod(i, 4)
        for offset, (data, label) in enumerate(((mesh, "mesh"), (torus, "torus"))):
            axis = figure.add_subplot(grid[r0, block * 3 + offset])
            values = [data[key]["mean"][r * 4:(r + 1) * 4] for r in range(4)]
            image = axis.imshow(values, cmap="YlOrRd", vmin=0, vmax=100)
            axis.set_xticks([]); axis.set_yticks([])
            axis.set_title(f"{title}\n{label}" if offset == 0 else label, fontsize=11)
            for r in range(4):
                for col in range(4):
                    v = values[r][col]
                    axis.text(col, r, f"{v:.0f}" if v >= 10 else f"{v:.1f}", ha="center", va="center", fontsize=9.5, color="white" if v > 60 else "black")
    figure.suptitle("Per-core congestion at capacity 4: mesh (left) beside torus (right) for every workload (% of active layers, mean of three mapping seeds)", fontsize=13)
    figure.colorbar(image, cax=figure.add_axes([0.93, 0.15, 0.012, 0.7]), label="% of active layers")
    figure.savefig(FIG / "mesh_vs_torus_heatmaps.png", dpi=170, bbox_inches="tight")
    plt.close(figure)
    landscape("fig_mesh_vs_torus.tex", "mesh_vs_torus_heatmaps.png",
              "Per-core congestion at capacity 4 on the mesh (left of each pair) and on the torus (right), for every workload. The torus lowers the overload in five workloads, leaves four unchanged and raises it for graph state; the traces differ in placement as well as topology.", "fig:mesh-vs-torus")
    print("rendered big figures;", len(figs), "Experiment 2 overview pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
