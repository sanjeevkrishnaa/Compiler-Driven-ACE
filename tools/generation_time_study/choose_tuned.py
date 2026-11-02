"""Pick, per context, the Dynamic option to validate.  Uses the tuning seeds (60-63) only.

Rule, fixed before looking at validation seeds: in each context (workload, memories, efficiency) take the
non-default option with the lowest mean Dynamic latency, provided its latency is below the default's by
more than the two 95% intervals added together.  A context with no such option validates only the default.
"""
from __future__ import annotations

import json

import pandas as pd

import experiments
from collect import DATA


def main() -> None:
    table = pd.read_csv(DATA / "tuning_summary.csv")
    table = table[table.strategy == "dynamic"]
    choices = []
    for (workload, memories, efficiency), group in table.groupby(["workload", "memories", "memory_efficiency"]):
        default = group[group.tag == "default"].iloc[0]
        others = group[group.tag != "default"].copy()
        others = others[others.latency_ms < default.latency_ms - default.latency_ms_ci - others.latency_ms_ci]
        if others.empty:
            continue
        best = others.sort_values("latency_ms").iloc[0]
        options = dict(experiments.tuning_options(int(memories), int(memories) - 1))[best.tag]
        choices.append(dict(workload=workload, memories=int(memories), compiler_memories=int(memories) - 1,
                            memory_efficiency=float(efficiency), tag=best.tag, options=options,
                            tuning_default_ms=float(default.latency_ms), tuning_option_ms=float(best.latency_ms)))
    (DATA / "tuned_choices.json").write_text(json.dumps(choices, indent=1))
    for choice in choices:
        print(choice["workload"], choice["memories"], choice["memory_efficiency"], choice["tag"], choice["options"],
              round(choice["tuning_default_ms"], 3), "->", round(choice["tuning_option_ms"], 3))


if __name__ == "__main__":
    main()
