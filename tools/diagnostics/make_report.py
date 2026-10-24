#!/usr/bin/env python3
"""Write docs/reports/dynamic-vs-odg-diagnosis.md and docs/reports/four-policy-comparison.md from the result files.

    python tools/diagnostics/make_report.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RES, DOCS = REPO / "results", REPO / "docs" / "reports"
DIAG = RES / "diagnostics_dynamic_vs_odg_2026-10-24" / "diagnostics.csv"
ORDER = ["ODG", "Dynamic", "CGP", "ACGP"]
NAMES = {"ghz": "GHZ", "bv": "Bernstein-Vazirani", "bmw_quark_cardinality": "BMW/QUARK cardinality", "vqe_real_amp": "VQE real amplitudes",
         "cdkm_ripple_carry_adder": "CDKM ripple-carry adder", "graphstate": "Graph state", "draper_qft_adder": "Draper QFT adder",
         "qaoa": "QAOA", "qft": "QFT", "randomcircuit": "Random circuit"}


def md(headers, rows) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def f(x, d=2, pct=False):
    return "-" if x is None or pd.isna(x) else f"{x:.{d}f}" + ("%" if pct else "")


def diagnosis() -> str:
    d = pd.read_csv(DIAG)
    q = d[(d.workload == "qft") & (d.mapping_seed == 42) & (d.group == "mechanism")]
    rows = []
    for m in (2, 3, 4, 6, 8, 16):
        r = [m]
        for p in ORDER:
            x = q[(q.memories == m) & (q.policy == p)].iloc[0]
            r += [f(x.latency_ms), f(x.wait_before_admission_ms + x.wait_after_rejection_ms), f(100 * x.checks_blocked_share, 1, True)]
        rows.append(r)
    t1 = md(["memories"] + [f"{p} {c}" for p in ORDER for c in ("latency ms", "wait ms", "stuck checks")], rows)
    x = q[q.policy == "Dynamic"].sort_values("memories")
    t2 = md(["memories", "served by ready pair", "their wait ms", "of them that waited", "others' wait ms", "ready pair held ms", "ordinary request holds a card ms", "stuck checks held by compiler pairs"],
            [[int(r.memories), f(100 * r.hit_rate, 1, True), f(r.hit_wait_ms), f(100 * r.hit_share_that_waited, 0, True), f(r.fallback_wait_ms),
              f(r.pair_ready_hold_ms, 1), f(r.application_hold_ms, 1), f(100 * r.blocked_by_compiler_share, 0, True)] for r in x.itertuples()])
    c = d[d.name == "qft_m4_dynamic"].iloc[0]
    t3 = md(["position in chain", "pairs used", "made before its layer started ms", "ready pair held ms", "request eligible after pair ready ms"],
            [["first hop", f(c.hop0_pairs, 0), f(c.hop0_made_before_layer_ms, 1), f(c.hop0_hold_ms, 1), f(c.hop0_request_wait_after_ready_ms, 1)],
             ["second hop", f(c.hop1_pairs, 0), f(c.hop1_made_before_layer_ms, 1), f(c.hop1_hold_ms, 1), f(c.hop1_request_wait_after_ready_ms, 1)],
             ["third hop or later", f(c.hop2plus_pairs, 0), f(c.hop2plus_made_before_layer_ms, 1), f(c.hop2plus_hold_ms, 1), f(c.hop2plus_request_wait_after_ready_ms, 1)]])
    a = d[(d.group == "ablation") | ((d.group == "mechanism") & (d.workload == "qft") & (d.memories == 4) & d.policy.isin(["Dynamic", "ODG"]))]
    a = a[(a.workload == "qft") & (a.memories == 4) & (a.mapping_seed == 42)]
    rows = []
    for r in a.sort_values(["policy", "name"]).itertuples():
        change = r.change if isinstance(r.change, str) and r.change else ("baseline" if r.name in ("qft_m4_dynamic", "qft_m4_on-demand") else f"compiler memories {int(r.compiler_cap)} of 4")
        rows.append([r.policy, change, f(r.latency_ms), f(r.wait_before_admission_ms + r.wait_after_rejection_ms), f(100 * r.hit_rate, 0, True) if pd.notna(r.hit_rate) else "-", f(r.fidelity, 4)])
    t4 = md(["policy", "change from baseline", "latency ms", "wait ms", "ready-pair hits", "fidelity"], rows)
    s = d[(d.workload == "qft") & (d.memories == 4) & d.group.isin(["mechanism", "seeds"])]
    t5 = md(["policy"] + [f"map {m} {c}" for m in (42, 43, 44) for c in ("latency", "wait")],
            [[p] + [v for m in (42, 43, 44) for v in (f(s[(s.policy == p) & (s.mapping_seed == m)].latency_ms.iloc[0]),
                                                   f(s[(s.policy == p) & (s.mapping_seed == m)].wait_before_admission_ms.iloc[0] + s[(s.policy == p) & (s.mapping_seed == m)].wait_after_rejection_ms.iloc[0]))] for p in ORDER])
    w = d[(d.memories == 4) & (d.mapping_seed == 42) & (d.group.eq("workloads") | ((d.workload == "qft") & (d.group == "mechanism")))]
    rows = []
    for wl in ("cdkm_ripple_carry_adder", "vqe_real_amp", "randomcircuit", "draper_qft_adder", "graphstate", "qaoa", "qft"):
        g = lambda p, col: w[(w.workload == wl) & (w.policy == p)][col].iloc[0]
        rows.append([NAMES[wl]] + [f(g(p, "latency_ms")) for p in ORDER] + [f(100 * g("Dynamic", "hit_rate"), 0, True), f(100 * g("Dynamic", "checks_blocked_share"), 1, True), f(100 * g("ODG", "checks_blocked_share"), 1, True)])
    t6 = md(["workload"] + [f"{p} ms" for p in ORDER] + ["dynamic hits", "dynamic stuck checks", "ODG stuck checks"], rows)
    return f"""# Why dynamic pre-generation can be slower than on-demand

Generated by `tools/diagnostics/make_report.py` from `results/diagnostics_dynamic_vs_odg_2026-10-24/diagnostics.csv`
(the full discussion, with the code references and the comparison with the old serialized scheduler, is Chapter 12 of the PDF report).

**Question.** On the corrected scheduler, dynamic compiler pre-generation is slower than on-demand generation (ODG) on QFT, QAOA, Draper
and graph state at two to four memories per core, and faster once memory is plentiful. Why?

**Answer, in one paragraph.** The extra latency is waiting for a free memory, not generation (QFT, four memories: generation 1.13 ms for ODG, 0.65 ms for dynamic;
wait 0.44 ms against 4.81 ms). Prepared pairs occupy memory cards for much longer than an ordinary request does (a ready pair waits about 24 ms before use,
an ordinary request keeps its card about 6 ms), and a request that has a ready pair still needs a free card of its own, because the pair's state is swapped into the
request's memory. The pair of a later hop in a qubit's chain is made at the start of the previous layer but its request is released only after the hop before it completes, so it waits longest.

**How it was checked.** The mechanism was read in the code: `compiler_trace.py:254` (the planner takes the layer just before the request), `request_scheduler.py:151-158`
(preparations launch when their layer activates), `request_scheduler.py:202-255` (admission needs a card with no overlapping booking),
`generation.py:265-343` (a request swaps a ready pair into its own memory, then releases the pair's memory), `adaptive_continuous.py:147-236, 404-447, 511-523`
(autonomous cycles, ACGP update, which pair a request may take), `node.py:57` (0.2 s period). It was measured with `tools/diagnostics` (admission checks
attributed to the kind of booking that held the memory cards; hold times; ablations), 70 runs, three physics seeds each. Corrections made along the way are in the PDF
report (Chapter 12 and the corrections log): the booking hold times of autonomous bookings are not reported because the event log does not release accepted autonomous reservations.

## Latency, wait and how often admission is stuck (QFT, mapping seed 42, mean of three physics seeds)
{t1}

"Stuck checks": share of admission checks that found no free memory at one of the request's two cores.

## Requests served from a ready pair still wait (dynamic)
{t2}

## Why a prepared pair waits: position in the chain (dynamic, QFT, four memories)
{t3}

## What changes the result (QFT, four memories, mapping seed 42)
{t4}

No effect: request duration (booking window), compiler reservation window, generation capacity, planner lookahead (the planner's schedule is identical for lookahead 1, 2, 4 and 8 in all 210 configurations, and no preparation is placed earlier than the layer before its request: `lookahead_check.txt`). Strong effect: the number of memories the compiler may hold.
Preparing pairs only for first hops is an experiment to isolate the cause, not a proposed policy.

## Other mapping seeds
{t5}

## Other benchmarks at four memories (mapping seed 42)
{t6}

## What is established and what is not
* Established: pre-generated pairs occupy memory cards several times as long as on-demand requests; the resulting scarcity costs more waiting than the avoided generation saves; the effect disappears when cards are not scarce; no tested simulator setting explains it but the compiler's cap does.
* Not established: that a better plan could not do better (the planner works in whole layers and ignores both the request's own card and chain order); behaviour under other physical parameters; the cause of CGP/ACGP pair ageing.
* The diagnosis is deep on QFT; the other benchmarks give the same sign in one mapping seed.

Reproduce: `python tools/diagnostics/run_diagnostics.py --output out/diag --jobs 4 && python tools/diagnostics/summarise.py out/diag`.
"""


def four_policies() -> str:
    parts = []
    for topo in ("mesh", "torus"):
        t = pd.read_csv(RES / f"experiment1_four_policies_{topo}_2026-10-24" / "four_policy_cell_means.csv")
        present = [w for w in NAMES if w in set(t.workload)]
        sections = [f"## {topo.capitalize()}"]
        for metric, title, d in (("latency_ms", "Request latency (ms)", 2), ("fidelity", "Delivered EPR fidelity", 4), ("wait_ms", "Wait for a free memory (ms)", 2),
                                 ("waste_percent", "Pairs generated and not used (%)", 1), ("used_per_request", "Readiness: pairs used per request", 3)):
            for b in (2, 4):
                pv = t[t.total_memories == b].pivot(index="workload", columns="policy", values=metric)
                polis = [p for p in ORDER if p in pv.columns and not pv[p].isna().all()]
                sections.append(f"### {title}, {topo}, {b} memories per core\n" + md(["workload"] + polis, [[NAMES[w]] + [f(pv.loc[w, p], d) for p in polis] for w in present]))
        lat = t.pivot_table(index=["workload", "total_memories"], columns="policy", values="latency_ms")
        gain = ((lat["ODG"] - lat["Dynamic"]) / lat["ODG"] * 100).unstack("total_memories")
        sections.append(f"### Latency gain of dynamic over ODG (%), {topo}; negative: dynamic is slower\n" + md(["workload"] + [str(b) for b in gain.columns if b >= 2],
                        [[NAMES[w]] + [f(gain.loc[w, b], 0) for b in gain.columns if b >= 2] for w in present]))
        parts.append("\n\n".join(sections))
    body = "\n\n".join(parts)
    return f"""# ODG, dynamic, CGP and ACGP on nine benchmarks

Generated by `tools/diagnostics/make_report.py` from `results/experiment1_four_policies_{{mesh,torus}}_2026-10-24/four_policy_cell_means.csv`
(Chapter 13 of the PDF report has the figures, the full discussion and the checks).

**Setup.** The Experiment 1 grid (memories 2, 3, 4, 6, 8, 16, 32; QFT also 64; three mapping seeds, three physics seeds, corrected scheduler, ACE's physical
parameters) on the mesh and on the torus. ODG and dynamic are the Experiment 1 runs. CGP (`continuous`) and ACGP (`adaptive-continuous`) were run with a cache cap of
memories-1 (as dynamic's compiler memories; ACE's own cap is a fixed 3) and stopped 1 ms after the last request (both opt-in runner options). The random circuit was set aside
for CGP and ACGP and is left out here. Waste = (generated - used) / generated from the protocol counters over the workload's duration; readiness = pairs used per request
(counters divided by twice the requests).

**Result.** Against CGP and ACGP, dynamic has lower latency at every modelled memory count on every benchmark, wastes no pair (they waste 34-89% on the mesh at four memories)
and has higher fidelity. Against ODG it is faster on five of nine benchmarks at four memories and on all nine from sixteen memories, slower on QFT, QAOA, Draper and graph state at two to
four, and never matches ODG's fidelity (0.950). CGP and ACGP beat ODG only on the benchmarks where ODG is at its floor. ACGP is not measurably better than CGP.

{body}

Limits: nine benchmarks; ACE's undecided physical parameters; the cache cap of memories-1 is a choice made for fairness; waste depends on workload length and is comparable only within a benchmark.
"""


def main() -> int:
    (DOCS / "dynamic-vs-odg-diagnosis.md").write_text(diagnosis(), encoding="utf-8")
    (DOCS / "four-policy-comparison.md").write_text(four_policies(), encoding="utf-8")
    print("wrote two reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
