"""Every figure of the report, drawn from the CSV files in data/.  Nothing is typed in by hand.

Style follows the project's chart rules: one measure per axis, thin marks, a direct label on every series
(two of the four colours are below 3:1 contrast on white, so colour never carries identity alone: each series
also has its own marker and line style), a light grid, and the same colour for the same quantity everywhere.
"""
from __future__ import annotations

import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd

from collect import DATA
from knobs import ROOT

FIG = ROOT / "docs" / "latex" / "generation_time_study" / "report" / "figures"
BLUE, ORANGE, AQUA, YELLOW, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#0b0b0b", "#52514e", "#e4e3de"
MARKERS = ("o", "s", "^", "D")
plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5, "axes.edgecolor": MUTED, "axes.linewidth": 0.7,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK, "axes.labelcolor": MUTED, "legend.frameon": False,
                     "legend.fontsize": 7.5, "figure.dpi": 150, "savefig.bbox": "tight", "font.family": "serif"})
CONTEXT = {("qft", 4): (BLUE, "o", "-"), ("qft", 3): (BLUE, "s", "--"), ("qaoa", 4): (ORANGE, "^", "-"), ("qaoa", 3): (ORANGE, "D", "--")}
NAME = {"qft": "QFT", "qaoa": "QAOA"}


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    plt.close(fig)


def label(ax, x, y, text, color, dx=0.0, dy=0.0, ha="left"):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", color=color, fontsize=7.5, ha=ha, va="center")


def spread_labels(ax, x, items, dx=4, gap_points=9):
    """Direct labels at data x, nudged apart vertically so that none overlap.  items: (y, text, colour)."""
    fig = ax.figure
    fig.canvas.draw()
    transform = ax.transData
    placed = sorted((transform.transform((x, y))[1], text, color) for y, text, color in items)
    ys = [p[0] for p in placed]
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + gap_points * fig.dpi / 72)
    x_display = transform.transform((x, 0))[0]
    for y, (_, text, color) in zip(ys, placed):
        data_x, data_y = transform.inverted().transform((x_display, y))
        ax.annotate(text, (data_x, data_y), xytext=(dx, 0), textcoords="offset points", color=color, fontsize=7.5, va="center", annotation_clip=False)


def paired(frame):
    keys = [k for k in ["workload", "route", "memories", "compiler_memories", "tag", "lead", "lookahead", "reservation_ms", "generation_capacity",
                        "memory_efficiency", "classical_scale", "empty_gap_ms", "coherence_time_s", "distance_scale", "bsm_success_rate",
                        "detector_efficiency", "request_retry_ms", "compiler_retry_ms"] if k in frame.columns]
    dyn = frame[frame.strategy == "dynamic"]
    odg = frame[frame.strategy == "on-demand"][keys + ["latency_ms", "makespan_s", "miss_generation_ms", "latency_ms_ci"]]
    odg = odg.rename(columns={c: c + "_odg" for c in ("latency_ms", "makespan_s", "miss_generation_ms", "latency_ms_ci")})
    out = dyn.merge(odg, on=keys)
    out["saving_ms"] = out.latency_ms_odg - out.latency_ms
    return out


def link_figure():
    t = pd.read_csv(DATA / "link_screen.csv")
    t = t[(t.samples > 0) & t.source.isin((0, 1))]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.5))
    panels = (("memory_efficiency", "Memory efficiency", False), ("classical_scale", "Classical delay (x 100 µs)", True), ("distance_scale", "Core-to-BSM distance scale (x 2.5 cm)", True))
    for ax, (knob, xlabel, logx) in zip(axes, panels):
        base = t[t.knob == "base"]
        for direction, (color, marker, style, name) in {0: (BLUE, "o", "-", "forward"), 1: (ORANGE, "s", "--", "reverse")}.items():
            g = t[(t.knob == knob) & (t.source == direction)].sort_values("value")
            xs = np.append(g.value.to_numpy(), {"memory_efficiency": 0.95, "classical_scale": 1.0, "distance_scale": 1.0}[knob])
            ys = np.append(g.generation_mean_ms.to_numpy(), base[base.source == direction].generation_mean_ms.mean())
            pred = np.append(g.predicted_generation_ms.to_numpy(), base[base.source == direction].predicted_generation_ms.mean())
            ci = np.append(g.generation_ci_ms.to_numpy(), base[base.source == direction].generation_ci_ms.mean())
            order = np.argsort(xs)
            ax.plot(xs[order], pred[order], color=color, lw=1.0, ls=style, alpha=0.55)
            ax.errorbar(xs[order], ys[order], yerr=ci[order], color=color, marker=marker, ms=4, lw=0, elinewidth=0.8, capsize=1.5, label=name)
        ax.set_xlabel(xlabel)
        ax.set_yscale("log")
        if logx:
            ax.set_xscale("log")
        if knob == "memory_efficiency":
            ax.invert_xaxis()
            ax.set_ylabel("Mean generation time (ms)")
            ax.legend(loc="upper left")
        ax.set_title({"memory_efficiency": "(a) efficiency", "classical_scale": "(b) classical delay", "distance_scale": "(c) distance"}[knob], loc="left")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    fig.tight_layout()
    save(fig, "link_generation")


def attempts_figure():
    hist = json.loads((DATA / "link_attempt_histograms.json").read_text())
    probe = pd.read_csv(DATA / "link_screen.csv")
    base = probe[(probe.knob == "base") & (probe.source == 0) & (probe.destination == 1)].iloc[0]
    p = base.predicted_p
    counts = {int(k): v for k, v in hist["0->1"].items()}
    total = sum(counts.values())
    ks = np.arange(1, 13)
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    ax.bar(ks - 0.2, [counts.get(k, 0) / total for k in ks], width=0.4, color=BLUE, label="measured")
    ax.bar(ks + 0.2, [(1 - p) ** (k - 1) * p for k in ks], width=0.4, color="#b9b8b1", label=f"geometric, p = {p:.3f}")
    ax.set_xlabel("Attempts until success")
    ax.set_ylabel("Share of pairs")
    ax.legend()
    save(fig, "attempts")


def sweep_figure(experiment, column, xlabel, name, invert=False, logx=False, xs_filter=None):
    frame = pd.read_csv(DATA / f"{experiment}_summary.csv")
    frame = paired(frame[frame.route == "history"])
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.5))
    ends = []
    for (workload, memories), g in frame.groupby(["workload", "memories"]):
        g = g.sort_values(column)
        color, marker, style = CONTEXT[(workload, memories)]
        for ax, y in zip(axes, (g.gain_latency_ms, g.saving_ms, g.gain_communication_s)):
            ax.plot(g.miss_generation_ms_odg, y, color=color, marker=marker, ms=3.5, lw=1.3, ls=style)
        ends.append((g.miss_generation_ms_odg.max(), g.gain_latency_ms.iloc[g.miss_generation_ms_odg.argmax()], f"{NAME[workload]} M{memories}", color))
    for ax in axes:
        ax.set_xlim(0.85, 22)
    spread_labels(axes[0], ends[0][0], [(e[1], e[2], e[3]) for e in ends])
    for ax, title, ylabel in zip(axes, ("(a) latency gain", "(b) latency saved per hop", "(c) communication-time gain"),
                                 ("Dynamic vs ODG (%)", "ms per hop", "Dynamic vs ODG (%)")):
        ax.set_xscale("log")
        ax.set_xlabel("ODG generation time on a miss (ms)")
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left")
    axes[0].axhline(0, color=MUTED, lw=0.6)
    fig.tight_layout()
    save(fig, name)


def gap_figure():
    frame = paired(pd.read_csv(DATA / "gap_summary.csv"))
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.6), sharex=True)
    colors = {0.95: (BLUE, "o"), 0.6: (AQUA, "^"), 0.4: (ORANGE, "s")}
    for column, workload in enumerate(("qft", "qaoa")):
        for row, metric in enumerate(("gain_latency_ms", "hit_rate")):
            ax = axes[row, column]
            g_all = frame[(frame.workload == workload) & (frame.memories == 4)]
            ends = []
            for eff, (color, marker) in colors.items():
                g = g_all[g_all.memory_efficiency == eff].sort_values("empty_gap_ms")
                y = g[metric] * (100 if metric == "hit_rate" else 1)
                ax.plot(g.empty_gap_ms.replace(0, 0.05), y, color=color, marker=marker, ms=3.5, lw=1.3)
                ends.append((y.iloc[-1], f"eff {eff}", color))
            ax.set_xscale("log")
            ax.set_xlim(0.035, 60)
            spread_labels(ax, 20, ends)
            if metric == "gain_latency_ms":
                ax.axhline(0, color=MUTED, lw=0.6)
                ax.set_title(f"{NAME[workload]} (M=4, C=3): latency gain", loc="left")
                ax.set_ylabel("Dynamic vs ODG (%)")
            else:
                ax.set_title("hit rate", loc="left")
                ax.set_ylabel("Requests with a ready pair (%)")
                ax.set_xlabel("Empty-layer gap (ms); 0 plotted at 0.05")
    fig.tight_layout()
    save(fig, "gap")


def breakeven_figure():
    t = pd.read_csv(DATA / "model_breakeven.csv")
    t = t[(t.break_even > -0.2) & (t.break_even < 1.2)]
    fig, ax = plt.subplots(figsize=(3.5, 3.1))
    ax.plot([0, 1], [0, 1], color=MUTED, lw=0.8)
    for wins, color, marker, name in ((True, BLUE, "o", "Dynamic wins"), (False, ORANGE, "x", "Dynamic loses")):
        g = t[t.wins == wins]
        ax.scatter(g.break_even, g.hit_rate, s=14, color=color, marker=marker, lw=1.0 if marker == "x" else 0, alpha=0.8, label=name)
    ax.set_xlabel("Break-even hit rate $h^*$")
    ax.set_ylabel("Measured hit rate $h$")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.legend(loc="upper right")
    ax.text(0.30, 0.36, "$h = h^*$", color=MUTED, fontsize=7.5, rotation=40)
    save(fig, "breakeven")


def readiness_figure():
    t = pd.read_csv(DATA / "model_readiness_trials.csv.gz")
    t = t[(t.gap >= 5) & (t.coherence >= 1.0) & (t.lead == 2)]
    fig, ax = plt.subplots(figsize=(3.5, 3.1))
    ax.plot([0, 1], [0, 1], color=MUTED, lw=0.8)
    for workload, color, marker in (("qft", BLUE, "o"), ("qaoa", ORANGE, "^")):
        g = t[t.workload == workload]
        ax.scatter(g.predicted, g.measured, s=10, color=color, marker=marker, alpha=0.55, label=NAME[workload], lw=0)
    ax.set_xlabel("Predicted share ready in time")
    ax.set_ylabel("Measured share ready in time")
    ax.set_xlim(0.4, 1.01)
    ax.set_ylim(0.4, 1.01)
    ax.legend(loc="upper left")
    save(fig, "readiness")


ROUTE_STYLE = {"history": (BLUE, "o", "-"), "xy": (ORANGE, "s", "--"), "minhop": (AQUA, "^", "-."), "greedy": (YELLOW, "D", ":")}


def lead_figure():
    lead = pd.read_csv(DATA / "lead_gap_summary.csv")
    lead = lead[lead.strategy == "dynamic"]
    eff = pd.read_csv(DATA / "efficiency_summary.csv")
    odg = eff[(eff.strategy == "on-demand") & (eff.route == "history") & (eff.memories == 4)]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.6), sharex=True)
    for row, workload in enumerate(("qft", "qaoa")):
        for column, efficiency in enumerate((0.95, 0.4)):
            ax = axes[row, column]
            reference = float(odg[(odg.workload == workload) & np.isclose(odg.memory_efficiency, efficiency)].latency_ms.iloc[0])
            for gap, color, marker, name in ((5.0, BLUE, "o", "gap 5 ms"), (0.0, ORANGE, "s", "gap 0")):
                g = lead[(lead.workload == workload) & (lead.memories == 4) & np.isclose(lead.memory_efficiency, efficiency) & (lead.empty_gap_ms == gap)].sort_values("lead")
                ax.errorbar(g.lead, g.latency_ms, yerr=g.latency_ms_ci, color=color, marker=marker, ms=3.5, lw=1.3, capsize=1.5, elinewidth=0.7, label=name)
                best = g.loc[g.latency_ms.idxmin()]
                ax.scatter([best.lead], [best.latency_ms], s=60, facecolors="none", edgecolors=color, lw=1.2, zorder=5)
            ax.axhline(reference, color=MUTED, lw=0.8, ls=":")
            ax.text(8.15, reference, "ODG", color=MUTED, fontsize=7.5, va="center")
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
            ax.yaxis.set_minor_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}" if v in (2, 3, 4, 5, 6, 7, 8, 9, 0.5, 0.6, 0.7, 0.8, 0.9, 1.5, 2.5) else ""))
            ax.tick_params(axis="y", which="minor", labelsize=6.5)
            ax.set_title(f"{NAME[workload]}, efficiency {efficiency}", loc="left")
            if column == 0:
                ax.set_ylabel("Dynamic latency (ms)")
            if row == 1:
                ax.set_xlabel("Planner lead (layers)")
            ax.set_xlim(0.7, 8.9)
    axes[0, 0].legend(loc="upper left")
    fig.tight_layout()
    save(fig, "lead")


def tuning_figure():
    t = pd.read_csv(DATA / "tuning_summary.csv")
    t = t[t.strategy == "dynamic"]
    contexts = [(w, m, e) for w in ("qft", "qaoa") for m in (3, 4) for e in (0.95, 0.4)]
    default = {c: float(t[(t.workload == c[0]) & (t.memories == c[1]) & np.isclose(t.memory_efficiency, c[2]) & (t.tag == "default")].latency_ms.iloc[0]) for c in contexts}
    tags = [x for x in t.tag.unique() if x != "default"]
    def change(c, tag):
        row = t[(t.workload == c[0]) & (t.memories == c[1]) & np.isclose(t.memory_efficiency, c[2]) & (t.tag == tag)]
        return 100 * (float(row.latency_ms.iloc[0]) / default[c] - 1) if len(row) else np.nan
    matrix = pd.DataFrame({f"{NAME[c[0]]} M{c[1]}\n eff {c[2]}": {tag: change(c, tag) for tag in tags} for c in contexts})
    order = matrix.mean(axis=1, skipna=True).sort_values().index
    matrix = matrix.loc[order]
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("div", [BLUE, "#f1f0ec", ORANGE])
    fig, ax = plt.subplots(figsize=(6.6, 7.4))
    ax.grid(False)
    cmap.set_bad("#ffffff")
    image = ax.imshow(np.ma.masked_invalid(np.clip(matrix.to_numpy(), -40, 40)), cmap=cmap, vmin=-40, vmax=40, aspect="auto")
    ax.set_xticks(range(matrix.shape[1]), matrix.columns, fontsize=7)
    ax.set_yticks(range(matrix.shape[0]), matrix.index, fontsize=7.5)
    ax.xaxis.tick_top()
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix.iloc[i, j]
            ax.text(j, i, "n/a" if np.isnan(v) else "0" if abs(v) < 0.05 else f"{v:+.0f}", ha="center", va="center", fontsize=6.8, color=MUTED if np.isnan(v) else INK)
    cb = fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("Dynamic latency vs default (%); clipped at \u00b140, numbers exact", fontsize=7)
    for spine in ax.spines.values():
        spine.set_visible(False)
    save(fig, "tuning")


def validation_figure():
    v = pd.read_csv(DATA / "validation_check.csv")
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    y = np.arange(len(v))[::-1]
    ax.scatter(v.tuning_change_percent, y, color=MUTED, marker="o", s=22, label="tuning seeds 60-63", zorder=3)
    ax.errorbar(v.validation_change_percent, y, xerr=v.validation_interval, fmt="s", color=BLUE, ms=4.5, capsize=2, lw=1, label="unseen seeds 100-105", zorder=4)
    ax.set_yticks(y, [f"{NAME[r.workload]} M{r.memories} eff {r.memory_efficiency}: {r.option}" for r in v.itertuples()], fontsize=7.5)
    ax.axvline(0, color=MUTED, lw=0.7)
    ax.set_xlabel("Change in Dynamic latency vs default (%)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    save(fig, "validation")


def routes_figure():
    r = paired(pd.read_csv(DATA / "routes_summary.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.6), sharey=False)
    for ax, workload in zip(axes, ("qft", "qaoa")):
        ends = []
        for route, (color, marker, style) in ROUTE_STYLE.items():
            g = r[(r.workload == workload) & (r.route == route)].sort_values("memory_efficiency", ascending=False)
            ax.errorbar(g.memory_efficiency, g.gain_latency_ms, yerr=g.gain_latency_ms_ci, color=color, marker=marker, ms=4, lw=1.2, ls=style, capsize=1.5, elinewidth=0.6)
            ends.append((g.gain_latency_ms.iloc[-1], route, color))
        ax.set_xlim(1.0, 0.3)
        spread_labels(ax, 0.4, ends, dx=3, gap_points=8)
        ax.set_title(f"{NAME[workload]} (M=4, C=3)", loc="left")
        ax.set_xlabel("Memory efficiency")
        ax.set_ylabel("Latency gain (%)")
    fig.tight_layout()
    save(fig, "routes")


def memory_figure():
    m = paired(pd.read_csv(DATA / "memory_summary.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.6), sharey=True)
    for ax, efficiency in zip(axes, (0.95, 0.4)):
        for workload, color, marker in (("qft", BLUE, "o"), ("qaoa", ORANGE, "^")):
            g = m[(m.workload == workload) & np.isclose(m.memory_efficiency, efficiency)].sort_values("memories")
            ax.errorbar(g.memories, g.gain_latency_ms, yerr=g.gain_latency_ms_ci, color=color, marker=marker, ms=4, lw=1.2, capsize=1.5, elinewidth=0.6)
            label(ax, g.memories.iloc[-1], g.gain_latency_ms.iloc[-1], NAME[workload], color, dx=4)
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_xlim(1.7, 9.4)
        ax.set_title(f"efficiency {efficiency}", loc="left")
        ax.set_xlabel("Memories per core M (C = M - 1)")
    axes[0].set_ylabel("Latency gain (%)")
    fig.tight_layout()
    save(fig, "memory")


def coherence_figure():
    c = paired(pd.read_csv(DATA / "coherence_summary.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.6))
    for efficiency, style, name in ((0.95, "-", "eff 0.95"), (0.4, "--", "eff 0.4")):
        for workload, color, marker in (("qft", BLUE, "o"), ("qaoa", ORANGE, "^")):
            g = c[(c.workload == workload) & np.isclose(c.memory_efficiency, efficiency)].sort_values("coherence_time_s")
            axes[0].plot(g.coherence_time_s, g.gain_latency_ms, color=color, marker=marker, ms=3.5, lw=1.2, ls=style)
            axes[1].plot(g.coherence_time_s, g.fidelity, color=color, marker=marker, ms=3.5, lw=1.2, ls=style)
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlabel("Memory coherence time (s)")
        ax.invert_xaxis()
    axes[0].axhline(0, color=MUTED, lw=0.6)
    axes[0].set_ylabel("Latency gain (%)")
    axes[1].set_ylabel("Delivered fidelity (Dynamic)")
    axes[0].text(0.03, 0.04, "solid: eff 0.95, dashed: eff 0.4\nblue QFT, orange QAOA", transform=axes[0].transAxes, fontsize=7, color=MUTED, va="bottom", ha="left")
    fig.tight_layout()
    save(fig, "coherence")


def chip_figure():
    chip = paired(pd.read_csv(DATA / "chip_summary.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.6), sharey=True)
    for ax, workload in zip(axes, ("qft", "qaoa")):
        ends = []
        for scale, color, marker in ((0.01, ORANGE, "s"), (0.1, AQUA, "^")):
            g = chip[(chip.workload == workload) & (chip.classical_scale == scale)].sort_values("empty_gap_ms")
            ax.plot(g.empty_gap_ms.replace(0, 0.03), g.gain_latency_ms, color=color, marker=marker, ms=4, lw=1.2)
            ends.append((g.gain_latency_ms.iloc[-1], f"delay x{scale:g}", color))
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_xscale("log")
        ax.set_xlim(0.02, 40)
        spread_labels(ax, 5, ends, dx=4)
        ax.set_title(f"{NAME[workload]} (M=4, C=3, eff 0.95)", loc="left")
        ax.set_xlabel("Empty-layer gap (ms); 0 plotted at 0.03")
    axes[0].set_ylabel("Latency gain (%)")
    fig.tight_layout()
    save(fig, "chip")


def retry_figure():
    r = paired(pd.read_csv(DATA / "retry_summary.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.6), sharey=True)
    names = {"retry request=1 compiler=1": "default", "retry request=0.01 compiler=1": "request retry scaled", "retry request=1 compiler=0.01": "compiler retry scaled", "retry request=0.01 compiler=0.01": "both scaled"}
    for ax, workload in zip(axes, ("qft", "qaoa")):
        for k, (scale, color) in enumerate(((0.01, ORANGE), (0.1, AQUA))):
            g = r[(r.workload == workload) & (r.classical_scale == scale)]
            tags = [t.replace(f"{scale:g}", "0.01") for t in g.tag]
            order = ["retry request=1 compiler=1", "retry request=0.01 compiler=1", "retry request=1 compiler=0.01", "retry request=0.01 compiler=0.01"]
            values = []
            for tag in order:
                row = g[[(t.replace(f"{scale:g}", "0.01") == tag) for t in g.tag]]
                values.append(float(row.gain_latency_ms.iloc[0]) if len(row) else np.nan)
            ax.bar(np.arange(4) + (k - 0.5) * 0.38, values, width=0.36, color=color, label=f"delay x{scale:g}")
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_xticks(range(4), ["default", "request\nscaled", "compiler\nscaled", "both\nscaled"], fontsize=7.5)
        ax.set_title(f"{NAME[workload]}", loc="left")
    axes[0].set_ylabel("Latency gain (%)")
    axes[1].legend(loc="lower right")
    fig.tight_layout()
    save(fig, "retry")


def workloads_figure():
    rows = []
    eff = paired(pd.read_csv(DATA / "efficiency_summary.csv"))
    eff = eff[(eff.memories == 4) & eff.memory_efficiency.isin((0.95, 0.4))]
    rows += [dict(workload=r.workload, route=r.route, efficiency=r.memory_efficiency, gain=r.gain_latency_ms, ci=r.gain_latency_ms_ci) for r in eff.itertuples()]
    other = paired(pd.read_csv(DATA / "workloads_summary.csv"))
    rows += [dict(workload=r.workload, route=r.route, efficiency=r.memory_efficiency, gain=r.gain_latency_ms, ci=r.gain_latency_ms_ci) for r in other.itertuples()]
    t = pd.DataFrame(rows)
    names = {"qft": "QFT-96", "qaoa": "QAOA-96", "draper_qft_adder": "Draper-96", "cdkm_ripple_carry_adder": "CDKM-48", "randomcircuit": "random-48"}
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.6), sharey=True)
    for ax, efficiency in zip(axes, (0.95, 0.4)):
        for k, (route, color) in enumerate((("xy", ORANGE), ("history", BLUE))):
            g = t[(t.route == route) & np.isclose(t.efficiency, efficiency)].set_index("workload").reindex(list(names))
            ax.bar(np.arange(len(names)) + (k - 0.5) * 0.38, g.gain, yerr=g.ci, width=0.36, color=color, label=route, capsize=1.5, error_kw=dict(lw=0.7))
        ax.set_xticks(range(len(names)), [names[n] for n in names], rotation=30, ha="right", fontsize=7.5)
        ax.set_title(f"efficiency {efficiency}", loc="left")
    axes[0].set_ylabel("Latency gain (%)")
    axes[0].legend(loc="upper right")
    fig.tight_layout()
    save(fig, "workloads")


def timeline_figure():
    events = pd.read_csv(DATA / "anatomy.csv")
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 3.6))
    colors = {"pairing": MUTED, "negotiate": BLUE, "emit": AQUA, "herald": ORANGE, "inform": ORANGE, "window": INK, "done": INK}
    cases = (("on-demand 0->1", "(a) ODG miss: one failed attempt, then success"), ("dynamic 0->1", "(b) Dynamic hit: the pair already exists"))
    for ax, (case, title) in zip(axes, cases):
        g = events[events.case == case].copy()
        g["ms"] = g.t_us / 1000
        if "dynamic" in case:
            g = g[g.ms > -0.5]
        g = g[g.node.str.startswith("router") | g.node.eq("manager")]
        window = float(g[g.event == "reservation window opens"].ms.iloc[0])
        done = float(g[g.event == "request completed"].ms.iloc[0])
        ax.axvspan(0, window, color="#b9b8b1", alpha=0.5, lw=0)
        ax.text(window / 2, 1.5, "guard", ha="center", fontsize=7.5, color=INK)
        ax.axvline(done, color=INK, lw=1.0)
        ax.text(done - 0.01, -0.45, f"done at {done:.1f} ms", fontsize=7.5, va="center", ha="right")
        for lane, node in ((0, "router_0_0"), (1, "router_0_1")):
            h = g[g.node == node]
            for r in h.itertuples():
                kind = ("herald" if "herald" in r.event else "emit" if "emits" in r.event else "negotiate" if "NEGOTIATE" in r.event else "inform" if "INFORM" in r.event else "pairing" if "pairing" in r.event or "reservation" in r.event else None)
                if kind:
                    ax.scatter([r.ms], [lane], s=22, color=colors[kind], marker={"herald": "*", "emit": "^", "negotiate": "s", "inform": "D", "pairing": "o"}[kind], zorder=4,
                               label=kind if kind not in ax.get_legend_handles_labels()[1] else None)
        ax.set_yticks([0, 1], ["router_0_0", "router_0_1"], fontsize=7.5)
        ax.set_ylim(-0.6, 1.9)
        ax.set_title(title, loc="left")
        ax.set_xlim(-0.03, max(done, window) * 1.12)
        ax.legend(loc="upper right", ncol=5, fontsize=7, handletextpad=0.2, columnspacing=0.8)
    axes[1].set_xlabel("Time since the request was submitted (ms)")
    fig.tight_layout()
    save(fig, "timeline")


def main(which):
    FIG.mkdir(parents=True, exist_ok=True)
    actions = dict(
        link=link_figure, attempts=attempts_figure, gap=gap_figure, breakeven=breakeven_figure, readiness=readiness_figure,
        efficiency=lambda: sweep_figure("efficiency", "memory_efficiency", "", "efficiency_sweep"),
        delay=lambda: sweep_figure("delay", "classical_scale", "", "delay_sweep"),
        lead=lead_figure, tuning=tuning_figure, validation=validation_figure, routes=routes_figure, memory=memory_figure,
        coherence=coherence_figure, chip=chip_figure, retry=retry_figure, workloads=workloads_figure, timeline=timeline_figure)
    for name in (which or actions):
        actions[name]()
        print("drew", name)


if __name__ == "__main__":
    main(sys.argv[1:])
