#!/usr/bin/env python3
"""Audit the committed MQT workloads over strategies, memory budgets and seeds, in parallel.

Every cell is one ``audit_trace`` run (the runner's own compiler spec, an event recorder, and the
invariant checker).  Output is one CSV row per cell, so a regression in completion, invariants,
rejections or waiting shows up as a changed row.

    python tools/ace_correctness/audit_matrix.py --workloads ghz bv --strategies on-demand dynamic \
        --memories 2 4 --seeds 0 1 --scheduler per-qubit --output out.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_trace import COMPILER_STRATEGIES, audit_trace      # noqa: E402

ARCHIVE = REPO_ROOT / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
PREFIX = "mqt_ten_workload_study"
WORKLOADS = ("ghz", "bv", "graphstate", "vqe_real_amp", "cdkm_ripple_carry_adder",
             "bmw_quark_cardinality", "draper_qft_adder", "qft", "qaoa", "randomcircuit")
COLUMNS = ["workload", "strategy", "memories", "seed", "scheduler", "admission", "requested", "completed",
           "violations", "violation_kinds", "makespan_ms", "retries", "max_retries_one_request",
           "max_admission_wait_ms", "wall_seconds"]


def extract(workload: str, directory: Path) -> Path:
    with zipfile.ZipFile(ARCHIVE) as archive:
        return Path(archive.extract(f"{PREFIX}/{workload}/seed_42/requests.txt", directory))


def run_cell(cell: dict) -> dict:
    options = {"admission": cell["admission"]} if cell["admission"] else {}
    audit = audit_trace(Path(cell["trace"]), cell["strategy"], seed=cell["seed"], total_memories=cell["memories"],
                        compiler_memories=min(3, cell["memories"] - 1) if cell["memories"] > 1 else 0,
                        generation_capacity=min(3, cell["memories"]),
                        scheduler=cell["scheduler"], scheduler_options=options or None,
                        record=not cell.get("time_only", False))
    kinds = sorted({v.invariant for v in audit.violations})
    return {"workload": cell["workload"], "strategy": cell["strategy"], "memories": cell["memories"],
            "seed": cell["seed"], "scheduler": cell["scheduler"], "admission": cell["admission"] or "-",
            "requested": audit.requested, "completed": audit.completed, "violations": len(audit.violations),
            "violation_kinds": "|".join(kinds), "makespan_ms": f"{audit.makespan_ms:.6f}",
            "retries": audit.total_retries, "max_retries_one_request": audit.max_retries_one_request,
            "max_admission_wait_ms": f"{audit.max_admission_wait_ms:.6f}",
            "wall_seconds": f"{audit.wall_seconds:.3f}"}


def build_cells(workloads, strategies, memories, seeds, scheduler, admission, directory: Path) -> list[dict]:
    traces = {w: extract(w, directory) for w in workloads}
    return [{"workload": w, "trace": str(traces[w]), "strategy": st, "memories": m, "seed": seed,
             "scheduler": scheduler, "admission": admission}
            for w in workloads for st in strategies for m in memories for seed in seeds]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=WORKLOADS)
    parser.add_argument("--strategies", nargs="+", default=["on-demand"], choices=COMPILER_STRATEGIES)
    parser.add_argument("--memories", nargs="+", type=int, default=[4])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0])
    parser.add_argument("--scheduler", choices=("legacy", "per-qubit"), default="per-qubit")
    parser.add_argument("--admission", choices=("poll", "event"), default=None)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--time-only", action="store_true",
                        help="time the bare simulation: no event recorder, no invariant check, one run at a time")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="ace-matrix-") as tmp:
        cells = build_cells(args.workloads, args.strategies, args.memories, args.seeds,
                            args.scheduler, args.admission, Path(tmp))
        # Largest traces first so the pool does not end waiting on one long cell.
        for cell in cells:
            cell["time_only"] = args.time_only
        if args.time_only:
            args.jobs = 1
        cells.sort(key=lambda c: -WORKLOADS.index(c["workload"]) if c["workload"] in ("randomcircuit", "qaoa", "qft") else 0)
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(run_cell, cells))
    rows.sort(key=lambda r: (WORKLOADS.index(r["workload"]), r["strategy"], r["memories"], r["seed"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    bad = [r for r in rows if r["violations"] or r["completed"] != r["requested"]]
    print(f"{len(rows)} cells, {len(bad)} with a violation or an incomplete run -> {args.output}")
    for r in bad[:10]:
        print("  ", {k: r[k] for k in ("workload", "strategy", "memories", "seed", "completed", "requested", "violation_kinds")})
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
