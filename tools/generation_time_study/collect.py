"""Flatten finished cases into the CSV files the figures, tables and report are built from.

<experiment>_trials.csv has one row per strategy and seed.  <experiment>_summary.csv has one row per
strategy and setting, with the mean, sample standard deviation and 95% t interval over seeds, and
the Dynamic-against-ODG gain paired by seed where both strategies ran in the same case.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import experiments
from knobs import Knobs, ROOT
from run_matrix import RUNS, case_key

DATA = ROOT / "docs" / "research" / "generation-time-2026-11-01" / "data"
METRICS = ("latency_ms", "median_ms", "p95_ms", "max_ms", "makespan_s", "communication_s", "admission_ms", "fidelity",
           "generation_phase_ms", "miss_generation_ms", "hit_rate", "late_rate", "fallback_rate", "planned_rate",
           "blocked_rate", "ready_of_planned", "preparation_ms", "preparation_p90_ms", "storage_ms", "slack_ms", "slack_p10_ms",
           "margin_p10_ms", "expired", "remaining", "waste_percent", "retries", "retried_rate", "hit_latency_ms",
           "miss_latency_ms", "late_latency_ms", "rejected_rate", "forward_generation_ms", "reverse_generation_ms",
           "forward_share")


def value(group: dict | None, name: str) -> float:
    return group[name] if group and group.get("n") else math.nan


def trial_row(reduced: dict, spec: dict, trial: dict) -> dict:
    settings = Knobs(**spec["knobs"])
    groups = trial["groups"]
    requests = trial["requests"]
    hits = trial.get("pregenerated_hits", 0.0)
    late = trial.get("late_compiler_pair_uses", 0.0)
    planned = trial.get("scheduled_preparations", 0.0)
    forward = groups.get("forward", {}).get("n", 0)
    reverse = groups.get("reverse", {}).get("n", 0)
    miss_keys = ("demand",)
    row = dict(workload=spec["workload"], route=spec["route"], memories=spec["memories"], compiler_memories=spec["compiler_memories"],
               tag=spec["tag"], strategy=trial["strategy"], seed=trial["seed"], lead=spec["lead"], lookahead=spec["lookahead"],
               reservation_ms=spec["reservation_ms"], generation_capacity=spec["generation_capacity"],
               layers=reduced["layers"], empty_layers=reduced["empty_layers"], hops=reduced["hops"],
               audit_violations=trial["audit_violations"], completion_rate=trial["completion_rate"])
    row.update(settings.as_dict())
    row.update(latency_ms=trial["request_latency_mean_ms"], median_ms=trial["request_latency_median_ms"],
               p95_ms=trial["request_latency_p95_ms"], max_ms=trial["request_latency_max_ms"],
               makespan_s=trial["end_to_end_latency_ms"] / 1000,
               communication_s=(trial["end_to_end_latency_ms"] - reduced["empty_layers"] * settings.empty_gap_ms) / 1000,
               admission_ms=trial["average_admission_wait_ms"], fidelity=trial["average_delivered_epr_fidelity"],
               generation_phase_ms=trial["avg_entanglement_generation_time_ms"],
               miss_generation_ms=value(groups.get("demand"), "generation_ms"),
               hit_rate=hits / requests, late_rate=late / requests,
               fallback_rate=trial.get("on_demand_fallbacks", math.nan) / requests,
               planned_rate=planned / requests, blocked_rate=trial.get("planner_blocked_preparations", math.nan) / requests,
               ready_of_planned=hits / planned if planned else math.nan,
               preparation_ms=value(trial["preparation_ms"], "mean"), preparation_p90_ms=value(trial["preparation_ms"], "p90"),
               storage_ms=value(trial["storage_ms"], "mean"), slack_ms=value(trial["slack_ms"], "mean"),
               slack_p10_ms=value(trial["slack_ms"], "p10"), margin_p10_ms=value(trial["margin_ms"], "p10"),
               expired=trial.get("expired_compiler_pairs", math.nan), remaining=trial.get("remaining_compiler_pairs", math.nan),
               waste_percent=trial.get("compiler_waste_percentage", math.nan), retries=trial["total_retries"],
               retried_rate=trial["requests_with_retries"] / requests, hit_latency_ms=value(groups.get("hit"), "latency_ms"),
               miss_latency_ms=value(groups.get("demand"), "latency_ms"), late_latency_ms=value(groups.get("late"), "latency_ms"),
               rejected_rate=trial.get("runtime_rejected_preparations", math.nan) / requests,
               forward_generation_ms=value(groups.get("demand_forward"), "generation_ms"),
               reverse_generation_ms=value(groups.get("demand_reverse"), "generation_ms"),
               forward_share=forward / (forward + reverse))
    return row


def load(name: str) -> tuple[pd.DataFrame, list[str]]:
    rows, missing = [], []
    for spec in experiments.EXPERIMENTS[name]():
        folder = RUNS / case_key(spec)
        path = folder / "reduced.json"
        if not path.exists():
            missing.append(folder.name + (" FAILED" if (folder / "failed.txt").exists() else ""))
            continue
        reduced = json.loads(path.read_text())
        rows += [trial_row(reduced, spec, trial) for trial in reduced["trials"]]
    return pd.DataFrame(rows), missing


def interval(values: np.ndarray) -> float:
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return math.nan
    return float(stats.t.ppf(0.975, len(values) - 1) * values.std(ddof=1) / math.sqrt(len(values)))


def summarise(trials: pd.DataFrame) -> pd.DataFrame:
    keys = ["workload", "route", "memories", "compiler_memories", "tag", "strategy", "lead", "lookahead", "reservation_ms",
            "generation_capacity", *Knobs().as_dict()]
    records = []
    for values, group in trials.groupby(keys, dropna=False, sort=False):
        record = dict(zip(keys, values))
        record.update(seeds=len(group), audit_violations=int(group["audit_violations"].sum()),
                      completion_min=float(group["completion_rate"].min()), hops=int(group["hops"].iloc[0]),
                      layers=int(group["layers"].iloc[0]), empty_layers=int(group["empty_layers"].iloc[0]))
        for metric in METRICS:
            data = group[metric].to_numpy(dtype=float)
            record[metric] = float(np.nanmean(data)) if np.any(~np.isnan(data)) else math.nan
            record[f"{metric}_sd"] = float(np.nanstd(data, ddof=1)) if np.sum(~np.isnan(data)) > 1 else math.nan
            record[f"{metric}_ci"] = interval(data)
        records.append(record)
    summary = pd.DataFrame(records)
    context = [k for k in keys if k != "strategy"]
    wide = trials.pivot_table(index=context + ["seed"], columns="strategy", values=["latency_ms", "makespan_s", "communication_s", "p95_ms"], dropna=False)
    if "dynamic" in trials["strategy"].values and "on-demand" in trials["strategy"].values:
        gains = []
        for metric in ("latency_ms", "makespan_s", "communication_s", "p95_ms"):
            ratio = 100 * (1 - wide[metric]["dynamic"] / wide[metric]["on-demand"])
            frame = ratio.groupby(level=context, dropna=False).agg(["mean", interval])
            frame.columns = [f"gain_{metric}", f"gain_{metric}_ci"]
            gains.append(frame)
        table = pd.concat(gains, axis=1).reset_index()
        table["strategy"] = "dynamic"
        summary = summary.merge(table, on=keys, how="left")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", default=[n for n in experiments.EXPERIMENTS if n != "validation"])
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        trials, missing = load(name)
        if trials.empty:
            print(name, "nothing yet", len(missing), "missing")
            continue
        trials.to_csv(DATA / f"{name}_trials.csv.gz", index=False, float_format="%.6g", compression={"method": "gzip", "mtime": 0})
        summary = summarise(trials)
        summary.to_csv(DATA / f"{name}_summary.csv", index=False, float_format="%.6g")
        bad = int(trials["audit_violations"].sum())
        incomplete = int((trials["completion_rate"] < 1).sum())
        print(f"{name}: {len(trials)} trials, {len(summary)} settings, missing {len(missing)}, violations {bad}, incomplete {incomplete}")
        for entry in missing[:4]:
            print("  missing", entry)


if __name__ == "__main__":
    main()
