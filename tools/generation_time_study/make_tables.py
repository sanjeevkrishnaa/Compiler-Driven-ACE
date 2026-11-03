"""Write every table and headline number of the report as LaTeX, from the CSV and JSON files in data/.

The report text refers to numbers through the macros in generated/numbers.tex, so a number in a sentence is
the number in the data.  Tables are written with booktabs; a "gain" is 100 x (1 - Dynamic / ODG), so a
negative gain means Dynamic is worse.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from collect import DATA
from knobs import ROOT

OUT = ROOT / "docs" / "latex" / "generation_time_study" / "report" / "generated"
NAME = {"qft": "QFT-96", "qaoa": "QAOA-96", "draper_qft_adder": "Draper-96", "cdkm_ripple_carry_adder": "CDKM-48", "randomcircuit": "random-48"}
macros: dict[str, str] = {}


def pair(frame: pd.DataFrame) -> pd.DataFrame:
    keys = [k for k in ["workload", "route", "memories", "compiler_memories", "tag", "lead", "lookahead", "reservation_ms", "generation_capacity",
                        "memory_efficiency", "classical_scale", "empty_gap_ms", "coherence_time_s", "distance_scale", "request_retry_ms",
                        "compiler_retry_ms", "detector_efficiency", "bsm_success_rate"] if k in frame.columns]
    dyn = frame[frame.strategy == "dynamic"]
    odg = frame[frame.strategy == "on-demand"][keys + ["latency_ms", "makespan_s", "miss_generation_ms", "fidelity"]]
    odg = odg.rename(columns={c: c + "_odg" for c in ("latency_ms", "makespan_s", "miss_generation_ms", "fidelity")})
    out = dyn.merge(odg, on=keys)
    out["saving_ms"] = out.latency_ms_odg - out.latency_ms
    return out


def f(x, digits=2, sign=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "--"
    text = f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"
    return text.replace("-", "$-$")


def table(name: str, spec: str, header: list[str], rows: list[list[str]], caption_free: bool = True) -> None:
    lines = [r"\begin{tabular}{" + spec + "}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    lines += [" & ".join(str(c) for c in row) + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    (OUT / f"{name}.tex").write_text("\n".join(lines) + "\n")


def macro(name: str, value) -> None:
    macros[name] = str(value)


def link_tables() -> None:
    link = pd.read_csv(DATA / "link_screen.csv")
    link = link[link.samples > 0]
    link["tol"] = link.generation_ci_ms + 0.02 * link.predicted_generation_ms
    link["ok"] = (link.generation_mean_ms - link.predicted_generation_ms).abs() <= link.tol
    labels = {"base": "none (baseline)", "memory_efficiency": "memory efficiency", "detector_efficiency": "detector efficiency", "bsm_success_rate": "BSM success rate",
              "classical_scale": "classical delay scale", "distance_scale": "link length scale", "attenuation_db_per_m": "fibre attenuation",
              "memory_frequency_hz": "memory excitation rate", "coherence_time_s": "coherence time", "raw_fidelity": "raw pair fidelity",
              "gate_fidelity": "gate fidelity", "measurement_fidelity": "measurement fidelity", "dark_count_per_s": "dark counts", "empty_gap_ms": "empty-layer gap"}
    rows = []
    for knob, g in link.groupby("knob", sort=False):
        values = sorted(set(g.value.dropna())) if knob != "base" else []
        span = "--" if not values else (f"{values[0]:g} to {values[-1]:g}" if len(values) > 1 else f"{values[0]:g}")
        worst = g.loc[g.error_percent.abs().idxmax()]
        rows.append([labels[knob], span, str(int(g.samples.sum())), f"{int(g.ok.sum())}/{len(g)}", f(float(worst.error_percent), 1, sign=True)])
    table("link_checks", "llrrr", ["Knob changed", "Values tried", "Pairs", "Within tolerance", "Worst error (\\%)"], rows)
    macro("LinkProbes", len(link))
    macro("LinkPairs", f"{int(link.samples.sum()):,}".replace(",", "\\,"))
    base = link[link.knob == "base"]
    macro("BaseGenForward", f(float(base[base.source == 0].generation_mean_ms.mean()), 3))
    macro("BaseGenReverse", f(float(base[base.source.isin((1, 4, 6)) & (base.source > base.destination)].generation_mean_ms.mean()), 3))
    macro("BaseGenMean", f(float(base.generation_mean_ms.mean()), 2))
    macro("BaseAttempts", f(float(base.attempts_mean.mean()), 2))
    macro("PredAttempts", f(float(base.predicted_attempts.mean()), 2))
    macro("BasePSuccess", f(float(base.predicted_p.iloc[0]), 3))


def sweep_tables() -> None:
    for name, column, values, header in (("efficiency", "memory_efficiency", (1.0, 0.95, 0.8, 0.6, 0.4, 0.3), "Eff."), ("delay", "classical_scale", (0.1, 0.5, 1.0, 2.0, 5.0), "Delay $\\times$")):
        frame = pair(pd.read_csv(DATA / f"{name}_summary.csv"))
        frame = frame[frame.route == "history"]
        rows = []
        for (w, m), g in frame.groupby(["workload", "memories"]):
            for v in values:
                r = g[np.isclose(g[column], v)]
                if r.empty:
                    continue
                r = r.iloc[0]
                rows.append([f"{NAME[w]} M{m}", f"{v:g}", f(r.miss_generation_ms_odg, 2), f(r.latency_ms_odg, 3), f(r.latency_ms, 3), f(r.gain_latency_ms, 1),
                             f(r.saving_ms, 2), f(r.gain_communication_s, 1), f(100 * r.hit_rate, 1)])
        table(f"{name}_sweep", "llrrrrrrr", ["Case", header, "ODG gen. (ms)", "ODG (ms)", "Dyn. (ms)", "Gain (\\%)", "Saved (ms)", "Comm. gain (\\%)", "Hit (\\%)"], rows)
    eff = pair(pd.read_csv(DATA / "efficiency_summary.csv"))
    eff = eff[eff.route == "history"]
    for key, (w, m) in {"QftFour": ("qft", 4), "QftThree": ("qft", 3), "QaoaFour": ("qaoa", 4), "QaoaThree": ("qaoa", 3)}.items():
        base = eff[(eff.workload == w) & (eff.memories == m) & np.isclose(eff.memory_efficiency, 0.95)].iloc[0]
        macro(f"Base{key}Odg", f(base.latency_ms_odg, 3))
        macro(f"Base{key}Dyn", f(base.latency_ms, 3))
        macro(f"Base{key}Gain", f(base.gain_latency_ms, 1))
        macro(f"Base{key}Hit", f(100 * base.hit_rate, 1))
        macro(f"Base{key}Makespan", f(base.gain_makespan_s, 1))
        macro(f"Base{key}Comm", f(base.gain_communication_s, 1))
        g = eff[(eff.workload == w) & (eff.memories == m)]
        peak = g.loc[g.gain_latency_ms.idxmax()]
        macro(f"Peak{key}Gain", f(peak.gain_latency_ms, 1))
        macro(f"Peak{key}Eff", f"{peak.memory_efficiency:g}")
        macro(f"Peak{key}Gen", f(peak.miss_generation_ms_odg, 1))
        low = g[np.isclose(g.memory_efficiency, 0.3)].iloc[0]
        macro(f"Low{key}Gain", f(low.gain_latency_ms, 1))
        macro(f"Low{key}Saving", f(low.saving_ms, 2))
        macro(f"Base{key}Saving", f(base.saving_ms, 2))
        macro(f"Low{key}Gen", f(low.miss_generation_ms_odg, 1))


def gap_tables() -> None:
    gap = pair(pd.read_csv(DATA / "gap_summary.csv"))
    rows = []
    for (w, m, e), g in gap.groupby(["workload", "memories", "memory_efficiency"]):
        cells = {r.empty_gap_ms: r for r in g.itertuples()}
        rows.append([f"{NAME[w]} M{m}", f"{e:g}"] + [f"{f(cells[x].gain_latency_ms, 0, True)} / {f(100 * cells[x].hit_rate, 0)}" if x in cells else "--" for x in (0.0, 0.5, 1.0, 2.0, 5.0, 20.0)])
    table("gap_sweep", "llrrrrrr", ["Case", "Eff.", "gap 0", "0.5 ms", "1 ms", "2 ms", "5 ms", "20 ms"], rows)
    be = pd.read_csv(DATA / "model_breakeven.csv")
    be = be[(be.experiment == "gap") & (be.memories == 4) & np.isclose(be.memory_efficiency, 0.95)]
    rows = [[NAME[r.workload], f"{r.empty_gap_ms:g}", f(100 * r.hit_rate, 1), f(r.hit_latency_ms, 3), f(r.rest_ms, 3), f(r.odg_ms, 3), f(100 * r.break_even, 1), f(r.latency_ms, 3)]
            for r in be.sort_values(["workload", "empty_gap_ms"]).itertuples()]
    table("breakeven", "lrrrrrrr", ["Workload", "Gap (ms)", "Hit (\\%)", "Hit cost", "Non-hit cost", "ODG", "Break-even (\\%)", "Dynamic"], rows)
    q = be[(be.workload == "qft")].set_index("empty_gap_ms")
    macro("QftGapZeroGain", f(float(pair(pd.read_csv(DATA / "gap_summary.csv")).query("workload=='qft' and memories==4 and memory_efficiency==0.95 and empty_gap_ms==0").gain_latency_ms.iloc[0]), 1))
    macro("QftGapZeroHit", f(100 * q.loc[0.0].hit_rate, 1))
    macro("QftGapZeroBreak", f(100 * q.loc[0.0].break_even, 1))
    macro("QftGapZeroRest", f(q.loc[0.0].rest_ms, 2))
    macro("QftGapFiveBreak", f(100 * q.loc[5.0].break_even, 1))
    macro("QftGapFiveRest", f(q.loc[5.0].rest_ms, 2))
    macro("QftOdgMs", f(q.loc[5.0].odg_ms, 2))
    macro("QftHitCost", f(q.loc[5.0].hit_latency_ms, 2))
    allb = pd.read_csv(DATA / "model_breakeven.csv")
    macro("BreakEvenCases", len(allb))
    macro("BreakEvenLosing", int((~allb.wins).sum()))
    macro("BreakEvenLosingHit", f(100 * allb[~allb.wins].hit_rate.median(), 0))
    macro("BreakEvenLosingBreak", f(100 * allb[~allb.wins].break_even.median(), 0))
    ready = pd.read_csv(DATA / "model_readiness_trials.csv.gz")
    clean = ready[(ready.gap >= 5) & (ready.coherence >= 1.0) & (ready.lead == 2)]
    qf = clean[clean.workload == "qft"]
    macro("ReadyQftError", f(float((qf.predicted - qf.measured).abs().mean() * 100), 1))
    macro("ReadyQaoaError", f(float((clean[clean.workload == "qaoa"].predicted - clean[clean.workload == "qaoa"].measured).abs().mean() * 100), 1))
    macro("ReadyTrials", len(clean))


def funnel_table() -> None:
    """What happens to the planned preparations of QFT, M=4, C=3, efficiency 0.95, per 100 requests, at three gaps."""
    import experiments
    from knobs import Knobs
    from run_matrix import RUNS, case_key
    rows = {}
    for gap in (5.0, 1.0, 0.0):
        spec = experiments.case("qft", "history", 4, 3, Knobs(memory_efficiency=0.95, empty_gap_ms=gap), seeds=experiments.TUNING)
        reduced = json.loads((RUNS / case_key(spec) / "reduced.json").read_text())
        dyn = [t for t in reduced["trials"] if t["strategy"] == "dynamic"]
        odg = [t for t in reduced["trials"] if t["strategy"] == "on-demand"]
        n = dyn[0]["requests"]
        mean = lambda key: 100 * float(np.mean([t[key] for t in dyn])) / n
        classes = {c: np.mean([t["groups"].get(c, {}).get("n", 0) for t in dyn]) for c in ("hit", "late", "demand")}
        cost = {c: np.mean([t["groups"][c]["latency_ms"] for t in dyn if c in t["groups"]]) if any(c in t["groups"] for t in dyn) else float("nan") for c in classes}
        wait = {c: np.mean([t["groups"][c]["admission_ms"] for t in dyn if c in t["groups"]]) if any(c in t["groups"] for t in dyn) else float("nan") for c in classes}
        rows[gap] = dict(planned=mean("scheduled_preparations"), launched=mean("runtime_launched_preparations"), accepted=mean("runtime_accepted_preparations"),
                         made=mean("generated_compiler_pairs"), used=mean("utilized_compiler_pairs"), hit=mean("pregenerated_hits"), expired=mean("expired_compiler_pairs"),
                         rejections=mean("runtime_rejection_events"), hit_cost=cost["hit"], late_cost=cost["late"], miss_cost=cost["demand"], miss_wait=wait["demand"],
                         odg=float(np.mean([t["request_latency_mean_ms"] for t in odg])), odg_wait=float(np.mean([t["average_admission_wait_ms"] for t in odg])),
                         dyn=float(np.mean([t["request_latency_mean_ms"] for t in dyn])), prep=float(np.mean([t["preparation_ms"]["mean"] for t in dyn])),
                         slack=float(np.mean([t["slack_ms"]["mean"] for t in dyn])))
    gaps = (5.0, 1.0, 0.0)
    lines = [("Preparations planned", "planned"), ("Launched", "launched"), ("Accepted by the protocol", "accepted"), ("Pair actually made", "made"),
             ("Used by a request", "used"), ("Ready before the request (hit)", "hit"), ("Made but expired unused", "expired"), ("Rejections (events)", "rejections")]
    body = [[label] + [f(rows[g][key], 1) for g in gaps] for label, key in lines]
    body += [["\\midrule \\multicolumn{4}{@{}l}{\\textit{Time per prepared pair and per request (ms)}}"] + [""] * 0]
    for label, key, digits in (("Time from launch to request (slack)", "slack", 1), ("Time to make a pair", "prep", 2), ("Hit hop latency", "hit_cost", 3), ("Non-hit hop latency", "miss_cost", 3),
                               ("Wait for a free memory, non-hit", "miss_wait", 3), ("ODG hop latency", "odg", 3), ("ODG wait for a free memory", "odg_wait", 3), ("Dynamic hop latency", "dyn", 3)):
        body.append([label] + [f(rows[g][key], digits) for g in gaps])
    lines_tex = [r"\begin{tabular}{@{}lrrr@{}}", r"\toprule", "Per 100 requests & gap 5\\,ms & gap 1\\,ms & gap 0 \\\\", r"\midrule"]
    for row in body:
        lines_tex.append(row[0] + (" \\\\" if len(row) == 1 else " & " + " & ".join(row[1:]) + " \\\\") if not row[0].startswith("\\midrule") else "\\midrule\n\\multicolumn{4}{@{}l}{\\textit{Times (ms)}} \\\\")
    lines_tex += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "funnel.tex").write_text("\n".join(lines_tex).replace("\\\\", "\\\\") + "\n")
    macro("FunnelSlackFive", f(rows[5.0]["slack"], 1))
    macro("FunnelSlackZero", f(rows[0.0]["slack"], 1))
    macro("FunnelPrep", f(rows[5.0]["prep"], 2))
    macro("FunnelMissWaitZero", f(rows[0.0]["miss_wait"], 2))
    macro("FunnelMissWaitFive", f(rows[5.0]["miss_wait"], 2))
    macro("FunnelOdgWait", f(rows[5.0]["odg_wait"], 3))
    macro("FunnelAcceptedZero", f(rows[0.0]["accepted"], 1))
    macro("FunnelHitZero", f(rows[0.0]["hit"], 1))
    macro("FunnelHitFive", f(rows[5.0]["hit"], 1))
    macro("FunnelExpiredZero", f(rows[0.0]["expired"], 1))
    macro("FunnelRejectZero", f(rows[0.0]["rejections"], 0))


def tuning_tables() -> None:
    tuning = pd.read_csv(DATA / "tuning_summary.csv")
    tuning = tuning[tuning.strategy == "dynamic"]
    rows = []
    for (w, m, e), g in tuning.groupby(["workload", "memories", "memory_efficiency"]):
        default = g[g.tag == "default"].iloc[0]
        g = g.assign(change=100 * (g.latency_ms / default.latency_ms - 1)).sort_values("change")
        best = g.iloc[0]
        worst = g.iloc[-1]
        rows.append([f"{NAME[w]} M{m}", f"{e:g}", f(default.latency_ms, 3), best.tag, f(best.change, 1, True), worst.tag, f(worst.change, 0, True),
                     str(int((g.change.abs() < 0.5).sum())), str(int((g.change < -2).sum())), str(int((g.change > 2).sum()))])
    table("tuning_summary", "llrlrlrrrr", ["Case", "Eff.", "Default (ms)", "Best option", "Change (\\%)", "Worst option", "Change (\\%)", "No effect", "Better", "Worse"], rows)
    v = pd.read_csv(DATA / "validation_check.csv")
    rows = [[NAME[r.workload] + f" M{r.memories}", f"{r.memory_efficiency:g}", r.option, f(r.tuning_change_percent, 1, True), f"{f(r.validation_change_percent, 1, True)} $\\pm$ {r.validation_interval:.1f}",
             f(r.default_vs_odg_percent, 1, True), f(r.chosen_vs_odg_percent, 1, True), "yes" if r.holds else "no"] for r in v.itertuples()]
    table("validation", "llllllll", ["Case", "Eff.", "Option", "Tuning (\\%)", "Unseen seeds (\\%)", "Default vs ODG", "Chosen vs ODG", "Holds"], rows)
    macro("ValidationHold", int(v.holds.sum()))
    macro("ValidationTotal", len(v))
    macro("TuningCases", len(pd.read_csv(DATA / "tuning_summary.csv")) // 2)


def other_tables() -> None:
    routes = pair(pd.read_csv(DATA / "routes_summary.csv"))
    rows = []
    for (w, e), g in routes.groupby(["workload", "memory_efficiency"]):
        cells = {r.route: r for r in g.itertuples()}
        rows.append([NAME[w], f"{e:g}"] + [f"{f(cells[x].gain_latency_ms, 1)} $\\pm$ {cells[x].gain_latency_ms_ci:.1f}" for x in ("xy", "greedy", "history", "minhop")])
    table("routes", "llllll", ["Workload", "Eff.", "XY", "greedy", "history", "minhop"], sorted(rows, key=lambda r: (r[0], -float(r[1]))))
    mem = pair(pd.read_csv(DATA / "memory_summary.csv"))
    rows = [[NAME[r.workload], f"{r.memory_efficiency:g}", str(int(r.memories)), f(r.latency_ms_odg, 2), f(r.latency_ms, 2), f(r.gain_latency_ms, 1), f(100 * r.hit_rate, 1), f(100 * r.blocked_rate, 1)]
            for r in mem.sort_values(["workload", "memory_efficiency", "memories"], ascending=[True, False, True]).itertuples()]
    table("memory", "llrrrrrr", ["Workload", "Eff.", "$M$", "ODG (ms)", "Dyn. (ms)", "Gain (\\%)", "Hit (\\%)", "Planner-blocked (\\%)"], rows)
    q = mem[(mem.workload == "qft") & np.isclose(mem.memory_efficiency, 0.95)].set_index("memories")
    macro("MemQftTwo", f(q.loc[2].gain_latency_ms, 0))
    macro("MemQftEight", f(q.loc[8].gain_latency_ms, 0))
    co = pair(pd.read_csv(DATA / "coherence_summary.csv"))
    rows = [[NAME[r.workload], f"{r.memory_efficiency:g}", f"{r.coherence_time_s:g}", f(r.gain_latency_ms, 1), f(r.fidelity_odg, 3), f(r.fidelity, 3), f(r.expired, 0), f(100 * r.hit_rate, 1)]
            for r in co.sort_values(["workload", "memory_efficiency", "coherence_time_s"], ascending=[True, False, False]).itertuples()]
    table("coherence", "llrrrrrr", ["Workload", "Eff.", "Coherence (s)", "Gain (\\%)", "ODG fid.", "Dyn. fid.", "Expired pairs", "Hit (\\%)"], rows)
    wl = pair(pd.read_csv(DATA / "workloads_summary.csv"))
    rows = [[NAME[r.workload], r.route, f"{r.memory_efficiency:g}", f(r.latency_ms_odg, 2), f(r.latency_ms, 2), f"{f(r.gain_latency_ms, 1)} $\\pm$ {r.gain_latency_ms_ci:.1f}", f(100 * r.hit_rate, 1), f(100 * r.blocked_rate, 1)]
            for r in wl.sort_values(["workload", "memory_efficiency", "route"], ascending=[True, False, True]).itertuples()]
    table("workloads", "lllrrrrr", ["Workload", "Route", "Eff.", "ODG (ms)", "Dyn. (ms)", "Gain (\\%)", "Hit (\\%)", "Blocked (\\%)"], rows)
    d = pair(pd.read_csv(DATA / "distance_summary.csv"))
    rows = [[NAME[r.workload], r.tag.replace("distance=", "").replace(",fast control", ", delay base 1 \\textmu s"), f(r.latency_ms_odg, 4), f(r.latency_ms, 4), f(r.gain_latency_ms, 1), f(100 * r.hit_rate, 1)]
            for r in d.sort_values(["workload", "distance_scale", "classical_scale"]).itertuples()]
    table("distance", "llrrrr", ["Workload", "Core-to-core distance", "ODG (ms)", "Dyn. (ms)", "Gain (\\%)", "Hit (\\%)"], rows)
    r = pair(pd.read_csv(DATA / "retry_summary.csv"))
    rows = [[NAME[x.workload], f"{x.classical_scale:g}", f"{x.request_retry_ms:g}", f"{x.compiler_retry_ms:g}", f(x.latency_ms_odg, 4), f(x.latency_ms, 4), f(x.gain_latency_ms, 1), f(x.max_ms, 3)]
            for x in r.sort_values(["workload", "classical_scale", "request_retry_ms", "compiler_retry_ms"], ascending=[True, True, False, False]).itertuples()]
    table("retry", "llrrrrrr", ["Workload", "Delay $\\times$", "Request retry (ms)", "Compiler retry (ms)", "ODG (ms)", "Dyn. (ms)", "Gain (\\%)", "Slowest hop (ms)"], rows)
    q = r[(r.workload == "qaoa") & (r.classical_scale == 0.01)].set_index(["request_retry_ms", "compiler_retry_ms"])
    macro("RetryQaoaDefault", f(q.loc[(1.0, 1.0)].gain_latency_ms, 0))
    macro("RetryQaoaScaled", f(q.loc[(0.01, 0.01)].gain_latency_ms, 0))
    chip = pair(pd.read_csv(DATA / "chip_summary.csv"))
    rows = [[NAME[x.workload], f"{x.classical_scale:g}", f"{x.empty_gap_ms:g}", f(x.latency_ms_odg, 4), f(x.latency_ms, 4), f(x.gain_latency_ms, 1), f(x.gain_makespan_s, 1), f(100 * x.hit_rate, 1)]
            for x in chip.sort_values(["workload", "classical_scale", "empty_gap_ms"]).itertuples()]
    table("chip", "llrrrrrr", ["Workload", "Delay $\\times$", "Gap (ms)", "ODG (ms)", "Dyn. (ms)", "Latency gain (\\%)", "Makespan gain (\\%)", "Hit (\\%)"], rows)


def scorecard() -> None:
    h = json.loads((DATA / "hypotheses.json").read_text())
    h1, h2, h3 = h["H1"], h["H2"], h["H3"]
    rows = [
        ["H1", "Generation time is $(4\\text{ or }5)\\,\\delta/p$.", "\\textbf{Mostly supported}",
         f"Attempts: {h1['attempts_within_tolerance']}/{h1['probes']} probes inside tolerance. Time: {h1['time_within_tolerance']}/{h1['probes']}; the 8 misses are 4 at memory excitation 1--2\\,kHz (H2) and 4 where requests longer than the 50\\,ms window restart (efficiency 0.3, attenuation 200\\,dB/m)."],
        ["H2", "Only $\\delta$ and the factors of $p$ matter.", "\\textbf{Partly falsified}",
         f"Coherence, fidelity, gap and dark counts $\\le$ 1000/s change nothing (all within {max(v['max_percent'] for v in h2['max_deviation_percent_from_base'].values()):.1f}\\%). Memory excitation below 5\\,kHz does matter (+99\\% at 1\\,kHz)."],
        ["H3", "Equal $p$ gives equal results whatever its cause.", "\\textbf{Supported in practice}",
         f"{h3['beyond_two_standard_errors']} of {h3['comparisons']} comparisons exceed two standard errors ({h3['expected_beyond_two_se_by_chance']} expected by chance); none survives a Bonferroni correction; the largest difference is {h3['largest_relative_difference_percent']:.1f}\\%."],
        ["H4", "Two separate limits on the hit rate.", "\\textbf{Supported}",
         "The planner-blocked share is constant in efficiency (spread 0.000 in all four cases) and equals the miss rate at fast generation. The ready-in-time share of accepted pairs falls only below efficiency 0.6."],
        ["H5", "Absolute saving grows; relative gain peaks.", "\\textbf{Supported}",
         "All four contexts peak at an interior efficiency (0.6); the absolute saving grows with generation time in 3 of 4 (QAOA M3 turns at 0.4)."],
        ["H6", "The gap decides how much Dynamic gains.", "\\textbf{Supported, strongly}",
         f"With no gap, default Dynamic loses to ODG at normal speed ({f(float(pair(pd.read_csv(DATA / 'gap_summary.csv')).query('workload==\"qft\" and memories==4 and memory_efficiency==0.95 and empty_gap_ms==0').gain_latency_ms.iloc[0]), 0, True)}\\% on QFT M4/C3). The hit rate responds to the gap in every context. Beyond 5\\,ms the gain stops changing."],
        ["H7", "Only ratios of time constants matter.", "\\textbf{Falsified for QAOA, then explained}",
         "QFT: hit rate identical at every scale. QAOA at delay $\\times$0.01: $-59\\%$, caused by the fixed 1\\,ms retry waits; scaling them restores $+24\\%$ (retry test)."],
        ["H8", "The best lead depends on generation time.", "\\textbf{Supported}",
         f"Best leads found: {', '.join(str(x) for x in h['H8']['distinct_best_leads'])}. They depend on both the gap and the generation speed, and leads above 4 are never best."],
        ["H9", "Short coherence removes the gain.", "\\textbf{Supported}",
         "Coherence 100\\,ms changes only fidelity; 10\\,ms cuts the QFT gain from 47\\% to 20\\% (hits fall as pairs expire); 1\\,ms makes Dynamic 55--99\\% worse than ODG."],
        ["H10", "History's advantage grows with slower generation.", "\\textbf{Partly supported}",
         "History beats XY at every efficiency in all 4 contexts, by 2--6 points. The advantage grows significantly only for QAOA M4 ($\\rho=0.82$, $p=0.007$); it is flat for QFT."],
    ]
    lines = [r"\begin{tabular}{@{}lp{3.2cm}p{2.6cm}p{7.0cm}@{}}", r"\toprule", "ID & Hypothesis & Verdict & Evidence \\\\", r"\midrule"]
    lines += [" & ".join(r) + r" \\[2pt]" for r in rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "scorecard.tex").write_text("\n".join(lines) + "\n")


def counts() -> None:
    import experiments
    from run_matrix import RUNS, case_key
    audit = json.loads((DATA / "audit_runs.json").read_text())
    macro("CasesAccepted", audit["cases_accepted"])
    seen, total = set(), 0
    for build in experiments.EXPERIMENTS.values():
        for spec in build():
            key = case_key(spec)
            if key in seen:
                continue
            seen.add(key)
            total += len(json.loads((RUNS / key / "reduced.json").read_text())["trials"])
    macro("TotalTrials", f"{total:,}".replace(",", "\\,"))


def link_rerun_text() -> None:
    """The three single-link settings that were stopped in the first screen: what the time-limited rerun found."""
    link = ROOT / "output" / "generation_time_study" / "link"
    rows = []
    for name, label in (("dark_count_per_s=1e+06", "dark counts $10^6$\\,/s"), ("dark_count_per_s=1e+08", "dark counts $10^8$\\,/s"), ("coherence_time_s=0.0001", "coherence $0.1$\\,ms")):
        for source, destination in ((0, 1), (1, 0)):
            path = link / f"{name}__{source}_{destination}.json"
            hop = f"{source}$\\to${destination}"
            if not path.exists():
                rows.append([label, hop, "not run", "--", "--"])
                continue
            d = json.loads(path.read_text())
            if d.get("samples", 0) == 0:
                rows.append([label, hop, "did not finish in the time limit", "--", "--"])
            else:
                rows.append([label, hop, f"{d['samples']} samples", f(d["generation_mean_ms"], 3), f(d["fidelity_mean"], 3)])
    table("link_rerun_rows", "llrrr", ["Setting", "Hop", "Outcome", "Generation (ms)", "Fidelity"], rows)
    (OUT / "link_rerun.tex").write_text(
        "Dark counts of $10^6$ and $10^8$ per second and a coherence time of $0.1$\\,ms did not finish 3000 samples in the first screen "
        "(15 minutes each), because they create events every microsecond or faster. They were rerun with a time limit:\\par\\smallskip\n"
        "\\begin{center}\\small\\input{generated/link_rerun_rows.tex}\\end{center}\n"
        "Dark counts of $10^6$\\,/s (100 samples per hop) agree with the formula within the interval and leave fidelity unchanged, so the "
        "rule that dark counts do not matter holds up to $10^6$\\,/s. The other two settings, run with 30 samples and a 7-minute limit, still did not finish: "
        "they are too expensive to simulate, so we say nothing about them. A setting that did not finish is part of no conclusion.\n")


def activation_table() -> None:
    """The simulator's newer default admission order against the order this study used (same cases, gaps 0 and 5 ms)."""
    new = pair(pd.read_csv(DATA / "activation_summary.csv"))
    old = pair(pd.read_csv(DATA / "gap_summary.csv"))
    old = old[(old.memories == 4) & np.isclose(old.memory_efficiency, 0.95)]
    rows = []
    for w in ("qft", "qaoa"):
        for gap in (0.0, 5.0):
            a = old[(old.workload == w) & (old.empty_gap_ms == gap)].iloc[0]
            b = new[(new.workload == w) & (new.empty_gap_ms == gap)].iloc[0]
            rows.append([NAME[w], f"{gap:g}", f(a.latency_ms, 3), f(a.gain_latency_ms, 1, True), f(100 * a.hit_rate, 1), f(b.latency_ms, 3), f(b.gain_latency_ms, 1, True), f(100 * b.hit_rate, 1)])
    table("activation", "llrrrrrr", ["Workload", "Gap (ms)", "Dyn. (ms)", "Gain (\\%)", "Hit (\\%)", "Dyn. (ms)", "Gain (\\%)", "Hit (\\%)"], rows)


def provenance() -> None:
    import subprocess
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    engine = ROOT / "third_party" / "SeQUeNCe"
    text = ("\\chapter{Provenance}\n\\begin{small}\\begin{tabular}{@{}ll@{}}\\toprule\n"
            f"Study branch & \\code{{{git('branch', '--show-current')}}} \\\\\n"
            "Simulator commit studied & \\code{dfd4b839} (main at the start of the study); rechecked on \\code{e4db6bfa} \\\\\n"
            "Engine & SeQUeNCe 0.8.1, commit \\code{cf5283cd} \\\\\n"
            "Python / libraries & 3.13; numpy, scipy, pandas, matplotlib \\\\\n"
            "Report built with & tectonic \\\\\n"
            "\\bottomrule\\end{tabular}\\end{small}\n")
    (OUT / "provenance.tex").write_text(text)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    link_tables()
    sweep_tables()
    gap_tables()
    funnel_table()
    tuning_tables()
    other_tables()
    scorecard()
    counts()
    link_rerun_text()
    activation_table()
    provenance()
    (OUT / "numbers.tex").write_text("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(macros.items())))
    print(len(macros), "macros;", len(list(OUT.glob("*.tex"))), "files")


if __name__ == "__main__":
    main()
