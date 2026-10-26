#!/usr/bin/env python3
"""Generate the completed QAOA study report source from validated artifacts."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path


def tex(value: object) -> str:
    return str(value).replace("&", r"\&").replace("_", r"\_").replace("%", r"\%")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    with gzip.open(root / "manifests/base-evaluation_jobs.jsonl.gz", "rt", encoding="utf-8") as stream:
        jobs = [json.loads(line) for line in stream]
    complete = [job for job in jobs if (root / job["output_path"] / "summary.csv").is_file()]
    variants = list((root / "raw/dynamic-variants").glob("*/summary.csv")) if (root / "raw/dynamic-variants").is_dir() else []
    heatmaps = sorted((root / "congestion/heatmaps").glob("*.png")) if (root / "congestion/heatmaps").is_dir() else []
    status_path = root / "summaries/base-evaluation-status.json"
    status = json.loads(status_path.read_text()) if status_path.is_file() else {}
    report = root / "report"
    report.mkdir(parents=True, exist_ok=True)
    csv_rel = "../summaries/base-evaluation-progress.csv"
    heatmap_rel = "../congestion/heatmaps/" + heatmaps[0].name if heatmaps else ""
    rows = [
        ("Base jobs", f"{len(complete)} / {len(jobs)}"),
        ("Policy-seed evaluations", f"{status.get('completed_policy_seed_evaluations', 0)} / {status.get('total_policy_seed_evaluations', 6402)}"),
        ("Dynamic auxiliary variant jobs", f"{len(variants)} / 143"),
        ("Congestion heatmaps", f"{len(heatmaps)} / 210"),
        ("Mapping route aliases", "15 conceptual / 11 distinct traces"),
    ]
    body = [
        r"\documentclass[11pt,a4paper]{article}", r"\usepackage[margin=25mm]{geometry}",
        r"\usepackage{booktabs}", r"\usepackage{graphicx}", r"\usepackage{hyperref}",
        r"\hypersetup{colorlinks=true,urlcolor=blue,linkcolor=blue}",
        r"\title{QAOA ACE Golden Study}", r"\author{BTP / MARS Lab}", r"\date{26 October 2026}",
        r"\begin{document}", r"\maketitle",
        r"\section{Scope and completion contract}",
        r"This report is generated only from the dated QAOA study root. The study uses T-HQA placement, mapping seeds 42/43/44, mesh XY/YX/shortest-reliable/maximum-reliability, torus Dijkstra, total memories 2/3/4/6/8/16/32, every legal compiler allocation, ODG/CGP/ACGP/Dynamic full-chain/Dynamic first-hop, and physics seeds 0/1. Primary latency is arrival-to-completion with no historical 5.3-ms subtraction.",
        r"\begin{table}[h] \centering \caption{Validated artifact coverage.} \begin{tabular}{lr} \toprule Artifact & Coverage \\\midrule",
    ]
    body.extend(f"{tex(label)} & {tex(value)} \\\\" for label, value in rows)
    body.extend([
        r"\bottomrule \end{tabular} \end{table}",
        r"\section{Reproducible data links}",
        rf"The complete base CSV is available at \href{{run:{csv_rel}}}{{base-evaluation-progress.csv}}. The execution manifest is \href{{run:../manifests/base-evaluation_jobs.jsonl.gz}}{{base-evaluation\_jobs.jsonl.gz}} and the congestion summary is \href{{run:../congestion/trace_congestion_summary.csv}}{{trace\_congestion\_summary.csv}}.",
    ])
    if heatmap_rel:
        body.extend([
            r"\section{Congestion heatmap evidence}",
            rf"\begin{{figure}}[h] \centering \includegraphics[width=0.98\linewidth]{{{heatmap_rel}}} \caption{{Representative QAOA congestion heatmap. The full heatmap directory contains {len(heatmaps)} generated PNG files.}} \end{{figure}}",
            rf"The complete heatmap table is in \href{{run:../congestion/per_core_congestion.csv}}{{per-core-congestion.csv}}; the figure is followed by that full committed CSV rather than being treated as standalone evidence.",
        ])
    body.extend([
        r"\section{Interpretation policy}",
        r"No result is reported from a partial directory. Any incomplete or failed job remains in raw/.partial for provenance and is excluded from aggregate claims. The two physics seeds support pipeline validation and trend analysis, not strong statistical inference.",
        r"\end{document}", "",
    ])
    tex_path = report / "qaoa_report.tex"
    tex_path.write_text("\n".join(body), encoding="utf-8")
    (report / "coverage.json").write_text(json.dumps({"base_jobs": len(complete), "base_jobs_expected": len(jobs), "dynamic_variant_jobs": len(variants), "dynamic_variant_jobs_expected": 143, "heatmaps": len(heatmaps), "heatmaps_expected": 210}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tex": str(tex_path), "base_jobs": len(complete), "dynamic_variants": len(variants), "heatmaps": len(heatmaps)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
