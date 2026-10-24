#!/usr/bin/env python3
"""Write the LaTeX tables and copy the figures of docs/latex/ace_report from the committed result files.

Every number in the report's tables comes from here; nothing is typed by hand.  Sections whose data does not exist yet are skipped
and reported.

    python tools/latex/make_tables.py
"""
from __future__ import annotations

import csv
import json
import shutil
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "latex" / "ace_report"
GEN, FIG = OUT / "generated", OUT / "figures"
RESULTS = REPO / "results"
sys.path.insert(0, str(REPO / "tools" / "heatmap"))
sys.path.insert(0, str(REPO / "tools" / "experiment2"))
sys.path.insert(0, str(REPO / "tools" / "experiment1"))

NAMES = {"ghz": "GHZ", "bv": "Bernstein--Vazirani", "bmw_quark_cardinality": "BMW/QUARK cardinality",
         "vqe_real_amp": "VQE real amplitudes", "cdkm_ripple_carry_adder": "CDKM ripple-carry adder", "graphstate": "Graph state",
         "draper_qft_adder": "Draper QFT adder", "qaoa": "QAOA", "qft": "QFT", "randomcircuit": "Random circuit"}
ORDER = list(NAMES)
BUDGETS = [1, 2, 3, 4, 6, 8, 16, 32]


def tex(s) -> str:
    return str(s).replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("--", "-{}-")



def table(path: Path, header: list[str], rows: list[list[str]], caption: str, label: str, colspec: str | None = None,
          small: bool = True) -> None:
    colspec = colspec or "l" + "r" * (len(header) - 1)
    # every table is scaled down to the text width if it is wider (never scaled up)
    lines = [r"\begin{table}[H]", r"\centering" + (r"\small" if small else ""),
             r"\resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{%", rf"\begin{{tabular}}{{@{{}}{colspec}@{{}}}}", r"\toprule",
             " & ".join(header) + r" \\", r"\midrule"]
    lines += [" & ".join(r) + r" \\" for r in rows]
    lines += [r"\bottomrule", r"\end{tabular}}", rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{table}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def figure(name: str, source: Path, caption: str, label: str, width: str = r"\linewidth") -> None:
    shutil.copy(source, FIG / source.name)
    (GEN / name).write_text("\n".join([r"\begin{figure}[H]", r"\centering",
                                       rf"\includegraphics[width={width}]{{{source.name}}}",
                                       rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{figure}"]) + "\n", encoding="utf-8")


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def heatmap_tables(skipped: list[str]) -> None:
    import regenerate_heatmap as hm
    data = hm.compute(4)
    rows = []
    for k in ORDER:
        d = data[k]
        act, ov = sum(d["active_layers"].values()), sum(d["overloaded_layers"].values())
        top = max(range(16), key=lambda c: d["mean"][c])
        rows.append([NAMES[k], "/".join(str(d["active_layers"][s]) for s in hm.SEEDS), f"{100 * ov / act:.1f}\\%",
                     f"C{top} ({d['mean'][top]:.1f}\\%)"])
    table(GEN / "heatmap_summary.tex", ["Workload", "Active layers (seeds 42/43/44)", "Layers with any overload", "Hottest core"], rows,
          "Structural overload at capacity 4, pooled over the three mapping seeds.", "tab:heatmap", "lrrr")
    figure("fig_heatmap.tex", RESULTS / "heatmap_regenerated_2026-10-24" / "per_core_congestion.png",
           "Per-core congestion: percentage of communication-active layers in which a core's demand exceeds 4 slots (mean over three "
           "mapping seeds). All 160 cells match the project's earlier figure at 0.1\\% resolution.", "fig:heatmap")


def exp2_tables(skipped: list[str]) -> None:
    import split_congestion as s
    cap_rows = {}
    for variant in ("hop", "route"):
        rows = []
        for k in ORDER:
            cells = []
            for C in (1, 2, 3, 4):
                d = s.compute(C, variant) if (variant, C) not in cap_rows else cap_rows[(variant, C)]
                cap_rows[(variant, C)] = d
                own = sum(s.mean_over_seeds(d, k, c, "own_percent") for c in range(16))
                rel = sum(s.mean_over_seeds(d, k, c, "relay_only_percent") for c in range(16))
                cells.append("none" if own + rel == 0 else f"{100 * own / (own + rel):.1f}\\%")
            rows.append([NAMES[k]] + cells)
        table(GEN / f"exp2_own_share_{variant}.tex", ["Workload", "C=1", "C=2", "C=3", "C=4"], rows,
              f"Share of overloaded core-layers caused by a core's own endpoint demand ({variant} counting); the rest is relay-only overload.",
              f"tab:exp2-{variant}")
    figure("fig_exp2.tex", RESULTS / "experiment2_own_vs_relay_2026-10-24" / "capacity_4" / "split_hop.png",
           "Own endpoint demand against relay demand per core at capacity 4 (hop counting).", "fig:exp2", r"0.7\linewidth")


def exp1_tables(skipped: list[str]) -> None:
    main = RESULTS / "experiment1_ten_benchmarks_2026-10-24"
    if not (main / "results.csv").exists():
        skipped.append("experiment 1")
        return
    import analyze as A
    rows = A.load(main / "results.csv")
    grouped = A.cells(rows)
    for policy, metric, digits, name, cap in (("on-demand", "latency_ms", 2, "exp1_latency_ondemand", "Request latency (ms), on-demand, mean $\\pm$ sd over nine runs."),
                                              ("dynamic", "latency_ms", 2, "exp1_latency_dynamic", "Request latency (ms), dynamic pre-generation."),
                                              ("dynamic", "fidelity", 4, "exp1_fidelity_dynamic", "Delivered EPR fidelity, dynamic pre-generation."),
                                              ("on-demand", "waited_fraction", 3, "exp1_waiting_ondemand", "Fraction of requests that waited more than a microsecond for a free memory, on-demand.")):
        budgets = BUDGETS if policy == "on-demand" else BUDGETS[1:]
        body = []
        for w in ORDER:
            cells = []
            for b in budgets:
                s = A.stats(grouped.get((w, policy, b), {}).get(metric, []))
                cells.append("--" if s is None else (f"{s['mean']:.{digits}f}" if metric == "waited_fraction" or metric == "fidelity"
                                                     else f"{s['mean']:.{digits}f}$\\pm${s['sd']:.{digits}f}"))
            body.append([NAMES[w]] + cells)
        head = ["Workload"] + [f"{b}" + ("$^*$" if b > 4 else "") for b in budgets]
        table(GEN / f"{name}.tex", head, body, cap + " Budgets marked $^*$ are counterfactual (beyond the modelled four slots).",
              f"tab:{name.replace('_', '-')}", small=True)
    for fn, cap, lab in (("latency_vs_budget.png", "Request latency against communication memories per core.", "fig:exp1-latency"),
                         ("fidelity_vs_budget.png", "Delivered EPR fidelity against communication memories per core.", "fig:exp1-fidelity"),
                         ("waiting_vs_budget.png", "Fraction of requests that had to wait for a free memory.", "fig:exp1-waiting")):
        figure(f"fig_{fn.split('.')[0]}.tex", main / fn, cap + " Line: mean of nine runs; band: minimum to maximum; grey: counterfactual budgets.", lab)
    (GEN / "exp1_controls.tex").write_text(r"\begin{itemize}" + "\n" + "\n".join(
        r"  \item " + tex(l.replace(" -- ", ": ")) for l in (main / "controls.txt").read_text(encoding="utf-8").strip().splitlines()) + "\n" + r"\end{itemize}" + "\n")


def cutoff_tables(skipped: list[str]) -> None:
    base = RESULTS / "cutoff_study_2026-10-24"
    if not (base / "mechanism.csv").exists():
        skipped.append("cutoff")
        return
    rows = load(base / "mechanism.csv")
    body = [[tex(r["workload"]), tex(r["case"]), f"{r['completed']}/{r['requested']}", r["violations"], r["released_consumed"],
             r["released_reservation_expired"], r["memory_expiry_resets"], r["adaptive_bookings"], f"{float(r['makespan_ms']):.1f}"] for r in rows]
    table(GEN / "cutoff_mechanism.tex", ["Workload", "Case", "Done", "Viol.", "Consumed", "Window", "Cut-off", "Bookings", "Makespan ms"], body,
          "Which timer discards a cached pair (compiler pre-generation, 4 memories). Consumed: pairs used; Window: releases at the end of the reservation window; Cut-off: memory resets by the cut-off.",
          "tab:cutoff-mechanism", "llrrrrrrr")
    cache = load(base / "cache_strategies_random16.csv")
    body = [[tex(r["strategy"]), tex(r["cutoff_ratio"]), r["pairs_generated"], r["pairs_used"], r["reported_waste_percent"] + "\\%", r["true_unused_percent"] + "\\%",
             r["latency_ms"], r["fidelity"]] for r in cache]
    table(GEN / "cutoff_cache.tex", ["Strategy", "Cut-off ratio", "Generated", "Used", "Reported waste", "Real unused", "Latency ms", "Fidelity"], body,
          "Autonomous caches on Random-16 (4 memories, coherence 1 s): effect of the memory cut-off. Reported waste omits cut-off discards.", "tab:cutoff-cache", "llrrrrrr")


def torus_tables(skipped: list[str]) -> None:
    path = RESULTS / "mesh_vs_torus_2026-10-24" / "comparison.csv"
    if not path.exists():
        skipped.append("torus")
        return
    rows = load(path)
    f = lambda x, d=2: "--" if x in ("", None) else f"{float(x):.{d}f}"
    body = []
    for r in rows:
        w = r["workload"]
        body.append([NAMES[w], f"{float(r['hops_mesh']):.0f}/{float(r['hops_torus']):.0f}",
                     f"{float(r['overload_c4_mesh']):.1f}/{float(r['overload_c4_torus']):.1f}",
                     f"{f(r['ondemand_latency_b2_mesh'])}/{f(r['ondemand_latency_b2_torus'])}",
                     f"{f(r['ondemand_latency_b4_mesh'])}/{f(r['ondemand_latency_b4_torus'])}",
                     f"{f(r['dynamic_latency_b8_mesh'])}/{f(r['dynamic_latency_b8_torus'])}"])
    table(GEN / "torus_comparison.tex", ["Workload", "Hops", "Overload\\% at C=4", "On-demand ms, 2 mem.", "On-demand ms, 4 mem.", "Dynamic ms, 8 mem."], body,
          "Mesh/torus. Hops: mean requests per trace. Overload: \\% of active layers with any core above capacity 4. Latencies are means over nine runs.", "tab:torus", "lrrrrr")
    figure("fig_heatmap_torus.tex", RESULTS / "heatmap_torus_2026-10-24" / "per_core_congestion.png",
           "Per-core congestion on the torus (percentage of active layers in which a core's demand exceeds 4 slots; mean over three mapping seeds).", "fig:heatmap-torus")


def parameter_tables(skipped: list[str]) -> None:
    path = RESULTS / "experiment1_ten_benchmarks_2026-10-24" / "run_parameters.json"
    if not path.exists():
        skipped.append("parameters")
        return
    r = json.loads(path.read_text(encoding="utf-8"))
    phys, const, run = r["ace_physics"], r["source_constants"], r["runner_parameters"]
    link = phys["router_to_bsm_links"][0]
    rows = [
        ["Memory fidelity", f"{phys['memory_fidelity']}"], ["Memory efficiency", f"{phys['memory_efficiency']}"],
        ["Memory coherence time", f"{phys['memory_coherence_time_s']} s"],
        ["Memory cut-off ratio (cut-off / coherence)", "1 (SeQUeNCe default; not set in the file)"],
        ["BSM detector efficiencies", ", ".join(str(x) for x in phys["bsm_detector_efficiencies"])],
        ["Gate / measurement fidelity", f"{phys['gate_fidelity']} / {phys['measurement_fidelity']}"],
        ["Router-to-BSM fibre", f"{link['distance_m']} m, {link['attenuation_db_per_m']} dB/m"],
        ["Classical delay", f"distance/c + {const['classical_delay_per_hop_us']} $\\mu$s per hop + {const['classical_delay_base_us']} $\\mu$s"],
        ["Configuration file", tex(phys["config_file"])],
    ]
    table(GEN / "params_physics.tex", ["Physical parameter", "Value"], rows, "Physical parameters in force (read from the run's parameter record).", "tab:params-physics", "lp{0.5\\linewidth}")
    harness = [
        ["Pre-generation lead (request submitted this long before its window)", f"{run['pregeneration_buffer_ms']} ms"],
        ["Request reservation window", f"{run['request_duration_ms']} ms"],
        ["Empty-layer gap", f"{const['empty_layer_gap_ms']:g} ms"], ["Retry period after a physical rejection", "1 ms"],
        ["Admission grace after a release or timeout", f"{const['admission_grace_ps']:g} ps"],
        ["A ``wait'' means more than", f"{const['wait_threshold_ms']:g} ms"],
        ["Compiler reservation window", f"{run['compiler_reservation_ms']:g} ms"],
        ["Planner: delta / lookahead / coherence layers", f"{run['delta_layers']:g} / {run['dynamic_lookahead_layers']:g} / {run['coherence_time_layers']:g}"],
        ["Fidelity threshold of a request", f"{run['fidelity_threshold']}"], ["Simulation stop time", f"{run['stop_time_s']:g} s"],
        ["Scheduler", f"{r['design']['scheduler']}, admission {run['admission']}, starvation guard on"],
        ["Seeds", f"mapping {r['design']['mapping_seeds']}, physics {r['design']['physics_seeds']}"],
    ]
    table(GEN / "params_harness.tex", ["Harness constant", "Value"], harness, "Harness and scheduler constants (not physical).", "tab:params-harness", "lp{0.3\\linewidth}")


def main() -> int:
    GEN.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    heatmap_tables(skipped)
    exp2_tables(skipped)
    exp1_tables(skipped)
    cutoff_tables(skipped)
    torus_tables(skipped)
    parameter_tables(skipped)
    print("wrote", len(list(GEN.glob("*.tex"))), "generated files;", "skipped:", skipped or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
