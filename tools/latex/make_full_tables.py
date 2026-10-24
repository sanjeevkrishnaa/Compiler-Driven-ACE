#!/usr/bin/env python3
"""Complete data tables, per-workload profiles, repository map and commit timeline for the master report.

Everything is generated from the committed result files and from git; the repository map checks that every file it links to exists.

    python tools/latex/make_full_tables.py
"""
from __future__ import annotations

import csv
import json
import shutil
import statistics as st
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "latex" / "ace_report"
GEN, FIG = OUT / "generated", OUT / "figures"
RES = REPO / "results"
BASE = "https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE"
BRANCH = "codex/ace-scheduler-correctness"
sys.path.insert(0, str(REPO / "tools" / "latex"))
sys.path.insert(0, str(REPO / "tools" / "experiment1"))
sys.path.insert(0, str(REPO / "tools" / "experiment2"))
from make_tables import NAMES, ORDER, BUDGETS, table, figure, load, tex    # noqa: E402
import analyze as A                                                       # noqa: E402

MAIN = RES / "experiment1_ten_benchmarks_2026-10-24"
E2 = RES / "experiment2_own_vs_relay_2026-10-24"


def longtable(path: Path, header: list[str], rows: list[list[str]], caption: str, label: str, colspec: str) -> None:
    lines = [r"{\scriptsize\setlength{\tabcolsep}{2.4pt}", rf"\begin{{longtable}}{{@{{}}{colspec}@{{}}}}", rf"\caption{{{caption}}}\label{{{label}}}\\", r"\toprule",
             " & ".join(header) + r" \\", r"\midrule", r"\endfirsthead", r"\toprule", " & ".join(header) + r" \\", r"\midrule", r"\endhead",
             r"\bottomrule", r"\endfoot"]
    lines += [" & ".join(r) + r" \\" for r in rows]
    lines += [r"\end{longtable}}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def exp1_full() -> None:
    rows = A.load(MAIN / "results.csv")
    g = A.cells(rows)
    out = []
    for w in ORDER:
        for policy in ("on-demand", "dynamic"):
            for b in BUDGETS + ([64] if w == "qft" else []):
                k = (w, policy, b)
                if k not in g:
                    continue
                lat, fid, mk, wt, rt = (A.stats(g[k].get(m, [])) for m in ("latency_ms", "fidelity", "makespan_ms", "waited_fraction", "retries"))
                out.append([NAMES[w], policy, f"{b}" + ("$^*$" if b > 4 else ""), f"{lat['mean']:.3f}", f"{lat['sd']:.3f}", f"{lat['min']:.3f}--{lat['max']:.3f}",
                            f"{fid['mean']:.4f}", f"{mk['mean'] / 1000:.2f}", f"{wt['mean']:.3f}", f"{rt['mean']:.2f}"])
    longtable(GEN / "exp1_full.tex", ["Workload", "Policy", "Mem.", "Latency ms", "sd", "min--max", "Fidelity", "Makespan s", "Waited", "Retries"], out,
              "Experiment 1, every cell: nine runs (three mapping $\\times$ three physics seeds). Latency in ms (mean, standard deviation, minimum--maximum); makespan in seconds; "
              "Waited is the fraction of requests that waited more than a microsecond; Retries the mean number of physical rejections per run. $^*$ counterfactual budget.",
              "tab:exp1-full", "llrrrrrrrr")


def exp1_derived() -> None:
    rows = A.load(MAIN / "results.csv")
    g = A.cells(rows)
    struct = json.loads((MAIN / "structural_overload.json").read_text(encoding="utf-8"))
    mean = lambda k, m: st.fmean(g[k][m])
    # penalty relative to 32 memories
    body = []
    for w in ORDER:
        base = mean((w, "on-demand", 32), "latency_ms")
        body.append([NAMES[w]] + [f"{100 * (mean((w, 'on-demand', b), 'latency_ms') / base - 1):+.0f}\\%" for b in (1, 2, 3, 4, 6, 8)])
    table(GEN / "exp1_penalty.tex", ["Workload", "1", "2", "3", "4", "6$^*$", "8$^*$"], body,
          "On-demand latency relative to the same workload with 32 memories (saturated), by memories per core. $^*$ counterfactual.", "tab:exp1-penalty")
    # structural overload next to the physical penalty
    body = []
    for w in ORDER:
        base = mean((w, "on-demand", 32), "latency_ms")
        body.append([NAMES[w]] + [f"{struct[w][str(b)]:.0f}\\% / {100 * (mean((w, 'on-demand', b), 'latency_ms') / base - 1):+.0f}\\%" for b in (1, 2, 3, 4)])
    table(GEN / "exp1_struct_vs_penalty.tex", ["Workload", "1 memory", "2", "3", "4"], body,
          "Structural overload of the traces (\\% of active layers with any core above capacity) / simulated on-demand latency penalty against 32 memories, at the same capacity.",
          "tab:exp1-struct")
    # makespan
    body = []
    for w in ORDER:
        body.append([NAMES[w]] + [f"{mean((w, 'on-demand', b), 'makespan_ms') / 1000:.2f}" for b in (1, 2, 4, 8, 32)]
                    + [f"{mean((w, 'dynamic', b), 'makespan_ms') / 1000:.2f}" for b in (2, 4, 8, 32)])
    table(GEN / "exp1_makespan.tex", ["Workload", "OD 1", "OD 2", "OD 4", "OD 8", "OD 32", "Dyn 2", "Dyn 4", "Dyn 8", "Dyn 32"], body,
          "Makespan (simulated seconds of the whole circuit), on-demand (OD) and dynamic (Dyn), by memories per core. Mostly the fixed 5.3\\,ms lead and 5\\,ms empty-layer gap.", "tab:exp1-makespan", "lrrrrrrrrr")
    # variation across mapping seeds at budgets 2 and 4 (on-demand)
    by = defaultdict(list)
    for r in rows:
        if r["strategy"] == "on-demand":
            by[(r["workload"], int(r["total_memories"]), r["mapping_seed"])].append(float(r["average_eligible_latency_ms"]))
    body = []
    for w in ORDER:
        body.append([NAMES[w]] + [f"{st.fmean(by[(w, b, s)]):.2f}" for b in (2, 4) for s in ("42", "43", "44")])
    table(GEN / "exp1_by_mapping_seed.tex", ["Workload", "2 mem. seed 42", "43", "44", "4 mem. seed 42", "43", "44"], body,
          "On-demand latency (ms) by mapping seed (mean over the three physics seeds): the mapping, not the physics, is the larger source of spread.", "tab:exp1-mapseed")


def profiles() -> None:
    rows = A.load(MAIN / "results.csv")
    g = A.cells(rows)
    struct = json.loads((MAIN / "structural_overload.json").read_text(encoding="utf-8"))
    mean = lambda k, m: st.fmean(g[k][m])
    parts = []
    for w in ORDER:
        base = mean((w, "on-demand", 32), "latency_ms")
        od = {b: mean((w, "on-demand", b), "latency_ms") for b in BUDGETS}
        dy = {b: mean((w, "dynamic", b), "latency_ms") for b in BUDGETS[1:]}
        wait4 = mean((w, "on-demand", 4), "waited_fraction")
        settle = next((b for b in BUDGETS if od[b] <= base * 1.05), None)
        cross = next((b for b in BUDGETS[1:] if dy[b] < od[b]), None)
        fid = {b: mean((w, "dynamic", b), "fidelity") for b in BUDGETS[1:]}
        text = (f"\\subsection*{{{NAMES[w]}}}\n"
                f"Structural overload at four slots: {struct[w]['4']:.1f}\\% of active layers (one slot: {struct[w]['1']:.0f}\\%). "
                f"On-demand latency is {od[1]:.2f}\\,ms with one memory, {od[2]:.2f} with two, {od[4]:.2f} with four and {od[32]:.2f} with 32; "
                f"it is within 5\\% of the saturated value from {settle} memor{'y' if settle == 1 else 'ies'}. "
                f"At four memories {100 * wait4:.1f}\\% of requests waited. "
                f"Dynamic pre-generation takes {dy[2]:.2f}\\,ms with two memories, {dy[4]:.2f} with four and {dy[32]:.2f} with 32, and first beats on-demand at "
                f"{cross if cross else 'no tested budget'} memories; its delivered fidelity is {fid[2]:.4f} at two memories and {fid[32]:.4f} at 32 (on-demand: 0.9498).\n")
        parts.append(text)
    (GEN / "exp1_profiles.tex").write_text("\n".join(parts), encoding="utf-8")


def exp2_tables() -> None:
    import split_congestion as S
    # peaks and hottest core (hop, capacity 4)
    rows = {}
    for r in load(E2 / "capacity_4" / "split_hop.csv"):
        rows.setdefault(r["workload"], {})[int(r["core"])] = r
    body = []
    for w in ORDER:
        cores = rows[w]
        top = max(cores, key=lambda c: float(cores[c]["mean_overloaded_percent"]))
        t = cores[top]
        f = lambda x: "--" if x == "" else f"{100 * float(x):.0f}\\%"
        if float(t["mean_overloaded_percent"]) == 0:
            body.append([NAMES[w], "none", "0.0", "0.0", "0.0", "--", "--"])
        else:
            body.append([NAMES[w], f"C{top}", f"{float(t['mean_overloaded_percent']):.1f}", f"{float(t['mean_own_percent']):.1f}",
                         f"{float(t['mean_relay_only_percent']):.1f}", f(t["mean_mean_relay_share_when_overloaded"]), f(t["mean_relay_share_of_excess"])])
    table(GEN / "exp2_hottest.tex", ["Workload", "Hottest core", "Overloaded \\%", "Own \\%", "Relay-only \\%", "Relay share of demand", "Relay share of excess"], body,
          "Hottest core of each workload at capacity 4 (hop counting): percentage of active layers overloaded, split into own and relay-only, and the relay share of its demand and of its excess.",
          "tab:exp2-hottest", "llrrrrr")
    # per-core own and relay-only at capacity 4 and 2 (workloads with any overload)
    for cap in (4, 2):
        data = {}
        for r in load(E2 / f"capacity_{cap}" / "split_hop.csv"):
            data.setdefault(r["workload"], {})[int(r["core"])] = r
        for field, label, name in (("mean_own_percent", "own endpoint demand", "own"), ("mean_relay_only_percent", "relay traffic only", "relay")):
            body = []
            for w in ORDER:
                if max(float(data[w][c]["mean_overloaded_percent"]) for c in range(16)) == 0:
                    continue
                body.append([NAMES[w]] + [f"{float(data[w][c][field]):.1f}" for c in range(16)])
            table(GEN / f"exp2_cores_{name}_c{cap}.tex", ["Workload"] + [f"C{c}" for c in range(16)], body,
                  f"Per core, \\% of active layers overloaded by {label}, capacity {cap}, hop counting (mean of three mapping seeds). Workloads with no overload are omitted.",
                  f"tab:exp2-cores-{name}-{cap}", "l" + "r" * 16)
    for cap in (1, 2, 3, 4):
        for variant in ("hop", "route"):
            src = E2 / f"capacity_{cap}" / f"split_{variant}.png"
            shutil.copy(src, FIG / f"exp2_c{cap}_{variant}.png")
    # peaks
    import tempfile, zipfile
    from hotspot_analysis import read_trace
    body = []
    with tempfile.TemporaryDirectory() as t, zipfile.ZipFile(S.ARCHIVE) as z:
        for w in ORDER:
            pd = pe = pr = 0
            for s in S.SEEDS:
                tr = read_trace(Path(z.extract(f"{S.PREFIX}/{w}/seed_{s}/requests.txt", t)), 4, 4)
                by = defaultdict(list)
                for h in tr.hops:
                    by[h.layer].append(h)
                for hops in by.values():
                    for _, (d, e) in S.layer_demand(hops, "hop").items():
                        pd, pe = max(pd, d), max(pe, e)
                    for _, (d, e) in S.layer_demand(hops, "route").items():
                        pr = max(pr, d)
            body.append([NAMES[w], str(pd), str(pe), str(pr)])
    table(GEN / "exp2_peaks.tex", ["Workload", "Peak demand $D$", "Peak endpoint demand $D_{\\mathrm{end}}$", "Peak routes through one core"], body,
          "Peak demand at one core in one layer, over all mapping seeds: how close endpoint demand comes to the capacity.", "tab:exp2-peaks")


def repo_map() -> None:
    def link(path: str, text: str | None = None) -> str:
        kind = "tree" if (REPO / path).is_dir() else "blob"
        assert (REPO / path).exists(), f"repository map links a missing path: {path}"
        return rf"\href{{{BASE}/{kind}/{BRANCH}/{path}}}{{\nolinkurl{{{text or path}}}}}"
    groups = [
        ("Reports and plans", [
            ("docs/reports/ace-correctness-audit.md", "what was wrong in the legacy simulator (F1--F10)"),
            ("docs/reports/ace-scheduler-verification.md", "verification of the corrected scheduler; wall-clock times"),
            ("docs/reports/ace-physical-parameters.md", "every physical parameter, its source, the open decision and the question for the guide"),
            ("docs/reports/ace-budget-rerun.md", "the 378-run budget study rerun (Gate 6)"),
            ("docs/reports/experiment1-ten-benchmarks.md", "Experiment 1 report (generated from the data)"),
            ("docs/reports/experiment2-own-vs-relay.md", "Experiment 2 report"),
            ("docs/reports/memory-cutoff-study.md", "memory cut-off study"),
            ("docs/reports/offline-routing-research.md", "can offline routing reduce congestion?"),
            ("docs/reports/run-times.md", "run times of every experiment"),
            ("docs/plans/ace-correctness-and-congestion-program.md", "the day plan and gates"),
            ("docs/plans/ace-request-scheduler-design.md", "scheduler design and reasoning"),
            ("docs/plans/handoff-2026-10-24.md", "state, open decisions, pitfalls"),
        ]),
        ("ACE source changed or added", [
            ("request_scheduler.py", "the per-qubit request manager with event-driven admission"),
            ("reservation.py", "request identity in reservations; release observer; event hooks"),
            ("parallel_core.py", "scheduler selection (legacy or per-qubit)"),
            ("execution_events.py", "typed execution events and stable reservation serials"),
            ("invariants.py", "the invariant checker (window-aware)"),
            ("latency_metrics.py", "the common latency definition"),
            ("compiler_trace.py", "topology-aware trace validation, torus guard"),
            ("run_trace_comparison.py", "the runner: --scheduler, --topology, new columns"),
        ]),
        ("Tools", [
            ("tools/ace_correctness", "baseline, audit, harness and audit matrix"),
            ("tools/experiment1", "Experiment 1 driver, analysis, report and unattended finisher"),
            ("tools/experiment2", "endpoint-versus-relay split"),
            ("tools/heatmap", "heatmap regeneration from raw traces"),
            ("tools/ace_budget_rerun", "parameterised budget sweep driver"),
            ("tools/routing_research", "offline re-routing: optimiser, study, simulation"),
            ("tools/torus", "torus config generator and runner"),
            ("tools/cutoff_study", "cut-off mechanism study"),
            ("tools/timing", "run-times report"),
            ("tools/latex", "generators for this report"),
            ("tools/congestion_study/run_study.py", "mapping study script (--topology torus, --mapping-only)"),
        ]),
        ("Results and data", [
            ("results/ace_correctness_baseline_2026-10-24", "the 164-row legacy baseline"),
            ("results/ace_scheduler_verification_2026-10-24", "verification matrices and wall times"),
            ("results/ace_budget_rerun_2026-10-24", "budget study rerun, both schedulers"),
            ("results/heatmap_regenerated_2026-10-24", "regenerated heatmap, its README and CSV"),
            ("results/experiment2_own_vs_relay_2026-10-24", "Experiment 2 data and figures, capacities 1--4"),
            ("results/experiment1_ten_benchmarks_2026-10-24", "Experiment 1 (mesh): results.csv, controls, figures, parameters, timings"),
            ("results/experiment1_sensitivity_acgp_table1_2026-10-24", "sensitivity arm"),
            ("results/experiment1_timing_serial_2026-10-24", "quiet serial timing pass"),
            ("results/experiment1_torus_2026-10-24", "Experiment 1 on the torus"),
            ("results/torus_traces_2026-10-24", "mapped torus traces"),
            ("results/mesh_vs_torus_2026-10-24", "mesh-versus-torus table"),
            ("results/offline_routing_2026-10-24", "offline routing data and re-routed traces"),
            ("results/cutoff_study_2026-10-24", "cut-off study data"),
            ("results/congestion/mqt_ten_workload_congestion_results.zip", "the archived mapped traces (ten workloads, seeds 42--44)"),
            ("mapper", "the vendored HQA mapper with provenance"),
        ]),
        ("This report", [("docs/latex/ace_report", "LaTeX source of this report"), ("docs/latex/ace_report/ace_report.pdf", "the compiled report")]),
    ]
    lines = [r"{\small"]
    for title, items in groups:
        lines += [rf"\subsection*{{{title}}}", r"\begin{longtable}{@{}p{0.60\linewidth}p{0.36\linewidth}@{}}"]
        for path, what in items:
            lines.append(link(path) + " & " + tex(what).replace("--", "--") + r" \\")
        lines.append(r"\end{longtable}")
    lines.append(r"}")
    (GEN / "repo_map.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def timeline() -> None:
    log = subprocess.run(["git", "log", "--reverse", "--format=%h%x09%ad%x09%s", "--date=format:%H:%M", "14cfdd2..HEAD"], cwd=REPO, capture_output=True, text=True).stdout
    rows = []
    for line in log.strip().splitlines():
        h, when, subject = line.split("\t", 2)
        heading, _, rest = subject.partition("] - ")
        rows.append([rf"\href{{{BASE}/commit/{h}}}{{\texttt{{{h}}}}}", tex(heading.lstrip('[')), tex(rest)])
    longtable(GEN / "timeline.tex", ["Commit", "Area", "What"], rows,
              "Every commit of the branch since the starting point (\\texttt{14cfdd2}), in order. Each hash links to the commit on GitHub.", "tab:timeline", "lp{0.12\\linewidth}p{0.68\\linewidth}")


def main() -> int:
    GEN.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    exp1_full()
    exp1_derived()
    profiles()
    exp2_tables()
    repo_map()
    timeline()
    print("wrote", len(list(GEN.glob("*.tex"))), "generated files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
