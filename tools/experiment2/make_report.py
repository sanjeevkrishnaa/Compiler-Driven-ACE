#!/usr/bin/env python3
"""Write results/experiment2_*/ (CSVs and figures for capacities 1 to 4) and docs/reports/experiment2-own-vs-relay.md."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import split_congestion as s                                                 # noqa: E402

OUT = REPO / "results" / "experiment2_own_vs_relay_2026-10-24"
CAPACITIES = (1, 2, 3, 4)


def cell(d, k, c, f, digits=1, scale=1.0):
    v = s.mean_over_seeds(d, k, c, f)
    return "-" if v is None else f"{scale * v:.{digits}f}"


def pooled(d, k):
    own = sum(s.mean_over_seeds(d, k, c, "own_percent") for c in range(16))
    rel = sum(s.mean_over_seeds(d, k, c, "relay_only_percent") for c in range(16))
    return own, rel


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    hop = {C: s.compute(C, "hop") for C in CAPACITIES}
    route = {C: s.compute(C, "route") for C in CAPACITIES}
    for C in CAPACITIES:
        for name, data in (("hop", hop[C]), ("route", route[C])):
            folder = OUT / f"capacity_{C}"
            folder.mkdir(exist_ok=True)
            s.write_csv(data, folder / f"split_{name}.csv")
            s.draw(data, C, name, folder / f"split_{name}.png")
    titles = dict(s.ORDER)

    def share_table(source, label):
        lines = [f"| Workload | " + " | ".join(f"C={C}" for C in CAPACITIES) + " |", "|---|" + "---:|" * len(CAPACITIES)]
        for k, _ in s.ORDER:
            cells = []
            for C in CAPACITIES:
                own, rel = pooled(source[C], k)
                cells.append("no overload" if own + rel == 0 else f"{100 * own / (own + rel):.1f}% ({own + rel:.0f})")
            lines.append(f"| {titles[k]} | " + " | ".join(cells) + " |")
        return "\n".join(lines)

    hottest = ["| Workload | Hottest core | Overloaded % | own % | relay-only % | Relay share of its demand when overloaded | Relay share of its excess |",
               "|---|---|---:|---:|---:|---:|---:|"]
    for k, _ in s.ORDER:
        d = hop[4]
        top = max(range(16), key=lambda c: s.mean_over_seeds(d, k, c, "overloaded_percent"))
        if s.mean_over_seeds(d, k, top, "overloaded_percent") == 0:
            hottest.append(f"| {titles[k]} | none | 0.0 | 0.0 | 0.0 | - | - |")
            continue
        hottest.append(f"| {titles[k]} | C{top} | {cell(d,k,top,'overloaded_percent')} | {cell(d,k,top,'own_percent')} | "
                       f"{cell(d,k,top,'relay_only_percent')} | {cell(d,k,top,'mean_relay_share_when_overloaded',0,100)}% | "
                       f"{cell(d,k,top,'relay_share_of_excess',0,100)}% |")

    import tempfile, zipfile, collections
    from hotspot_analysis import read_trace
    peaks = ["| Workload | Peak demand D at one core in one layer | Peak endpoint demand D_end | Peak routes through one core |", "|---|---:|---:|---:|"]
    with tempfile.TemporaryDirectory() as t, zipfile.ZipFile(s.ARCHIVE) as z:
        for k, _ in s.ORDER:
            pd = pe = pr = 0
            for seed in s.SEEDS:
                tr = read_trace(Path(z.extract(f"{s.PREFIX}/{k}/seed_{seed}/requests.txt", t)), 4, 4)
                by = collections.defaultdict(list)
                for h in tr.hops:
                    by[h.layer].append(h)
                for hops in by.values():
                    for _, (dd, ee) in s.layer_demand(hops, "hop").items():
                        pd, pe = max(pd, dd), max(pe, ee)
                    for _, (dd, ee) in s.layer_demand(hops, "route").items():
                        pr = max(pr, dd)
            peaks.append(f"| {titles[k]} | {pd} | {pe} | {pr} |")

    doc = f"""# Experiment 2: how much of each core's congestion is its own demand, and how much is relay traffic

Data and figures: `results/experiment2_own_vs_relay_2026-10-24/` (CSV and PNG per capacity and counting variant).
Code: `tools/experiment2/split_congestion.py` (tests in `tools/experiment2/tests/`). Structural analysis of the archived
mapped traces: it counts demand, it simulates no physics, and it is independent of the request scheduler.

## Definitions

* A **route** is a qubit's consecutive hops within one layer. Its first source and final destination are its **endpoints**;
  every core in between is a **relay**. (The traces already split a long move into one hop per link.)
* For a core and a layer, **D** is the number of hops touching the core. **D_end** counts the touches that are a route
  endpoint; **D_relay** counts the rest. A relay core is touched by two hops of the route (one arriving, one leaving), so
  it contributes 2; an endpoint contributes 1. D = D_end + D_relay.
* With capacity C (communication memories per core), a layer is **overloaded** for the core when D > C. It is
  **own-overloaded** when D_end > C (endpoint demand alone is too much) and **relay-only-overloaded** when
  D_end <= C < D (it would have fit without relay traffic). These sets are disjoint and together are exactly the
  overloaded layers, so own% + relay-only% is the heatmap's overloaded%.
* Percentages are over communication-active layers, per mapping seed, then the equal-weight mean over seeds 42, 43, 44.
* *Relay share of the excess* is the part of `max(0, D - C)` that endpoint demand alone would not have caused:
  `(max(0, D - C) - max(0, D_end - C)) / max(0, D - C)`, summed over layers.
* Two ways of counting, both reported. **hop** is the archive's counting (above). **route** counts qubits in flight under
  per-qubit ordering: a route's hops run one after another, so a relay core needs one memory for it at a time, not two.

## Validation

* With the **hop** counting, own% + relay-only% reproduces **all 160 cells** of the project's per-core heatmap (at its
  printed 0.1% resolution), and the per-core relay incidences, incident hops and peak layer demand reproduce **all 480
  per-trial rows** of the archive's `all_trials_cores.csv` exactly. Both are pinned by tests.
* The two sets add up to the overloaded layers for every core and seed (tested), and route counting never reports more
  overload than hop counting (tested).

## Result 1: at the modelled capacity of 4, congestion is relay congestion

Hottest core of each workload (hop counting, capacity 4):

{chr(10).join(hottest)}

Peak demand, to show how close endpoint demand comes to the capacity:

{chr(10).join(peaks)}

At capacity 4 endpoint demand alone almost never exceeds the capacity: its peak is 4 in QFT and Draper, 5 in QAOA and
at most 3 in the other workloads, while total demand reaches 24. The only own-overload at capacity 4 is in QAOA, at the
corner cores C0 and C3 (0.61% of active layers each), which is 0.44% of QAOA's overload; in every other workload it is zero. The cores that overload are the central ones (C5, C6,
C9, C10) that many routes pass through, so the overload is caused by routes passing through, not by routes starting or
ending there. Where overload exists, relay touches are about 78 to 93% of the demand in the overloaded layers.

## Result 2: smaller memory budgets bring in own-demand overload

Share of the overloaded core-layers that come from own endpoint demand (hop counting); in brackets, the total overload
in core-layer percentage points summed over the 16 cores (so 100 means the equivalent of one core overloaded in every layer):

{share_table(hop, "hop")}

With four memories almost nothing is own-overload. With one memory a core is overloaded by its own endpoint demand as
soon as two routes start or end there, so QFT is 77% own-overload at capacity 1 and mostly relay-overload from capacity 2
upward. A routing change that moves traffic away from the central cores can only remove the relay part; the own part is a
floor set by the mapping.

## Result 3: counting qubits in flight, not hops

A relay needs one memory at a time, not two, so the demand is lower. Same table with route counting:

{share_table(route, "route")}

Route counting finds less overload (for example core C10 at capacity 4 is overloaded in {cell(route[4],'qft',10,'overloaded_percent')}% of QFT's active layers against {cell(hop[4],'qft',10,'overloaded_percent')}% under hop counting, and in {cell(route[4],'draper_qft_adder',10,'overloaded_percent')}% against {cell(hop[4],'draper_qft_adder',10,'overloaded_percent')}% for Draper), and relay traffic is still essentially all of what remains at capacity 4. Which counting the simulator behaves like is
a scheduler fact: under the corrected per-qubit scheduler a chain's next hop is admitted only after the previous one finishes,
which is the route counting.

## What this does and does not say

* It says where demand comes from, measured on the archived mappings. It does not say what a routing algorithm would
  achieve: that needs a routing policy that exists and is simulated, and none does yet.
* It bounds the benefit of one. Removing every relay touch at capacity 4 would remove essentially all of the overload
  (all of it except QAOA's 0.44%), because endpoint demand is almost always within capacity; that is an upper bound, since the routes cannot all avoid central
  cores. At capacity 1 or 2 a router could remove at most the relay share shown in Result 2.
* The traces' hop paths are shortest paths with a reliability tie-break, not dimension-ordered routes
  (only 46.7% of multi-hop routes match XY), so the relay locations are as the mapper produced them.
"""
    (REPO / "docs" / "reports" / "experiment2-own-vs-relay.md").write_text(doc, encoding="utf-8")
    print("wrote", OUT, "and the report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
