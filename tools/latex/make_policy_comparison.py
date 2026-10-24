#!/usr/bin/env python3
"""Tables and figure wrappers for the two new chapters: why dynamic pre-generation can be slower than on-demand
(chapter 12) and the four-policy comparison ODG / Dynamic / CGP / ACGP (chapter 13).

Reads results/diagnostics_dynamic_vs_odg_2026-10-24/diagnostics.csv, results/ace_budget_rerun_2026-10-24/results_*.csv and
results/experiment1_four_policies_{mesh,torus}_2026-10-24/*.  Every number in the chapters' tables comes from these files.

    python tools/latex/make_policy_comparison.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "latex"))
import make_tables as MT                                                      # noqa: E402

RES = REPO / "results"
DIAG = RES / "diagnostics_dynamic_vs_odg_2026-10-24"
BUDGET = RES / "ace_budget_rerun_2026-10-24"
GEN, FIG, NAMES = MT.GEN, MT.FIG, MT.NAMES
ORDER = ["ODG", "Dynamic", "CGP", "ACGP"]
BUDGETS = [1, 2, 3, 4, 6, 8, 16, 32]


def f(x, d=2, pct=False):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "--"
    return f"{x:.{d}f}" + (r"\%" if pct else "")


def landscape(name: str, png: Path, caption: str, label: str) -> None:
    if png.resolve() != (FIG / png.name).resolve():
        shutil.copy(png, FIG / png.name)
    (GEN / name).write_text("\n".join([
        r"\begin{landscape}", r"\begin{figure}[p]", r"\centering",
        rf"\includegraphics[width=\linewidth,height=0.80\textheight,keepaspectratio]{{{png.name}}}",
        rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{figure}", r"\end{landscape}"]) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------- legacy vs corrected
def legacy_tables(skipped: list) -> None:
    try:
        old, new = (pd.read_csv(BUDGET / f"results_{n}.csv") for n in ("legacy", "per_qubit"))
    except FileNotFoundError:
        skipped.append("legacy comparison")
        return
    def cell(frame, w, b, s, col):
        d = frame[(frame.workload == w) & (frame.total_memories == b) & (frame.strategy == s)]
        return pd.to_numeric(d[col], errors="coerce").mean()
    rows = []
    for w in ("qft", "qaoa", "draper_qft_adder", "graphstate", "ghz"):
        for b in (2, 3, 4, 32):
            vals = []
            for frame, col in ((old, "average_request_latency_ms"), (old, "average_eligible_latency_ms"), (new, "average_eligible_latency_ms")):
                o, d = cell(frame, w, b, "on-demand", col), cell(frame, w, b, "dynamic", col)
                vals += [f(o), f(d), f(100 * (o - d) / o, 0, pct=True)]
            rows.append([NAMES[w], str(b)] + vals)
    head = ["Workload", "Mem."] + [f"{p} {q}" for p in ("Old own", "Old common", "New common") for q in ("ODG", "Dyn.", "gain")]
    MT.table(GEN / "legacy_vs_corrected.tex", head, rows,
             "Request latency (ms) of on-demand (ODG) and dynamic (Dyn.) and the dynamic gain $(\\text{ODG}-\\text{Dyn.})/\\text{ODG}$. "
             "Old own: the old serialized scheduler's own latency, whose clock for a request starts when its batch is submitted. "
             "Old common: the same old runs under the common definition, which also counts the wait for earlier batches. "
             "New common: the corrected per-qubit scheduler under the common definition. Mean of nine runs "
             "(three mapping seeds, three physics seeds).", "tab:legacy-vs-corrected", colspec="llrrrrrrrrr")
    # makespan
    mk = []
    for w in ("qft", "qaoa", "draper_qft_adder", "graphstate", "ghz"):
        b = 4
        vals = [f(cell(frame, w, b, s, "end_to_end_latency_ms") / 1000, 2) for frame in (old, new) for s in ("on-demand", "dynamic")]
        mk.append([NAMES[w]] + vals)
    MT.table(GEN / "legacy_makespan.tex", ["Workload", "Old ODG", "Old Dyn.", "New ODG", "New Dyn."], mk,
             "End-to-end time of the whole trace (s) at four memories per core, old serialized scheduler and corrected scheduler "
             "(mean of nine runs).", "tab:legacy-makespan")


# ----------------------------------------------------------------------------------------------- diagnostics
def diagnostics_tables(skipped: list) -> None:
    path = DIAG / "diagnostics.csv"
    if not path.exists():
        skipped.append("diagnostics")
        return
    d = pd.read_csv(path)
    q = d[(d.workload == "qft") & (d.mapping_seed == 42) & (d.group == "mechanism")]
    rows = []
    for m in (2, 3, 4, 6, 8, 16):
        r = [str(m)]
        for p in ORDER:
            x = q[(q.memories == m) & (q.policy == p)]
            r += [f(x.latency_ms.iloc[0]), f(x.wait_before_admission_ms.iloc[0] + x.wait_after_rejection_ms.iloc[0])] if len(x) else ["--", "--"]
        rows.append(r)
    MT.table(GEN / "diag_latency_wait.tex", ["Mem."] + [f"{p} {c}" for p in ORDER for c in ("lat.", "wait")], rows,
             "QFT, mapping seed 42, mean of three physics seeds: request latency and the part of it spent waiting for a free memory "
             "(ms). The remainder of the latency is generation.", "tab:diag-latency-wait", colspec="r" + "rr" * 4)
    rows = []
    for m in (2, 3, 4, 6, 8, 16):
        r = [str(m)]
        for p in ORDER:
            x = q[(q.memories == m) & (q.policy == p)]
            r += [f(100 * x.checks_blocked_share.iloc[0], 1, pct=True)] if len(x) else ["--"]
        for p in ("Dynamic", "CGP", "ACGP"):
            x = q[(q.memories == m) & (q.policy == p)]
            share = {"Dynamic": "blocked_by_compiler_share"}.get(p, "blocked_by_autonomous_share")
            r += [f(100 * x[share].iloc[0], 0, pct=True)] if len(x) else ["--"]
        rows.append(r)
    MT.table(GEN / "diag_blocking.tex", ["Mem."] + [f"{p}" for p in ORDER] + ["Dyn. by compiler", "CGP by cache", "ACGP by cache"], rows,
             "QFT, mapping seed 42. Left: share of admission checks that found no free memory at one of the request's two cores. "
             "Right: of the memory cards found taken at a stuck core, the share held by the policy's own pre-generation bookings "
             "(the rest are held by other requests).", "tab:diag-blocking", colspec="r" + "r" * 7)
    x = q[q.policy == "Dynamic"].sort_values("memories")
    rows = [[str(int(r.memories)), f(100 * r.hit_rate, 1, pct=True), f(r.hit_wait_ms), f(100 * r.hit_share_that_waited, 0, pct=True),
             f(r.fallback_wait_ms), f(r.pair_ready_hold_ms, 1), f(r.application_hold_ms, 1)] for r in x.itertuples()]
    MT.table(GEN / "diag_hits.tex", ["Mem.", "Hits", "Hit wait", "Hits that waited", "Other wait", "Pair held", "Request holds"], rows,
             "Dynamic, QFT, mapping seed 42 (mean of three physics seeds). Hits: share of requests served by a ready pair, i.e. a prepared pair "
             "generated by the time it was used. Hit wait and Other wait: mean wait for a free memory (ms) of the hits and of the other requests. "
             "Pair held: time (ms) a ready pair waits in memory before it is used. Request holds: time (ms) an ordinary request keeps its memory card booked.", "tab:diag-hits")
    c = d[(d.workload == "qft") & (d.policy == "Dynamic") & (d.memories == 4) & (d.name == "qft_m4_dynamic")]
    if len(c) and c.hop0_hold_ms.notna().all():
        r = c.iloc[0]
        total = r.hop0_pairs + r.hop1_pairs + r.hop2plus_pairs
        rows = [["first hop", f(r.hop0_pairs, 0), f(r.hop0_made_before_layer_ms, 1), f(r.hop0_hold_ms, 1), f(r.hop0_request_wait_after_ready_ms, 1)],
                ["second hop", f(r.hop1_pairs, 0), f(r.hop1_made_before_layer_ms, 1), f(r.hop1_hold_ms, 1), f(r.hop1_request_wait_after_ready_ms, 1)],
                ["third hop or later", f(r.hop2plus_pairs, 0), f(r.hop2plus_made_before_layer_ms, 1), f(r.hop2plus_hold_ms, 1), f(r.hop2plus_request_wait_after_ready_ms, 1)]]
        MT.table(GEN / "diag_chain.tex", ["Position in the chain", "Pairs used", "Made before its layer started (ms)", "Ready pair held (ms)", "Request eligible after pair ready (ms)"], rows,
                 "Dynamic, QFT, four memories, mapping seed 42 (mean of three physics seeds): the pair of a later hop is made as early as the pair of a first hop, "
                 "but its request becomes eligible much later, so the pair waits longer.",
                 "tab:diag-chain")
    a = d[(d.group == "ablation") | ((d.group == "mechanism") & (d.workload == "qft") & (d.memories == 4) & d.policy.isin(["Dynamic", "ODG"]))]
    a = a[(a.mapping_seed == 42) & (a.workload == "qft") & (a.memories == 4)]
    rows = []
    for r in a.sort_values(["policy", "name"]).itertuples():
        change = r.change if isinstance(r.change, str) and r.change else ("baseline" if r.compiler_cap in (0, 3) else f"cap {r.compiler_cap}")
        if r.name.endswith("cap1") or r.name.endswith("cap2"):
            change = f"compiler memories {int(r.compiler_cap)} of 4"
        change = change.replace("--only-chain-hops-below;", "pairs only for the first ").replace("--only-chain-hops-below=", "")
        rows.append([r.policy, MT.tex(change), f(r.latency_ms), f(r.wait_before_admission_ms + r.wait_after_rejection_ms), f(100 * r.hit_rate, 0, pct=True) if pd.notna(r.hit_rate) else "--", f(r.fidelity, 4)])
    MT.table(GEN / "diag_ablation.tex", ["Policy", "Change from the baseline", "Latency (ms)", "Wait (ms)", "Ready-pair hits", "Fidelity"], rows,
             "QFT, four memories, mapping seed 42, mean of three physics seeds. Each row changes one setting. These are experiments to find "
             "the cause, not proposed settings.", "tab:diag-ablation", colspec="llrrrr")
    s = d[(d.workload == "qft") & (d.memories == 4) & d.group.isin(["mechanism", "seeds"])]
    rows = []
    for p in ORDER:
        r = [p]
        for ms in (42, 43, 44):
            x = s[(s.policy == p) & (s.mapping_seed == ms)]
            r += [f(x.latency_ms.iloc[0]), f(x.wait_before_admission_ms.iloc[0] + x.wait_after_rejection_ms.iloc[0])] if len(x) else ["--", "--"]
        rows.append(r)
    MT.table(GEN / "diag_seeds.tex", ["Policy"] + [f"map {m} {c}" for m in (42, 43, 44) for c in ("lat.", "wait")], rows,
             "QFT, four memories: the diagnosis on the three mapping seeds (mean of three physics seeds each; latency and wait in ms).",
             "tab:diag-seeds", colspec="lrrrrrr")
    w = d[(d.memories == 4) & (d.mapping_seed == 42) & (d.group.isin(["workloads", "mechanism"])) & (d.workload != "")]
    w = w[w.group.eq("workloads") | ((w.workload == "qft") & (w.group == "mechanism"))]
    rows = []
    for wl in ("cdkm_ripple_carry_adder", "vqe_real_amp", "randomcircuit", "draper_qft_adder", "graphstate", "qaoa", "qft"):
        r = [NAMES[wl]]
        for p in ORDER:
            x = w[(w.workload == wl) & (w.policy == p)]
            r.append(f(x.latency_ms.iloc[0]) if len(x) else "--")
        x = w[(w.workload == wl) & (w.policy == "Dynamic")]
        r.append(f(100 * x.hit_rate.iloc[0], 0, pct=True) if len(x) else "--")
        for p in ("Dynamic", "ODG"):
            x = w[(w.workload == wl) & (w.policy == p)]
            r.append(f(100 * x.checks_blocked_share.iloc[0], 1, pct=True) if len(x) else "--")
        rows.append(r)
    MT.table(GEN / "diag_workloads.tex", ["Workload"] + [f"{p} (ms)" for p in ORDER] + ["Dynamic hits", "Dyn. stuck checks", "ODG stuck checks"], rows,
             "Request latency at four memories on the other benchmarks (mapping seed 42, mean of three physics seeds), the share of requests "
             "dynamic served from a ready pair, and the share of admission checks that found no free memory under dynamic and under on-demand. "
             "Dynamic is faster than on-demand where its own prepared pairs rarely get in the way.", "tab:diag-workloads")


# ----------------------------------------------------------------------------------------------- four policies
def four_policy_tables(skipped: list) -> None:
    for topo, label in (("mesh", "mesh"), ("torus", "torus")):
        folder = RES / f"experiment1_four_policies_{topo}_2026-10-24"
        path = folder / "four_policy_cell_means.csv"
        if not path.exists():
            skipped.append(f"four policies {topo}")
            continue
        t = pd.read_csv(path)
        def pivot(metric, b):
            return t[t.total_memories == b].pivot(index="workload", columns="policy", values=metric)
        for metric, title, digits, key in (("latency_ms", "Request latency (ms)", 2, "lat"), ("fidelity", "Delivered EPR fidelity", 4, "fid"),
                                           ("waste_percent", "Pairs generated and never used (\\%)", 1, "waste"),
                                           ("wait_ms", "Wait for a free memory (ms)", 2, "wait")):
            for b in (2, 4):
                pv = pivot(metric, b)
                polis = [p for p in ORDER if p in pv.columns and not pv[p].isna().all()]
                rows = [[NAMES[w]] + [f(pv.loc[w, p], digits) if w in pv.index else "--" for p in polis] for w in MT.ORDER]
                MT.table(GEN / f"fp_{topo}_{key}_{b}.tex", ["Workload"] + polis, rows,
                         f"{title}, {label}, {b} memories per core (modelled), mean of three mapping seeds of the mean of three physics seeds.",
                         f"tab:fp-{topo}-{key}-{b}")
        # win table
        lat = t.pivot_table(index=["workload", "total_memories"], columns="policy", values="latency_ms")
        gain = ((lat["ODG"] - lat["Dynamic"]) / lat["ODG"] * 100).unstack("total_memories")
        rows = [[NAMES[w]] + [f(gain.loc[w, b], 0, pct=True) if (w in gain.index and b in gain.columns and pd.notna(gain.loc[w, b])) else "--" for b in BUDGETS[1:]] for w in MT.ORDER]
        MT.table(GEN / f"fp_{topo}_gain.tex", ["Workload"] + [str(b) + ("$^*$" if b > 4 else "") for b in BUDGETS[1:]], rows,
                 f"Latency gain of dynamic over on-demand, $(\\text{{ODG}}-\\text{{Dyn.}})/\\text{{ODG}}$, {label}; negative means dynamic is slower. "
                 "Budgets marked $^*$ are counterfactual.", f"tab:fp-{topo}-gain")
        # where dynamic lies: the memory count from which it beats on-demand, and how it stands against CGP and ACGP
        rows = []
        for w in MT.ORDER:
            if w not in lat.index.get_level_values(0):
                continue
            sub = lat.loc[w]
            def first_win(a, b):
                ok = [m for m in sub.index if m >= 2 and pd.notna(sub.loc[m, a]) and pd.notna(sub.loc[m, b]) and sub.loc[m, a] < sub.loc[m, b]]
                later_loss = [m for m in sub.index if m >= 2 and pd.notna(sub.loc[m, a]) and pd.notna(sub.loc[m, b]) and sub.loc[m, a] >= sub.loc[m, b]]
                if not ok:
                    return "never"
                start = min(ok)
                return f"{start}" if not [m for m in later_loss if m > start] else f"{start}$^\\dagger$"
            def count(a, b):
                both = [m for m in sub.index if m >= 2 and pd.notna(sub.loc[m, a]) and pd.notna(sub.loc[m, b])]
                win = sum(sub.loc[m, a] < sub.loc[m, b] - 1e-9 for m in both)
                loss = sum(sub.loc[m, a] > sub.loc[m, b] + 1e-9 for m in both)
                return f"{win}/{len(both) - win - loss}/{loss}"
            fid = t[(t.workload == w) & (t.total_memories == 4)].set_index("policy").fidelity
            rows.append([NAMES[w], first_win("Dynamic", "ODG"), count("Dynamic", "CGP"), count("Dynamic", "ACGP"),
                         f(fid.get("Dynamic"), 3), f(fid.get("CGP"), 3), f(fid.get("ACGP"), 3), f(fid.get("ODG"), 3)])
        MT.table(GEN / f"fp_{topo}_where.tex", ["Workload", "Dynamic beats ODG from (memories)", "vs CGP win/tie/loss", "vs ACGP win/tie/loss",
                                                "Fidelity Dyn.", "CGP", "ACGP", "ODG"], rows,
                 f"Where dynamic lies, {label}. Column~2: the smallest memory count from which dynamic has lower latency than on-demand "
                 "($^\\dagger$: with at least one later count where it does not). Columns~3--4: over the memory counts "
                 "run for both policies (2 to 32; QFT also 64), the number at which dynamic has lower latency, equal latency (the floor reached when nothing waits) or higher latency than CGP and than ACGP. Columns~5--8: delivered fidelity at four memories.",
                 f"tab:fp-{topo}-where", colspec="lcccrrrr")
        best = lat.idxmin(axis=1).groupby(level="total_memories").value_counts().unstack(fill_value=0).reindex(columns=ORDER, fill_value=0)
        rows = [[str(b)] + [str(int(best.loc[b, p])) if b in best.index else "0" for p in ORDER] for b in BUDGETS]
        MT.table(GEN / f"fp_{topo}_best.tex", ["Mem."] + ORDER, rows,
                 f"{label.capitalize()}: number of benchmarks (of ten) on which each policy has the lowest latency at each memory count "
                 "(a policy is counted only where it was run; dynamic, CGP and ACGP start at two memories).", f"tab:fp-{topo}-best", colspec="rrrrr")
        for png, cap, lab in (("latency.png", "Request latency against memories per core, all four policies (log scale).", "lat"),
                              ("fidelity.png", "Delivered EPR fidelity against memories per core.", "fid"),
                              ("waste.png", "Pairs generated and never used, as a percentage of pairs generated (dynamic, CGP, ACGP).", "waste"),
                              ("wait.png", "Average wait for a free memory (log scale).", "wait"),
                              ("readiness.png", "Pre-generated pairs consumed per request (pairs are counted at both endpoints, so the unit is pairs used divided by twice the requests).", "ready")):
            if (folder / png).exists():
                shutil.copy(folder / png, FIG / f"fp_{topo}_{png}")
                landscape(f"fig_fp_{topo}_{lab}.tex", FIG / f"fp_{topo}_{png}",
                          f"{cap} {label.capitalize()}, corrected scheduler, mean of three mapping seeds of the mean of three physics seeds; CGP and ACGP cache at most memories$-1$ pairs per core.",
                          f"fig:fp-{topo}-{lab}")


def main() -> int:
    GEN.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    skipped: list = []
    legacy_tables(skipped)
    diagnostics_tables(skipped)
    four_policy_tables(skipped)
    print("policy comparison tables written; skipped:", skipped or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
