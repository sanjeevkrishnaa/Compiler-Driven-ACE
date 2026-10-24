#!/usr/bin/env python3
"""Write docs/reports/run-times.md and docs/latex/ace_report/generated/runtimes_*.tex from the recorded timing files."""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RES = REPO / "results"
NAMES = {"ghz": "GHZ", "bv": "Bernstein-Vazirani", "bmw_quark_cardinality": "BMW/QUARK cardinality", "vqe_real_amp": "VQE real amplitudes",
         "cdkm_ripple_carry_adder": "CDKM ripple-carry adder", "graphstate": "Graph state", "draper_qft_adder": "Draper QFT adder",
         "qaoa": "QAOA", "qft": "QFT", "randomcircuit": "Random circuit"}
ORDER = list(NAMES)


def load(path):
    with open(path, newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def params(folder):
    return json.loads((RES / folder / "run_parameters.json").read_text(encoding="utf-8"))


def fmt(seconds: float) -> str:
    return f"{seconds / 60:.1f} min" if seconds >= 120 else f"{seconds:.1f} s"


def main() -> int:
    lines = ["# Run times of every experiment", "",
             "Wall-clock seconds on the development Mac (8 CPUs, Python 3.13). Recorded by the drivers (`timings.csv`, `run_parameters.json`) except where stated.",
             "An *invocation* is one process that runs one workload at one budget and policy for three physics seeds; a run is one physics seed (one third of an invocation).",
             "Times from parallel runs include contention from the other jobs, so their sum exceeds the wall clock; the serial pass has no such inflation.", ""]
    # 1. headline totals
    totals = [("Experiment 1, mesh (456 invocations, 1,368 runs)", "experiment1_ten_benchmarks_2026-10-24"),
              ("Experiment 1, torus (456 invocations, 1,368 runs)", "experiment1_torus_2026-10-24"),
              ("Sensitivity arm, ACGP Table I parameters (40 invocations, 120 runs)", "experiment1_sensitivity_acgp_table1_2026-10-24"),
              ("Serial timing pass (90 invocations, 270 runs, mapping seed 42)", "experiment1_timing_serial_2026-10-24")]
    lines += ["## Totals", "", "| Experiment | Parallel jobs | Wall clock | Sum of invocation times |", "|---|---:|---:|---:|"]
    for name, folder in totals:
        t = params(folder)["timing"]
        lines.append(f"| {name} | {t['parallel_jobs']} | {fmt(t['total_wall_clock_seconds'])} | {fmt(sum(t['per_workload_sum_of_invocation_seconds'].values()))} |")
    lines += ["", "Smaller pieces, timed separately: the heatmap regeneration 2.7 s; the endpoint-versus-relay split (Experiment 2, both counting variants) 4.3 s; "
              "mapping all 30 torus trials (ten workloads, three seeds) finished within 30 s of the launch; the offline re-routing study 190 s (mesh) and 475 s (torus) "
              "with 3 jobs; the simulation of re-routed mesh traces 1,200 s with 3 jobs while other jobs were running; the legacy baseline check about 15 min "
              "(not instrumented, so approximate).", ""]
    # 2. per-workload, parallel runs
    lines += ["## Per benchmark: sum of invocation seconds (parallel runs, contended)", "", "| Benchmark | Mesh | Torus |", "|---|---:|---:|"]
    pm = params("experiment1_ten_benchmarks_2026-10-24")["timing"]["per_workload_sum_of_invocation_seconds"]
    pt = params("experiment1_torus_2026-10-24")["timing"]["per_workload_sum_of_invocation_seconds"]
    for w in ORDER:
        lines.append(f"| {NAMES[w]} | {fmt(pm[w])} | {fmt(pt[w])} |")
    # 3. serial pass table: seconds per run (invocation / 3), by workload, policy, budget
    rows = load(RES / "experiment1_timing_serial_2026-10-24" / "timings.csv")
    cell = defaultdict(list)
    for r in rows:
        cell[(r["workload"], r["strategy"], int(r["budget"]))].append(float(r["invocation_wall_seconds"]) / 3)
    lines += ["", "## Per benchmark, one run at a time: seconds per run (serial pass, mapping seed 42)", "",
              "Each cell is the mean over the invocation's three physics seeds (invocation time divided by three).", "",
              "| Benchmark | on-demand 1 | 2 | 4 | 8 | 32 | dynamic 2 | 4 | 8 | 32 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    tex = []
    for w in ORDER:
        vals = [f"{st.fmean(cell[(w, 'on-demand', b)]):.1f}" for b in (1, 2, 4, 8, 32)] + [f"{st.fmean(cell[(w, 'dynamic', b)]):.1f}" for b in (2, 4, 8, 32)]
        lines.append(f"| {NAMES[w]} | " + " | ".join(vals) + " |")
        tex.append([NAMES[w].replace("&", r"\&")] + vals)
    # 4. earlier bare-simulation timing at 4 memories
    legacy = load(RES / "ace_scheduler_verification_2026-10-24" / "wall_time_legacy.csv")
    perq = load(RES / "ace_scheduler_verification_2026-10-24" / "wall_time_per_qubit.csv")
    bare = {(r["workload"], r["strategy"], "legacy"): float(r["wall_seconds"]) for r in legacy}
    bare.update({(r["workload"], r["strategy"], "per-qubit"): float(r["wall_seconds"]) for r in perq})
    lines += ["", "## Bare simulation at 4 memories, legacy against per-qubit scheduler (one seed, no event recorder, one at a time)", "",
              "| Benchmark | on-demand legacy | on-demand per-qubit | dynamic legacy | dynamic per-qubit |", "|---|---:|---:|---:|---:|"]
    for w in ORDER:
        lines.append(f"| {NAMES[w]} | " + " | ".join(f"{bare[(w, s, k)]:.1f} s" for s in ("on-demand", "dynamic") for k in ("legacy", "per-qubit")) + " |")
    lines += ["", "The new scheduler costs a few percent more real time on the larger traces, because it reads the reservation tables at admission. "
              "Real time has no relation to the simulated latency the experiments report."]
    (REPO / "docs" / "reports" / "run-times.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # LaTeX table for the report
    gen = REPO / "docs" / "latex" / "ace_report" / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    body = [r"\begin{table}[H]", r"\centering\small", r"\resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{%", r"\begin{tabular}{@{}lrrrrrrrrr@{}}", r"\toprule",
            r"Benchmark & \multicolumn{5}{c}{on-demand, memories} & \multicolumn{4}{c}{dynamic, memories} \\",
            r" & 1 & 2 & 4 & 8 & 32 & 2 & 4 & 8 & 32 \\", r"\midrule"]
    body += [" & ".join(r) + r" \\" for r in tex]
    body += [r"\bottomrule", r"\end{tabular}}",
             r"\caption{Seconds of real time per simulation run, one run at a time (serial pass, mapping seed 42; mean over three physics seeds).}",
             r"\label{tab:runtimes-serial}", r"\end{table}"]
    (gen / "runtimes_serial.tex").write_text("\n".join(body) + "\n", encoding="utf-8")
    tt = [("Experiment 1, mesh", "experiment1_ten_benchmarks_2026-10-24"), ("Experiment 1, torus", "experiment1_torus_2026-10-24"),
          ("Sensitivity arm", "experiment1_sensitivity_acgp_table1_2026-10-24"), ("Serial timing pass", "experiment1_timing_serial_2026-10-24")]
    body = [r"\begin{table}[H]", r"\centering\small", r"\begin{tabular}{@{}lrrr@{}}", r"\toprule", r"Experiment & Jobs & Runs & Wall clock \\", r"\midrule"]
    for name, folder in tt:
        p = params(folder)
        body.append(f"{name} & {p['timing']['parallel_jobs']} & {p['design']['runs']} & {fmt(p['timing']['total_wall_clock_seconds'])} \\\\")
    body += [r"\bottomrule", r"\end{tabular}", r"\caption{Wall-clock time of each experiment.}", r"\label{tab:runtimes-total}", r"\end{table}"]
    (gen / "runtimes_total.tex").write_text("\n".join(body) + "\n", encoding="utf-8")
    print("wrote docs/reports/run-times.md and the LaTeX tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
