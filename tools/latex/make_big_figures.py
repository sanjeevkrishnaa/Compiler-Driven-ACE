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


def landscape(name: str, png: str, caption: str, label: str) -> None:
    (GEN / name).write_text("\n".join([
        r"\begin{landscape}", r"\begin{figure}[p]", r"\centering",
        rf"\includegraphics[width=\linewidth,height=0.80\textheight,keepaspectratio]{{{png}}}",
        rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{figure}", r"\end{landscape}"]) + "\n", encoding="utf-8")


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

    # Experiment 2: per capacity and counting, three workloads to a figure, one figure per page
    titles = dict(S.ORDER)
    blocks = []
    for cap, variant in ((4, "hop"), (4, "route"), (2, "hop"), (1, "hop"), (3, "hop")):
        data = S.compute(cap, variant)
        shown = [k for k, _ in S.ORDER if max(S.mean_over_seeds(data, k, c, "overloaded_percent") for c in range(16)) > 0.5]
        for i in range(0, len(shown), 3):
            chunk = shown[i:i + 3]
            name = f"exp2_big_c{cap}_{variant}_{i // 3}.png"
            S.draw(data, cap, variant, FIG / name, workloads=chunk, figwidth=9.6, rowheight=4.2, text=10, title_size=11, dpi=150)
            counting = "hop counting" if variant == "hop" else "route counting (qubits in flight)"
            blocks.append("\n".join([
                r"\begin{figure}[p]", r"\centering", rf"\includegraphics[width=\linewidth,height=0.86\textheight,keepaspectratio]{{{name}}}",
                rf"\caption{{Own endpoint demand (left) against relay-only overload (right), capacity {cap}, {counting}: "
                + ", ".join(titles[k] for k in chunk) + r". Percentage of active layers, mean of three mapping seeds.}",
                rf"\label{{fig:exp2-c{cap}-{variant}-{i // 3}}}", r"\end{figure}"]))
    (GEN / "exp2_figs.tex").write_text("\n".join(blocks) + "\n", encoding="utf-8")
    print("rendered big figures;", len(blocks), "Experiment 2 figure pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
