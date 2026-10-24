#!/usr/bin/env python3
"""Tabulate the diagnostic JSONs (tools/diagnostics/run_diagnostics.py) into one CSV.

Every number is the mean over the physics seeds of the job (0, 1, 2).  Columns:
latency and its split (wait before admission, wait after a protocol rejection, generation), delivered fidelity,
hit rate (compiler pairs only), wait of requests served by a ready pair vs requests that fell back to on-demand,
the time a ready pair sat in memory before use, the share of admission checks that found no free memory and which kind
of booking held the blocked cards, pairs generated and not used by the end of the run (waste; for CGP/ACGP (generated - used) / generated from the protocol counters, for compiler pairs expired plus still unused over generated), and for compiler pairs the hold and the
wait for the request by hop position within its chain.

Hold times of autonomous (CGP/ACGP) bookings are not reported: the event log never releases an accepted autonomous
reservation, so its hold cannot be measured from bookings (see occupancy.bookings).  What CGP/ACGP bookings do to
admission is measured directly, from the booking table at each admission check.

    python tools/diagnostics/summarise.py results/<dir>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

POLICY = {"on-demand": "ODG", "dynamic": "Dynamic", "continuous": "CGP", "adaptive-continuous": "ACGP"}


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def row(path: Path) -> dict:
    data = json.loads(path.read_text())
    job, seeds = data["job"], data["per_seed"]
    avg = lambda f: mean(_safe(f, d) for d in seeds)
    block = lambda d: d["admission_blocking"]
    kind_share = lambda kind: avg(lambda d: block(d)["blocked_cards_by_kind_share"].get(kind, 0.0))
    chain = lambda hop, key: avg(lambda d: d["pair_hold_by_chain_position"][hop][key])
    generated = lambda d: (d.get("compiler") or {}).get("generated_compiler_pairs", d["stats"].get("protocol_generated_pairs"))
    unused = lambda d: ((d["compiler"]["expired_compiler_pairs"] + d["compiler"]["remaining_compiler_pairs"]) if d.get("compiler")
                        else d["stats"].get("protocol_unused_pairs"))
    return {
        "group": job["group"], "name": job["name"], "workload": job["workload"], "mapping_seed": job.get("mapping_seed", 42),
        "policy": POLICY[job["policy"]], "memories": job["memories"],
        "compiler_cap": 0 if job["policy"] == "on-demand" else job["cap"],
        "change": ";".join([f"{k}={v}" for k, v in job["override"].items()] + job.get("diag", [])),
        "physics_seeds": len(seeds),
        "latency_ms": avg(lambda d: d["average_request_latency_ms"]),
        "wait_before_admission_ms": avg(lambda d: d["wait_split_ms"]["before_admission_mean"]),
        "wait_after_rejection_ms": avg(lambda d: d["wait_split_ms"]["after_admission_mean"]),
        "generation_ms": avg(lambda d: d["stats"]["avg_entanglement_generation_time_ms"]),
        "fidelity": avg(lambda d: d["average_delivered_epr_fidelity"]),
        "hit_rate": avg(lambda d: d["compiler"]["intended_request_hit_rate"] if d.get("compiler") else None),
        "hit_wait_ms": avg(lambda d: d["hit_vs_fallback"]["hit"]["mean_wait_ms"]),
        "fallback_wait_ms": avg(lambda d: d["hit_vs_fallback"]["fallback"]["mean_wait_ms"]),
        "hit_share_that_waited": avg(lambda d: d["hit_vs_fallback"]["hit"]["share_that_waited"]),
        "pair_ready_hold_ms": avg(lambda d: d["pair_ready_hold_ms"]["mean"]),
        "dependency_wait_ms": avg(lambda d: d["wait_split_ms"]["dependency_wait_mean"]),
        "admission_checks": avg(lambda d: block(d)["admission_checks"]),
        "checks_blocked_share": avg(lambda d: block(d)["checks_that_found_no_free_memory"] / block(d)["admission_checks"]),
        "blocked_by_compiler_share": kind_share("compiler"), "blocked_by_autonomous_share": kind_share("autonomous"),
        "blocked_by_application_share": kind_share("application"),
        "blocking_window_ms": avg(lambda d: next(iter(v for k, v in block(d)["blocking_window_ms_mean"].items() if k != "application"), None)),
        "blocking_started_ms_before_check": avg(lambda d: -next(iter(v for k, v in block(d)["blocking_window_start_offset_ms_mean"].items() if k != "application"), None)),
        "application_hold_ms": avg(lambda d: (d["bookings"].get("application") or {}).get("mean_hold_ms_of_closed_non_transient")),
        "rejection_events": avg(lambda d: d["protocol_rejections"]["events"]),
        "pairs_generated": avg(generated), "pairs_unused": avg(unused),
        "waste_percent": avg(lambda d: (100 * unused(d) / generated(d)) if d.get("compiler") and generated(d) else
                             (100 * (d["stats"]["protocol_generated_pairs"] - d["stats"]["protocol_used_pairs"]) / d["stats"]["protocol_generated_pairs"]
                              if d["stats"].get("protocol_generated_pairs") else None)),
        "waste_expired_percent": avg(lambda d: d["stats"].get("protocol_waste_percentage")),
        "hop0_hold_ms": chain("hop0", "mean_ready_hold_ms"), "hop1_hold_ms": chain("hop1", "mean_ready_hold_ms"),
        "hop2plus_hold_ms": chain("hop2+", "mean_ready_hold_ms"),
        "hop0_request_wait_after_ready_ms": chain("hop0", "mean_request_eligible_minus_generated_ms"),
        "hop1_request_wait_after_ready_ms": chain("hop1", "mean_request_eligible_minus_generated_ms"),
        "hop2plus_request_wait_after_ready_ms": chain("hop2+", "mean_request_eligible_minus_generated_ms"),
        "hop0_pairs": chain("hop0", "pairs"), "hop1_pairs": chain("hop1", "pairs"), "hop2plus_pairs": chain("hop2+", "pairs"),
        "hop0_made_before_layer_ms": avg(lambda d: -d["pair_hold_by_chain_position"]["hop0"]["mean_generated_minus_layer_start_ms"]),
        "hop1_made_before_layer_ms": avg(lambda d: -d["pair_hold_by_chain_position"]["hop1"]["mean_generated_minus_layer_start_ms"]),
        "hop2plus_made_before_layer_ms": avg(lambda d: -d["pair_hold_by_chain_position"]["hop2+"]["mean_generated_minus_layer_start_ms"]),
        "makespan_ms": avg(lambda d: d["stats"]["end_to_end_latency_ms"]),
    }


def _safe(f, d):
    try:
        return f(d)
    except (KeyError, TypeError, ZeroDivisionError, StopIteration):
        return None


def main(folder: Path) -> None:
    rows = sorted((row(p) for p in folder.glob("*.json")), key=lambda r: (r["group"], r["workload"], r["mapping_seed"], r["memories"], r["name"]))
    with (folder / "diagnostics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {folder / 'diagnostics.csv'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
