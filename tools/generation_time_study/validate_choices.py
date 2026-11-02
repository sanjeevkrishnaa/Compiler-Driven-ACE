"""Did the options chosen on the tuning seeds still help on seeds that tuning never saw?

For each chosen (context, option): the change in Dynamic latency relative to the default, on tuning seeds 60-63
and on validation seeds 100-105, with a Welch 95% interval for the validation change.  An option "holds" when the
validation interval excludes zero on the same side as tuning.  Validation also reports the same-seed ODG
comparison, because an option that helps Dynamic but loses to ODG is not a win.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from collect import DATA


def welch_change(new: np.ndarray, base: np.ndarray) -> tuple[float, float]:
    """Percent change of the means and the half-width of its 95% interval (delta method)."""
    ratio = new.mean() / base.mean()
    se = ratio * np.sqrt(new.var(ddof=1) / len(new) / new.mean() ** 2 + base.var(ddof=1) / len(base) / base.mean() ** 2)
    df = len(new) + len(base) - 2
    return 100 * (ratio - 1), 100 * stats.t.ppf(0.975, df) * se


def main() -> None:
    choices = json.loads((DATA / "tuned_choices.json").read_text())
    trials = pd.read_csv(DATA / "validation_trials.csv.gz")
    tuning = pd.read_csv(DATA / "tuning_trials.csv.gz")
    rows = []
    for choice in choices:
        w, m, e, tag = choice["workload"], choice["memories"], choice["memory_efficiency"], choice["tag"]
        context = lambda f: f[(f.workload == w) & (f.memories == m) & np.isclose(f.memory_efficiency, e)]
        val = context(trials)
        default = val[(val.tag == "default") & (val.strategy == "dynamic")].latency_ms.to_numpy()
        odg = val[(val.tag == "default") & (val.strategy == "on-demand")].latency_ms.to_numpy()
        chosen = val[(val.tag == tag) & (val.strategy == "dynamic")].latency_ms.to_numpy()
        tune = context(tuning)
        t_default = tune[(tune.tag == "default") & (tune.strategy == "dynamic")].latency_ms.to_numpy()
        t_chosen = tune[(tune.tag == tag) & (tune.strategy == "dynamic")].latency_ms.to_numpy()
        change, half = welch_change(chosen, default)
        t_change, _ = welch_change(t_chosen, t_default)
        odg_change, odg_half = welch_change(chosen, odg)
        rows.append(dict(workload=w, memories=m, memory_efficiency=e, option=tag, tuning_change_percent=round(t_change, 1),
                         validation_change_percent=round(change, 1), validation_interval=round(half, 1),
                         holds=bool(change + half < 0), still_beats_odg=bool(odg_change + odg_half < 0),
                         default_vs_odg_percent=round(welch_change(default, odg)[0], 1), chosen_vs_odg_percent=round(odg_change, 1),
                         validation_seeds=int(len(chosen))))
    table = pd.DataFrame(rows)
    table.to_csv(DATA / "validation_check.csv", index=False)
    print(table.to_string(index=False))
    print("hold:", int(table.holds.sum()), "of", len(table))


if __name__ == "__main__":
    main()
