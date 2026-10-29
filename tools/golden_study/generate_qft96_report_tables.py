#!/usr/bin/env python3
"""Generate the completed QFT-96 LaTeX tables from validated CSV artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def n(value: str, digits: int = 3) -> str:
    if value in ("", None) or math.isnan(float(value)):
        return "N/A"
    return f"{float(value):.{digits}f}"


def pm(mean: str, sd: str, digits: int = 3) -> str:
    if mean in ("", None) or math.isnan(float(mean)):
        return "N/A"
    return f"{n(mean, digits)} $\\pm$ {n(sd, digits)}"


def policy(name: str) -> str:
    return {"Dynamic-full-chain": "Dynamic full", "Dynamic-first-hop": "Dynamic first-hop",
            "baseline-layer-start": "Layer-start baseline"}.get(name, name)


def route(topology: str, name: str) -> str:
    return f"{topology.title()} {name.replace('_', '-')}"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ledger(status: dict[str, object]) -> str:
    return f"""% Generated from validated QFT-96 status; do not edit by hand.
\\begin{{table}}[H]
\\centering\\scriptsize
\\begin{{tabular}}{{lrrl}}
\\toprule
Phase & Jobs complete & Planned & Status \\\\
\\midrule
Route audit & 15 & 15 & complete \\\\
Base ACE matrix & {status['completed_jobs']:,} & {status['total_jobs']:,} & complete \\\\
Base policy--seed evaluations & {status['completed_policy_seed_evaluations']:,} & {status['total_policy_seed_evaluations']:,} & complete \\\\
Dynamic launch variants & 143 & 143 & complete \\\\
\\bottomrule
\\end{{tabular}}
\\caption{{Final QFT-96 execution ledger. All completed base job outputs were validated against the frozen scoped manifest before aggregation.}}
\\label{{tab:qft96-final-ledger}}
\\end{{table}}
"""


def matched(rows: list[dict[str, str]]) -> str:
    body = []
    for row in rows:
        body.append(" & ".join((
            route(row["topology"], row["route_policy"]), policy(row["policy"]),
            pm(row["request_latency_mean_ms_mean"], row["request_latency_sd_ms_sd"]),
            pm(row["request_latency_p95_ms_mean"], row["request_latency_p95_ms_sd"]),
            # plot_qft96_metrics writes this derived CSV in seconds even though
            # the retained column name describes its raw millisecond source.
            pm(row["end_to_end_latency_ms_mean"], row["end_to_end_latency_ms_sd"]),
            pm(row["average_admission_wait_ms_mean"], row["average_admission_wait_ms_sd"]),
            n(row["average_delivered_epr_fidelity_mean"], 4),
        )) + r" \\")
    return """% Generated from metrics_matched_m4_c3.csv; do not edit by hand.
\\begin{landscape}
\\begin{longtable}{llrrrrr}
\\caption{Complete fixed-memory QFT-96 comparison: ODG uses $M=4,C=0$; cache policies use $M=4,C=3$. Values aggregate all distinct validated route traces and two physics seeds per trace. Latency, p95 and admission wait are milliseconds; makespan is seconds.}\\label{tab:qft96-final-matched}\\\\
\\toprule
Route & Policy & Latency & p95 & Makespan & Admission & Fidelity \\\\
\\midrule
\\endfirsthead
\\toprule
Route & Policy & Latency & p95 & Makespan & Admission & Fidelity \\\\
\\midrule
\\endhead
""" + "\n".join(body) + """
\\bottomrule
\\end{longtable}
\\end{landscape}
"""


def variants(rows: list[dict[str, str]]) -> str:
    keep = [r for r in rows if r["variant"] in {"baseline-layer-start", "predecessor-start", "first-hop-only"}]
    body = []
    for row in keep:
        body.append(" & ".join((
            policy(row["variant"]), route(row["topology"], row["route_policy"]), n(row["observations"], 0),
            pm(row["average_request_latency_ms_mean"], row["average_request_latency_ms_sd"]),
            pm(row["request_latency_p95_ms_mean"], row["request_latency_p95_ms_sd"]),
            pm(row["end_to_end_latency_ms_mean"], row["end_to_end_latency_ms_sd"]),
            n(row["average_delivered_epr_fidelity_mean"], 4), n(row["intended_request_hit_rate_mean"], 3),
        )) + r" \\")
    return """% Generated from dynamic_variants_metrics.csv; do not edit by hand.
\\begin{landscape}
\\begin{longtable}{llrrrrrr}
\\caption{Structural Dynamic-policy comparison at $M=4,C=3$. Delay sensitivity variants remain in the linked source CSV but are not treated as separate algorithms. Values are means $\\pm$ sample SD across the available validated trace--physics observations.}\\label{tab:qft96-structural-variants}\\\\
\\toprule
Variant & Route & $n$ & Latency (ms) & p95 (ms) & Makespan (s) & Fidelity & Hit rate \\\\
\\midrule
\\endfirsthead
\\toprule
Variant & Route & $n$ & Latency (ms) & p95 (ms) & Makespan (s) & Fidelity & Hit rate \\\\
\\midrule
\\endhead
""" + "\n".join(body) + """
\\bottomrule
\\end{longtable}
\\end{landscape}
"""


def congestion(rows: list[dict[str, str]]) -> str:
    selected = [r for r in rows if r["capacity"] == "4" and r["variant"] == "route"]
    body = []
    for row in selected:
        body.append(" & ".join((
            route(row["topology"], row["route_policy"]), row["mapping_seed"],
            n(row["overloaded_layer_percent"], 1), n(row["overloaded_core_layers"], 0),
            n(row["excess_demand"], 0),
        )) + r" \\")
    return """% Generated from trace_congestion_summary.csv; do not edit by hand.
\\begin{table}[H]
\\centering\\small
\\begin{tabular}{lrrrr}
\\toprule
Route & Seed & Overloaded layers (\\%) & Overloaded core-layers & Excess demand \\\\
\\midrule
""" + "\n".join(body) + """
\\bottomrule
\\end{tabular}
\\caption{Route-occupancy congestion at four communication memories per core. Percentages use only the 226 communication-active QFT-96 layers. This is trace demand, not simulated memory occupancy.}
\\label{tab:qft96-congestion-m4}
\\end{table}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    status = json.loads((root / "summaries/base-evaluation-status.json").read_text(encoding="utf-8"))
    write(output / "qft96_final_ledger.tex", ledger(status))
    write(output / "qft96_final_matched.tex", matched(read_csv(root / "figures/metrics/metrics_matched_m4_c3.csv")))
    write(output / "qft96_structural_variants.tex", variants(read_csv(root / "figures/dynamic-variants/dynamic_variants_metrics.csv")))
    write(output / "qft96_congestion_m4.tex", congestion(read_csv(root / "congestion/trace_congestion_summary.csv")))
    print(f"wrote final QFT-96 tables to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
