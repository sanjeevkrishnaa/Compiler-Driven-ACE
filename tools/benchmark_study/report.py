"""Figures, tables and the LaTeX section of each analysed benchmark and route.

    <venv with pandas+matplotlib>/bin/python tools/benchmark_study/report.py

Reads results/benchmark_study_2026-11-04/per_seed.csv (written by analyze.py).  For every benchmark-route pair it writes
  docs/latex/benchmark_study/figures/<benchmark>_<route>_headline.pdf   five configurations, five metrics
  docs/latex/benchmark_study/figures/<benchmark>_<route>_k_<metric>.pdf  every strategy at every K
  docs/latex/benchmark_study/generated/<benchmark>_<route>.tex          tables and figure blocks
and docs/latex/benchmark_study/generated/sections.tex, the list main.tex includes.  Bars are the mean of the seeds; the
whisker spans the lowest and highest seed.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "results" / "benchmark_study_2026-11-04" / "per_seed.csv"
DOC = ROOT / "docs" / "latex" / "benchmark_study"
K_ORDER = ["1", "2", "3", "4", "6", "8", "inf"]
NAMES = {"qft": "QFT", "bv": "BV", "ghz": "GHZ", "dj": "DJ", "qpeexact": "QPE (exact)", "qaoa": "QAOA",
         "draper_qft_adder": "Draper adder", "graphstate": "Graph state", "bmw_quark_cardinality": "BMW cardinality",
         "bmw_quark_copula": "BMW copula"}
K_LABEL = {k: ("\\infty" if k == "inf" else k) for k in K_ORDER}     # used inside $K=...$
STRATEGIES = ["ODG", "CGP", "ACGP", "Dynamic"]
# headline comparisons: (tag, heading, explanation, [(strategy, K, label)])
HEADLINES = [
    ("8", "8 memories per core, 6 for pre-generation",
     "ODG, CGP, ACGP and Dynamic~(8) use 8 memories per core, of which 6 may hold pre-generated pairs; "
     "Dynamic~($\\infty$) uses 64, which no core ever fills.",
     [("ODG", "8", "ODG"), ("CGP", "8", "CGP"), ("ACGP", "8", "ACGP"), ("Dynamic", "8", "Dynamic (8)"),
      ("Dynamic", "inf", "Dynamic (inf)")]),
    ("4all", "4 memories per core, all 4 for pre-generation",
     "ODG, CGP, ACGP and Dynamic~(4) use 4 memories per core and every strategy may fill all 4 with pre-generated "
     "pairs (CGP and ACGP cache 4, not $\\lfloor0.75\\cdot4\\rfloor=3$ as in the $K$ sweep); Dynamic~($\\infty$) as above.",
     [("ODG", "4all", "ODG"), ("CGP", "4all", "CGP"), ("ACGP", "4all", "ACGP"), ("Dynamic", "4all", "Dynamic (4)"),
      ("Dynamic", "inf", "Dynamic (inf)")]),
]
# validated categorical palette (dataviz skill), fixed order; three hues are under 3:1 contrast, so every bar is hatched
# and every chart has a table
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
HATCHES = ["", "//", "\\\\", "xx", ".."]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
METRICS = [("latency_ms", "Latency", "mean latency per hop (ms)", 3),
           ("fidelity", "Fidelity", "mean delivered EPR fidelity", 4),
           ("hop_coverage_pct", "Coverage", "hops with a ready pair (%)", 1),
           ("wastage_pct", "Wastage", "pairs generated but not used (%)", 2),
           ("utilisation_pct", "Utilisation", "pairs used / pairs generated (%)", 1)]
plt.rcParams.update({"font.size": 8.5, "axes.edgecolor": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "hatch.linewidth": 0.6, "pdf.fonttype": 42})


def stats(frame, strategy, k, metric):
    values = frame[(frame.strategy == strategy) & (frame.K.astype(str) == k)][metric].dropna()
    if values.empty:
        return math.nan, math.nan, math.nan
    return values.mean(), values.min(), values.max()


def bar(ax, x, value, low, high, color, hatch, width):
    if math.isnan(value):
        ax.text(x, 0, "n/a", ha="center", va="bottom", fontsize=7, color=MUTED)
        return
    ax.bar(x, value, width, color=color, hatch=hatch, edgecolor=INK if hatch else "white", linewidth=0.4)
    if high > low:
        ax.errorbar(x, value, yerr=[[value - low], [high - value]], color=INK, elinewidth=0.8, capsize=1.5)


def headline_figure(frame, title, configs, path):
    fig, axes = plt.subplots(1, 5, figsize=(12, 3.0))
    for ax, (metric, name, ylabel, digits) in zip(axes, METRICS):
        for i, (strategy, k, label) in enumerate(configs):
            value, low, high = stats(frame, strategy, k, metric)
            bar(ax, i, value, low, high, COLORS[i], HATCHES[i], 0.7)
            if not math.isnan(value):
                ax.text(i, value, f"{value:.{digits}f}", ha="center", va="bottom", fontsize=6.3, color=INK)
        ax.set_xticks(range(len(configs)), [label for _, _, label in configs], rotation=35, ha="right", fontsize=7.5)
        ax.set_title(name, fontsize=9.5)
        ax.set_ylabel(ylabel, fontsize=7.5)
        ax.grid(axis="x", visible=False)
        ax.margins(y=0.15)
    fig.suptitle(title, x=0.01, ha="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def sweep_figure(frame, metric, name, ylabel, title, path):
    fig, ax = plt.subplots(figsize=(9, 3.0))
    width = 0.8 / len(STRATEGIES)
    for si, strategy in enumerate(STRATEGIES):
        for ki, k in enumerate(K_ORDER):
            value, low, high = stats(frame, strategy, k, metric)
            x = ki + (si - (len(STRATEGIES) - 1) / 2) * width
            if math.isnan(value):
                continue
            bar(ax, x, value, low, high, COLORS[si], HATCHES[si], width * 0.92)
    ax.set_xticks(range(len(K_ORDER)), [("inf (64)" if k == "inf" else k) for k in K_ORDER])
    ax.set_xlabel("memories per core K")
    ax.set_ylabel(ylabel)
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[Patch(facecolor=COLORS[i], hatch=HATCHES[i], edgecolor=INK, linewidth=0.4, label=s)
                       for i, s in enumerate(STRATEGIES)], ncol=4, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.22), fontsize=8)
    ax.set_title(f"{title}: {name}", loc="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def cell(value, digits):
    return "--" if math.isnan(value) else f"{value:.{digits}f}"


def section(frame, benchmark, route):
    tag = f"{benchmark}_{route}"
    title = f"{NAMES[benchmark]}, {'XY' if route == 'xy' else 'history'} routing"
    for metric, name, ylabel, _ in METRICS:
        sweep_figure(frame, metric, name, ylabel, title, DOC / "figures" / f"{tag}_k_{metric}.pdf")
    hops = int(frame.hops.iloc[0])
    lines = [f"\\section{{{title}}}",
             f"{hops} hops; seeds {', '.join(str(s) for s in sorted(frame.seed.unique()))}; every run completed every hop and "
             "passed the physical audit (Checks sheet of the workbook)."]
    for htag, heading, explanation, configs in HEADLINES:
        if any(math.isnan(stats(frame, strategy, k, "latency_ms")[0]) for strategy, k, _ in configs):
            continue                      # not run for this benchmark and route
        figure = f"{tag}_headline_{htag}.pdf"
        headline_figure(frame, f"{title}: {heading}", configs, DOC / "figures" / figure)
        lines += [f"\\subsection{{Headline: {heading}}}", explanation,
                  "\\begin{table}[H]\\centering\\small",
                  "\\begin{tabular}{lrrrrrrr}\\toprule",
                  "Configuration & Latency (ms) & p95 (ms) & Fidelity & Hop cov. (\\%) & Chain full (\\%) & Wastage (\\%) & Utilisation (\\%)\\\\\\midrule"]
        for strategy, k, label in configs:
            values = [stats(frame, strategy, k, m)[0] for m in ("latency_ms", "p95_ms", "fidelity", "hop_coverage_pct",
                                                                  "chain_full_pct", "wastage_pct", "utilisation_pct")]
            digits = [3, 2, 4, 1, 1, 2, 1]
            lines.append(label.replace("inf", "$\\infty$") + " & " + " & ".join(cell(v, d) for v, d in zip(values, digits)) + "\\\\")
        lines += ["\\bottomrule\\end{tabular}",
                  f"\\caption{{{title}, {heading}: mean of the seeds.}}\\end{{table}}",
                  "\\begin{figure}[H]\\centering",
                  f"\\includegraphics[width=\\linewidth]{{{figure}}}",
                  f"\\caption{{{title}, {heading}. Bars are the mean of the seeds, whiskers the seed range; "
                  "fidelity bars start at zero, so read the labels.}\\end{figure}"]
    lines += ["\\subsection{Memories per core K}",
              "Dynamic may use all K memories, except 6 of 8 at $K=8$; CGP and ACGP cache $\\lfloor 0.75K\\rfloor$ pairs "
              "(so at $K=1$ they are ODG). $K=\\infty$ is 64 memories."]
    for metric, name, ylabel, digits in METRICS:
        lines += ["\\begin{table}[H]\\centering\\small",
                  "\\begin{tabular}{l" + "r" * len(K_ORDER) + "}\\toprule",
                  f"{name} & " + " & ".join(f"$K={K_LABEL[k]}$" for k in K_ORDER) + "\\\\\\midrule"]
        for strategy in STRATEGIES:
            lines.append(strategy + " & " + " & ".join(cell(stats(frame, strategy, k, metric)[0], digits) for k in K_ORDER) + "\\\\")
        lines += ["\\bottomrule\\end{tabular}",
                  f"\\caption{{{title}: {name.lower()} ({ylabel.replace('%', chr(92) + '%')}) for every K.}}\\end{{table}}",
                  "\\begin{figure}[H]\\centering",
                  f"\\includegraphics[width=\\linewidth]{{{tag}_k_{metric}.pdf}}",
                  f"\\caption{{{title}: {name.lower()} for every K.}}\\end{{figure}}"]
    notes = DOC / "sections" / f"{tag}_findings.tex"
    if notes.exists():
        lines += ["\\subsection{Findings}", f"\\input{{sections/{tag}_findings.tex}}"]
    (DOC / "generated" / f"{tag}.tex").write_text("\n".join(lines) + "\n")
    return tag


def main() -> None:
    frame = pd.read_csv(DATA, dtype={"K": str})
    for folder in ("figures", "generated", "sections"):
        (DOC / folder).mkdir(parents=True, exist_ok=True)
    tags = [section(group, b, r) for (b, r), group in frame.groupby(["benchmark", "route"], sort=False)]
    (DOC / "generated" / "sections.tex").write_text("".join(f"\\input{{generated/{t}.tex}}\n\\clearpage\n" for t in tags))
    print("sections:", tags)


if __name__ == "__main__":
    main()
