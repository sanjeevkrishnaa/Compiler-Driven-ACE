"""A two-part analytic model of why Dynamic helps, checked against the simulator.

1. Readiness.  A prepared pair is ready in time when its attempts finish before the request starts.  With
   success probability p per attempt and a cycle of c = 4 delta (forward hop) or 5 delta (reverse hop),
   attempts k are geometric, so P(ready | slack s) = 1 - (1 - p)^floor(s / c).  The slack distribution is
   read from the same run (its 10th, 50th and 90th percentiles and its maximum), so the only things the
   model supplies are p and c, both fixed by the physical knobs.  Prediction is compared with the
   measured share of accepted preparations that were ready.
2. Break-even.  Dynamic latency = h L_hit + (1 - h) L_miss, with h the hit rate.  Dynamic beats ODG when
   h exceeds h* = (L_miss - L_odg) / (L_miss - L_hit).  L_hit, L_miss and L_odg are measured per class.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import experiments
from collect import DATA
from knobs import Knobs, success_probability
from run_matrix import RUNS, case_key


def slack_cdf(quantiles: dict) -> np.ndarray:
    points = np.array([[0.0, quantiles["p10"]], [0.1, quantiles["p10"]], [0.5, quantiles["p50"]], [0.9, quantiles["p90"]], [1.0, quantiles["max"]]])
    return np.interp(np.linspace(0.005, 0.995, 200), points[:, 0], points[:, 1])


def predicted_ready(spec: dict, trial: dict) -> float:
    knobs = Knobs(**spec["knobs"])
    p = success_probability(knobs)
    delta = 0.1 * knobs.classical_scale
    forward = trial["groups"].get("forward", {}).get("n", 0)
    reverse = trial["groups"].get("reverse", {}).get("n", 0)
    weight = forward / (forward + reverse)
    slack = slack_cdf(trial["slack_ms"])
    out = 0.0
    for share, cycle in ((weight, 4 * delta), (1 - weight, 5 * delta)):
        attempts = np.floor(slack / cycle)
        out += share * float(np.mean(1 - (1 - p) ** attempts))
    return out


def main() -> None:
    rows = []
    for name in ("efficiency", "delay", "gap", "lead_gap", "scale", "chip", "memory", "coherence"):
        for spec in experiments.EXPERIMENTS[name]():
            path = RUNS / case_key(spec) / "reduced.json"
            if not path.exists() or spec["route"] != "history":
                continue
            reduced = json.loads(path.read_text())
            for trial in reduced["trials"]:
                if trial["strategy"] != "dynamic" or not trial["slack_ms"] or trial["runtime_accepted_preparations"] <= 0:
                    continue
                rows.append(dict(experiment=name, workload=spec["workload"], memories=spec["memories"], seed=trial["seed"], lead=spec["lead"],
                                 gap=spec["knobs"].get("empty_gap_ms", 5.0), efficiency=spec["knobs"].get("memory_efficiency", 0.95),
                                 scale=spec["knobs"].get("classical_scale", 1.0), coherence=spec["knobs"].get("coherence_time_s", 1.0),
                                 measured=trial["pregenerated_hits"] / trial["runtime_accepted_preparations"],
                                 predicted=predicted_ready(spec, trial), accepted=trial["runtime_accepted_preparations"]))
    table = pd.DataFrame(rows)
    table.to_csv(DATA / "model_readiness_trials.csv.gz", index=False, float_format="%.6g", compression={"method": "gzip", "mtime": 0})
    clean = table[(table.gap >= 5) & (table.coherence >= 1.0) & (table.lead == 2)]
    for label, frame in (("time-limited cases (gap >= 5 ms, lead 2, coherence 1 s)", clean), ("all cases", table)):
        error = frame.predicted - frame.measured
        print(f"{label}: n={len(frame)}  mean abs error {error.abs().mean():.4f}  bias {error.mean():+.4f}  "
              f"R2 {1 - (error ** 2).sum() / ((frame.measured - frame.measured.mean()) ** 2).sum():.4f}")
    by = clean.groupby(["experiment", "workload", "memories", "efficiency", "scale"]).agg(measured=("measured", "mean"), predicted=("predicted", "mean")).reset_index()
    by.to_csv(DATA / "model_readiness.csv", index=False, float_format="%.5g")
    print(by[(by.experiment == "efficiency") & (by.memories == 4)].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
