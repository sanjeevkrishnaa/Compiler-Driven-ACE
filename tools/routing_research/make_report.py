#!/usr/bin/env python3
"""Write docs/reports/offline-routing-research.md and the LaTeX tables from the committed offline-routing results."""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
R = REPO / "results" / "offline_routing_2026-10-24"
GEN = REPO / "docs" / "latex" / "ace_report" / "generated"
NAMES = {"ghz": "GHZ", "bv": "Bernstein-Vazirani", "bmw_quark_cardinality": "BMW/QUARK cardinality", "vqe_real_amp": "VQE real amplitudes",
         "cdkm_ripple_carry_adder": "CDKM ripple-carry adder", "graphstate": "Graph state", "draper_qft_adder": "Draper QFT adder",
         "qaoa": "QAOA", "qft": "QFT", "randomcircuit": "Random circuit"}
ORDER = list(NAMES)


def load(p):
    with open(p, newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def pooled(rows, variant):
    agg = defaultdict(Counter)
    for r in rows:
        if r["variant"] == variant:
            k = (int(r["capacity"]), int(r["extra_hops"]))
            for f in ("baseline_excess", "optimised_excess", "best_lower_bound", "baseline_overloaded_layers", "optimised_overloaded_layers",
                      "added_hops", "total_hops", "layers_not_proved_optimal"):
                agg[k][f] += int(r[f])
    return agg


def md(header, rows):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(r) + " |" for r in rows])


def structural_rows(agg):
    out = []
    for (cap, extra), a in sorted(agg.items()):
        red = 100 * (1 - a["optimised_excess"] / a["baseline_excess"]) if a["baseline_excess"] else 0.0
        out.append([str(cap), str(extra), f"{a['baseline_excess']}", f"{a['optimised_excess']} ({red:.1f}%)", f"{a['best_lower_bound']}",
                    f"{a['baseline_overloaded_layers']} → {a['optimised_overloaded_layers']}", f"{100 * a['added_hops'] / a['total_hops']:.2f}%"])
    return out


def paired(sim_path):
    rows = load(sim_path)
    d = {(r["label"], r["mapping_seed"], r["seed"], r["budget"]): r for r in rows}
    out = {}
    for w in ["graphstate", "draper_qft_adder", "qaoa", "qft", "randomcircuit"]:
        for b in ("2", "3", "4"):
            cells = {}
            for extra in (0, 2):
                ch, lat, wait = [], [], []
                for ms in ("42", "43", "44"):
                    for s in ("0", "1", "2"):
                        o = d[(w, ms, s, b)]
                        n = d[(f"{w}__c{b}_e{extra}", ms, s, b)]
                        ch.append(100 * (float(o["latency_ms"]) - float(n["latency_ms"])) / float(o["latency_ms"]))
                        lat.append(float(n["latency_ms"]))
                        wait.append(float(n["waited_fraction"]))
                cells[extra] = (st.fmean(ch), st.stdev(ch), sum(c > 0 for c in ch), st.fmean(lat), st.fmean(wait))
            base = [float(d[(w, ms, s, b)]["latency_ms"]) for ms in ("42", "43", "44") for s in ("0", "1", "2")]
            basew = [float(d[(w, ms, s, b)]["waited_fraction"]) for ms in ("42", "43", "44") for s in ("0", "1", "2")]
            out[(w, b)] = (st.fmean(base), st.fmean(basew), cells)
    return out


def sim_rows(p):
    rows = []
    for (w, b), (base, basew, cells) in p.items():
        c0, c2 = cells[0], cells[2]
        rows.append([NAMES[w], b, f"{base:.2f}", f"{c0[3]:.2f} ({c0[0]:+.1f}% ±{c0[1]:.1f}; {c0[2]}/9)", f"{c2[3]:.2f} ({c2[0]:+.1f}% ±{c2[1]:.1f}; {c2[2]}/9)",
                     f"{basew:.3f} → {c0[4]:.3f}"])
    return rows


def main() -> int:
    mesh, torus = load(R / "mesh" / "study.csv"), load(R / "torus" / "study.csv")
    head = ["Capacity", "Extra hops", "Excess now", "Excess after re-routing", "Lower bound", "Overloaded layers", "Added hops"]
    sections = ["# Can offline routing reduce the congestion?", "",
                "Mapping held fixed; only the path of each qubit move is re-chosen, per layer, offline (exact optimisation, global knowledge of the layer). "
                "*Excess* is the demand above capacity, summed over cores and layers. All numbers pool the ten benchmarks and the three mapping seeds; "
                "data in `results/offline_routing_2026-10-24/`, code in `tools/routing_research/`.", "",
                "**What is proved.** The optimiser is exact (no layer was left unproved), never worse than the mapper's own routes, and bounded below by two valid lower bounds: "
                "endpoint demand alone, and total demand minus cores x capacity. No routing can beat the larger of the two.", ""]
    for name, rows in (("mesh", mesh), ("torus", torus)):
        for variant, label in (("route", "route counting (qubits in flight, what the per-qubit scheduler sees)"), ("hop", "hop counting (the archive's counting)")):
            sections += [f"## Structural result, {name}, {label}", "", md(head, structural_rows(pooled(rows, variant))), ""]
    sims = [("mesh", R / "mesh" / "simulated.csv")]
    if (R / "torus" / "simulated.csv").exists():
        sims.append(("torus", R / "torus" / "simulated.csv"))
    for name, path in sims:
        sections += [f"## Simulated effect on latency, {name} (on-demand, same mapping, endpoints and seeds)", "",
                     "Latency in ms, mean of nine runs. In brackets: paired reduction against the original routes (positive = faster), its standard deviation over the nine pairs, "
                     "and the number of pairs in which re-routing was faster. Last column: fraction of requests that waited, original → re-routed (no extra hops).", "",
                     md(["Workload", "Memories", "Original routes", "Re-routed, shortest paths only", "Re-routed, up to +2 hops", "Waited"], sim_rows(paired(path))), ""]
    (REPO / "docs" / "reports" / "offline-routing-research.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
    # LaTeX
    def tex_table(name, header, rows, caption, label, colspec):
        lines = [r"\begin{table}[H]", r"\centering\small", rf"\begin{{tabular}}{{@{{}}{colspec}@{{}}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
        lines += [" & ".join(c.replace("%", r"\%").replace("→", r"$\to$").replace("±", r"$\pm$").replace("&", r"\&") for c in r) + r" \\" for r in rows]
        lines += [r"\bottomrule", r"\end{tabular}", rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{table}"]
        (GEN / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    GEN.mkdir(parents=True, exist_ok=True)
    for topo, rows in (("mesh", mesh), ("torus", torus)):
        tex_table(f"routing_struct_{topo}.tex", head, structural_rows(pooled(rows, "route")),
                  f"Offline re-routing, {topo}, route counting, pooled over ten benchmarks and three mapping seeds. Excess is demand above capacity.", f"tab:routing-{topo}", "rrrrrrr")
    for name, path in sims:
        tex_table(f"routing_sim_{name}.tex", ["Workload", "Mem.", "Original", "Re-routed", "+2 hops", "Waited"], sim_rows(paired(path)),
                  f"Simulated on-demand latency (ms), {name}: original routes against offline re-routing. Brackets: paired reduction, sd, pairs faster of nine.",
                  f"tab:routing-sim-{name}", "lrrrrr")
    print("wrote docs/reports/offline-routing-research.md and LaTeX tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
