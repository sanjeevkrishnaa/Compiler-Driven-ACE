#!/usr/bin/env python3
"""Tabulate the diagnostic JSONs (tools/diagnostics/run_diagnostics.py) into one CSV and a markdown digest.

Columns: latency and its split (admission wait, generation), delivered fidelity, hit rate, wait of hit vs fallback
requests, how long a ready pair sat in memory, the share of admission checks that found no free memory and which kind of booking
held the blocked cards, how long each kind of booking is held, and pairs generated but never used (waste).

    python tools/diagnostics/summarise.py results/<dir>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

POLICY = {"on-demand": "ODG", "dynamic": "Dynamic", "continuous": "CGP", "adaptive-continuous": "ACGP"}


def row(path: Path) -> dict:
    data = json.loads(path.read_text())
    job, d = data["job"], data["per_seed"][0]
    bookings = d.get("bookings") or {}
    cards = job["memories"]
    block = d["admission_blocking"]
    kinds = block["blocked_cards_by_kind_share"]
    wait = d["wait_split_ms"]
    hit, fall = d["hit_vs_fallback"]["hit"], d["hit_vs_fallback"]["fallback"]
    compiler, stats = d.get("compiler") or {}, d["stats"]
    generated = compiler.get("generated_compiler_pairs", stats.get("protocol_generated_pairs"))
    unused = (compiler.get("expired_compiler_pairs", 0) + compiler.get("remaining_compiler_pairs", 0)) if compiler \
        else stats.get("protocol_unused_pairs")
    return {
        "group": job["group"], "name": job["name"], "workload": job["workload"], "policy": POLICY[job["policy"]],
        "memories": cards, "compiler_cap": 0 if job["policy"] == "on-demand" else job["cap"],
        "override": ";".join(f"{k}={v}" for k, v in job["override"].items()),
        "latency_ms": d["average_request_latency_ms"], "wait_ms": stats["avg_retry_wait_time_ms"],
        "generation_ms": stats["avg_entanglement_generation_time_ms"],
        "fidelity": d["average_delivered_epr_fidelity"],
        "hit_rate": compiler.get("intended_request_hit_rate"),
        "hit_wait_ms": hit["mean_wait_ms"], "fallback_wait_ms": fall["mean_wait_ms"],
        "pair_hold_mean_ms": d["pair_ready_hold_ms"]["mean"],
        "wait_before_admission_ms": wait["before_admission_mean"], "wait_after_admission_ms": wait["after_admission_mean"],
        "dependency_wait_ms": wait["dependency_wait_mean"],
        "admission_checks": block["admission_checks"],
        "checks_blocked_share": block["checks_that_found_no_free_memory"] / block["admission_checks"] if block["admission_checks"] else None,
        "blocked_by_compiler_share": kinds.get("compiler", 0.0), "blocked_by_autonomous_share": kinds.get("autonomous", 0.0),
        "blocked_by_application_share": kinds.get("application", 0.0),
        "application_hold_ms": (bookings.get("application") or {}).get("mean_hold_ms"),
        "prebooking_hold_ms": (bookings.get("compiler") or bookings.get("autonomous") or {}).get("mean_hold_ms"),
        "rejection_events": d["protocol_rejections"]["events"],
        "pairs_generated": generated, "pairs_unused": unused,
        "waste_percent": (100 * unused / generated) if generated else None,
        "makespan_ms": stats["end_to_end_latency_ms"],
    }


def main(folder: Path) -> None:
    rows = sorted((row(p) for p in folder.glob("*.json")), key=lambda r: (r["group"], r["workload"], r["memories"], r["name"]))
    with (folder / "diagnostics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {folder / 'diagnostics.csv'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
