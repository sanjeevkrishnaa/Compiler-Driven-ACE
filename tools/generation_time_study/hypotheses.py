"""Apply each pre-registered falsification rule of docs/research/generation-time-2026-11-01/plan.md to the collected data.

Every verdict is a number or a count from the CSV files in data/, never prose written by hand.  The result is
data/hypotheses.json; the report prints it.  Where a hypothesis fails only in part, the failing part is listed.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from collect import DATA

KEYS = ["workload", "route", "memories", "compiler_memories", "tag", "lead", "lookahead", "reservation_ms", "generation_capacity"]


def paired(frame: pd.DataFrame, extra: list[str]) -> pd.DataFrame:
    keys = [k for k in KEYS + extra if k in frame.columns]
    dyn = frame[frame.strategy == "dynamic"]
    odg = frame[frame.strategy == "on-demand"][keys + ["latency_ms", "makespan_s", "miss_generation_ms"]]
    odg = odg.rename(columns={c: c + "_odg" for c in ["latency_ms", "makespan_s", "miss_generation_ms"]})
    out = dyn.merge(odg, on=keys)
    out["saving_ms"] = out.latency_ms_odg - out.latency_ms
    return out


def h1_h2(result: dict) -> None:
    link = pd.read_csv(DATA / "link_screen.csv")
    link = link[link.samples > 0]
    link["tolerance"] = link.generation_ci_ms + 0.02 * link.predicted_generation_ms
    link["time_ok"] = (link.generation_mean_ms - link.predicted_generation_ms).abs() <= link.tolerance
    link["attempts_ok"] = (link.attempts_mean - link.predicted_attempts).abs() <= link.attempts_ci + 0.02 * link.predicted_attempts
    failing = link[~link.time_ok]
    result["H1"] = dict(
        probes=int(len(link)), attempts_within_tolerance=int(link.attempts_ok.sum()), time_within_tolerance=int(link.time_ok.sum()),
        time_failures=[dict(knob=r.knob, value=float(r.value), source=int(r.source), error_percent=round(float(r.error_percent), 1))
                       for r in failing.itertuples()],
        per_attempt_ms_by_direction={f"{int(s)}->{int(d)}": round(float(v), 4) for (s, d), v in
                                     link[link.knob == "base"].groupby(["source", "destination"]).ms_per_attempt_mean.mean().items()},
        base_generation_ms=round(float(link[link.knob == "base"].generation_mean_ms.mean()), 4),
        base_predicted_ms=round(float(link[link.knob == "base"].predicted_generation_ms.mean()), 4))
    base = link[(link.knob == "base") & (link.source.isin((0, 1))) & (link.destination.isin((0, 1)))]
    reference = base.groupby("source").generation_mean_ms.mean()
    inert = {}
    for knob in ("coherence_time_s", "raw_fidelity", "gate_fidelity", "measurement_fidelity", "empty_gap_ms", "dark_count_per_s"):
        group = link[link.knob == knob]
        deviation = (group.generation_mean_ms - group.source.map(reference)).abs() / group.source.map(reference) * 100
        inert[knob] = dict(max_percent=round(float(deviation.max()), 2), within_interval=bool((group.generation_mean_ms - group.source.map(reference)).abs().le(group.generation_ci_ms + base.generation_ci_ms.max()).all()))
    frequency = link[link.knob == "memory_frequency_hz"]
    result["H2"] = dict(max_deviation_percent_from_base=inert,
                        memory_frequency_exceptions=[dict(hz=float(r.value), source=int(r.source), error_percent=round(float(r.error_percent), 1))
                                                      for r in frequency[~frequency.time_ok].itertuples()],
                        frequency_ok_from_hz=float(frequency[frequency.time_ok].value.min()))


def h3(result: dict) -> None:
    trials = pd.read_csv(DATA / "equivalence_trials.csv.gz")
    trials["cause"] = np.where(trials.memory_efficiency < 0.95, "memory", np.where(trials.detector_efficiency < 0.95, "detector", "bsm_rate"))
    rows = []
    for (workload, strategy), group in trials.groupby(["workload", "strategy"]):
        for metric in ("latency_ms", "makespan_s", "hit_rate", "fidelity"):
            samples = {c: g[metric].to_numpy() for c, g in group.groupby("cause")}
            for a, b in (("memory", "detector"), ("memory", "bsm_rate"), ("detector", "bsm_rate")):
                if np.allclose(samples[a].std(), 0) and np.allclose(samples[b].std(), 0):
                    continue
                t, p = stats.ttest_ind(samples[a], samples[b], equal_var=False)
                se = np.sqrt(samples[a].var(ddof=1) / len(samples[a]) + samples[b].var(ddof=1) / len(samples[b]))
                rows.append(dict(workload=workload, strategy=strategy, metric=metric, pair=f"{a}-{b}",
                                 relative_difference_percent=round(100 * float(samples[a].mean() / samples[b].mean() - 1), 2),
                                 difference_in_standard_errors=round(float(abs(samples[a].mean() - samples[b].mean()) / se), 2), p=round(float(p), 3)))
    table = pd.DataFrame(rows)
    result["H3"] = dict(comparisons=int(len(table)), beyond_two_standard_errors=int((table.difference_in_standard_errors > 2).sum()),
                        significant_after_bonferroni=int((table.p < 0.05 / len(table)).sum()), expected_beyond_two_se_by_chance=round(len(table) * 0.05, 1),
                        largest_relative_difference_percent=float(table.relative_difference_percent.abs().max()),
                        details=table[table.difference_in_standard_errors > 2].to_dict("records"))


def h4_h5(result: dict) -> None:
    eff = pd.read_csv(DATA / "efficiency_summary.csv")
    eff = eff[eff.route == "history"]
    dyn = eff[eff.strategy == "dynamic"]
    result["H4"] = dict(
        planner_blocked_spread_across_efficiency={f"{w} M{m}": round(float(g.blocked_rate.max() - g.blocked_rate.min()), 4)
                                                   for (w, m), g in dyn.groupby(["workload", "memories"])},
        misses_equal_blocked_at_fast_generation={f"{w} M{m}": round(float((g[g.memory_efficiency >= 0.9].fallback_rate - g[g.memory_efficiency >= 0.9].blocked_rate).abs().max()), 4)
                                                  for (w, m), g in dyn.groupby(["workload", "memories"])},
        ready_of_planned_at={f"{w} M{m}": {str(e): round(float(r), 3) for e, r in zip(g.memory_efficiency, g.ready_of_planned)
                                           if e in (0.95, 0.6, 0.4, 0.3)} for (w, m), g in dyn.groupby(["workload", "memories"])})
    pair = paired(eff, ["memory_efficiency"])
    rows = {}
    for (w, m), g in pair.groupby(["workload", "memories"]):
        g = g.sort_values("memory_efficiency", ascending=False)
        peak = g.loc[g.gain_latency_ms.idxmax()]
        rows[f"{w} M{m}"] = dict(peak_gain_percent=round(float(peak.gain_latency_ms), 1), peak_efficiency=float(peak.memory_efficiency),
                                 gain_at_1_0=round(float(g.iloc[0].gain_latency_ms), 1), gain_at_lowest=round(float(g.iloc[-1].gain_latency_ms), 1),
                                 interior_maximum=bool(0 < list(g.memory_efficiency).index(peak.memory_efficiency) < len(g) - 1),
                                 absolute_saving_monotone=bool((g.saving_ms.diff().dropna() > -0.01).all()),
                                 saving_at_1_0_ms=round(float(g.iloc[0].saving_ms), 3), saving_at_lowest_ms=round(float(g.iloc[-1].saving_ms), 3))
    result["H5"] = rows


def h6(result: dict) -> None:
    gap = pd.read_csv(DATA / "gap_summary.csv")
    pair = paired(gap, ["memory_efficiency", "empty_gap_ms"])
    rows = {}
    for (w, m, e), g in pair.groupby(["workload", "memories", "memory_efficiency"]):
        g = g.sort_values("empty_gap_ms")
        rows[f"{w} M{m} eff {e}"] = {f"gap {r.empty_gap_ms:g}": dict(gain=round(float(r.gain_latency_ms), 1), hit=round(float(r.hit_rate), 3)) for r in g.itertuples()}
    unaffected = [k for k, v in rows.items() if max(x["hit"] for x in v.values()) - min(x["hit"] for x in v.values()) < 0.02]
    result["H6"] = dict(contexts=rows, contexts_with_hit_rate_unchanged_by_gap=unaffected)


def h7(result: dict) -> None:
    scale = pd.read_csv(DATA / "scale_summary.csv")
    rows = {}
    for (workload, tag), g in scale.groupby(["workload", "tag"]):
        dyn, odg = g[g.strategy == "dynamic"].sort_values("classical_scale"), g[g.strategy == "on-demand"].sort_values("classical_scale")
        rows[f"{workload} {tag}"] = dict(scales=list(dyn.classical_scale), gain_percent=[round(float(x), 1) for x in dyn.gain_latency_ms],
                                         hit_rate=[round(float(x), 4) for x in dyn.hit_rate],
                                         odg_latency_per_scale=[round(float(l / s), 4) for l, s in zip(odg.latency_ms, odg.classical_scale)],
                                         retried_rate=[round(float(x), 4) for x in dyn.retried_rate])
    result["H7"] = rows


def h8_h9_h10(result: dict) -> None:
    lead = pd.read_csv(DATA / "lead_gap_summary.csv")
    lead = lead[lead.strategy == "dynamic"]
    best = {}
    for (w, m, e, g), x in lead.groupby(["workload", "memories", "memory_efficiency", "empty_gap_ms"]):
        row = x.loc[x.latency_ms.idxmin()]
        best[f"{w} M{m} eff {e} gap {g:g}"] = dict(best_lead=int(row.lead), latency_ms=round(float(row.latency_ms), 3),
                                                  lead2_ms=round(float(x[x.lead == 2].latency_ms.iloc[0]), 3), worst_ms=round(float(x.latency_ms.max()), 3))
    result["H8"] = dict(best_lead=best, distinct_best_leads=sorted({v["best_lead"] for v in best.values()}))
    co = pd.read_csv(DATA / "coherence_summary.csv")
    pair = paired(co, ["memory_efficiency", "coherence_time_s"])
    result["H9"] = {f"{r.workload} eff {r.memory_efficiency} coherence {r.coherence_time_s:g} s": dict(gain=round(float(r.gain_latency_ms), 1), fidelity=round(float(r.fidelity), 3),
                                                                                                      expired=round(float(r.expired), 0), hit=round(float(r.hit_rate), 3))
                    for r in pair.itertuples() if r.memory_efficiency in (0.95, 0.4)}
    eff = pd.read_csv(DATA / "efficiency_summary.csv")
    pair = paired(eff, ["memory_efficiency"])
    wide = pair.pivot_table(index=["workload", "memories", "memory_efficiency"], columns="route", values="gain_latency_ms").reset_index()
    wide["difference"] = wide["history"] - wide["xy"]
    rows = {}
    for (w, m), g in wide.groupby(["workload", "memories"]):
        g = g.sort_values("memory_efficiency", ascending=False)
        rho, p = stats.spearmanr(-np.log(g.memory_efficiency), g.difference)
        rows[f"{w} M{m}"] = dict(difference_at_1_0=round(float(g.iloc[0].difference), 2), difference_max=round(float(g.difference.max()), 2),
                                 difference_min=round(float(g.difference.min()), 2), spearman_rho=round(float(rho), 2), p=round(float(p), 3),
                                 history_always_ahead=bool((g.difference > 0).all()))
    result["H10"] = rows
    routes = pd.read_csv(DATA / "routes_summary.csv")
    pair = paired(routes, ["memory_efficiency"])
    result["H10_routes"] = {f"{w} eff {e}": {r.route: round(float(r.gain_latency_ms), 1) for r in g.itertuples()}
                            for (w, e), g in pair.groupby(["workload", "memory_efficiency"])}


def main() -> None:
    result: dict = {}
    h1_h2(result)
    h3(result)
    h4_h5(result)
    h6(result)
    h7(result)
    h8_h9_h10(result)
    (DATA / "hypotheses.json").write_text(json.dumps(result, indent=1, default=float))
    print(json.dumps({k: result[k] for k in ("H1", "H2", "H3", "H4", "H5", "H10")}, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
