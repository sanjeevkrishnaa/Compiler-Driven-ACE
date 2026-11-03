"""Break-even hit rate of Dynamic, from measured per-class latencies.

Dynamic latency = h L_hit + (1 - h) L_rest, where L_rest is the mean over every request that was not a hit
(late pairs and requests served on demand).  Dynamic beats ODG exactly when h > h* = (L_rest - L_odg) / (L_rest - L_hit).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from collect import DATA


def main() -> None:
    frames = []
    for name in ("efficiency", "gap", "delay", "chip", "scale", "lead_gap", "memory", "coherence"):
        frame = pd.read_csv(DATA / f"{name}_summary.csv")
        frame["experiment"] = name
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True)
    table = table[table.route == "history"]
    keys = ["experiment", "workload", "memories", "compiler_memories", "tag", "lead", "memory_efficiency", "classical_scale", "empty_gap_ms",
            "coherence_time_s", "reservation_ms", "request_retry_ms", "compiler_retry_ms"]
    keys = [k for k in keys if k in table.columns]
    dyn = table[table.strategy == "dynamic"]
    odg = table[table.strategy == "on-demand"][keys + ["latency_ms"]].rename(columns={"latency_ms": "odg_ms"})
    merged = dyn.merge(odg, on=keys)
    h = merged.hit_rate
    merged["rest_ms"] = (merged.latency_ms - h * merged.hit_latency_ms) / (1 - h)
    merged["break_even"] = (merged.rest_ms - merged.odg_ms) / (merged.rest_ms - merged.hit_latency_ms)
    merged["margin"] = merged.hit_rate - merged.break_even
    merged["wins"] = merged.latency_ms < merged.odg_ms
    merged["model_says_wins"] = merged.margin > 0
    merged["model_correct"] = merged.wins == merged.model_says_wins
    keep = keys + ["hit_rate", "hit_latency_ms", "rest_ms", "odg_ms", "latency_ms", "break_even", "margin", "wins", "model_says_wins", "model_correct"]
    merged[keep].to_csv(DATA / "model_breakeven.csv", index=False, float_format="%.5g")
    print("cases", len(merged), "| identity holds (model_correct):", int(merged.model_correct.sum()))
    print("break-even hit rate: median %.3f  range %.3f..%.3f" % (merged.break_even.median(), merged.break_even.min(), merged.break_even.max()))
    print("L_hit ms: median %.3f | L_rest minus L_odg ms: median %.3f" % (merged.hit_latency_ms.median(), (merged.rest_ms - merged.odg_ms).median()))
    losing = merged[~merged.wins]
    print("cases where Dynamic loses:", len(losing), "| their hit rate median %.3f vs break-even median %.3f" % (losing.hit_rate.median(), losing.break_even.median()))
    print("in those cases L_rest - L_odg (extra cost of a non-hit): median %.3f ms" % (losing.rest_ms - losing.odg_ms).median())
    print(merged[(merged.experiment == "gap") & (merged.workload == "qft") & (merged.memories == 4) & (merged.memory_efficiency == 0.95)]
          [["empty_gap_ms", "hit_rate", "hit_latency_ms", "rest_ms", "odg_ms", "break_even"]].round(3).sort_values("empty_gap_ms").to_string(index=False))


if __name__ == "__main__":
    main()
