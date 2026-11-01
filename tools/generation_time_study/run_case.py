"""Run one case of the study and reduce its per-request output to compact per-seed records.

A case is a JSON spec: a trace, a set of knobs, and the compiler options.  The simulator's own
CLI does the work with --audit-events, so every trial is checked by the physical invariant audit
and a violation fails the case.  Per-request files are large, so after reduction they are deleted
unless keep_raw is set; any case can be reproduced from its spec, because runs are deterministic
in the seed.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import statistics
import sys

import knobs as kn

SUMMARY_FIELDS = (
    "requests", "completed_requests", "completion_rate", "request_latency_mean_ms", "request_latency_median_ms",
    "request_latency_p95_ms", "request_latency_max_ms", "end_to_end_latency_ms", "average_admission_wait_ms",
    "max_admission_wait_ms", "requests_that_waited_fraction", "average_delivered_epr_fidelity", "total_retries",
    "requests_with_retries", "avg_entanglement_generation_time_ms", "max_entanglement_generation_time_ms",
    "scheduled_preparations", "planner_blocked_preparations", "planner_peak_compiler_memory_per_core",
    "runtime_launched_preparations", "runtime_accepted_preparations", "runtime_rejected_preparations",
    "runtime_rejection_events", "pregenerated_hits", "intended_request_hits", "late_compiler_pair_uses",
    "on_demand_fallbacks", "generated_compiler_pairs", "utilized_compiler_pairs", "expired_compiler_pairs",
    "remaining_compiler_pairs", "compiler_waste_percentage", "average_fidelity_at_creation",
    "average_fidelity_at_utilization", "average_storage_time_ms", "protocol_generated_pairs", "protocol_used_pairs",
    "protocol_unused_pairs", "compiler_progress_yields")


def build_argv(spec: dict, config: Path, output: Path) -> list[str]:
    argv = ["run_trace_comparison", "--trace", str(kn.ROOT / spec["trace"]), "--config", str(config),
            "--strategies", spec["strategies"], "--seeds", spec["seeds"],
            "--total-memories", str(spec["memories"]), "--compiler-memories", str(spec["compiler_memories"]),
            "--generation-capacity", str(spec["generation_capacity"]), "--planner-lead-layers", str(spec["lead"]),
            "--dynamic-lookahead-layers", str(spec["lookahead"]), "--coherence-time-layers", str(spec["coherence_layers"]),
            "--scheduler", "per-qubit", "--admission", "event", "--admission-priority", spec["priority"],
            "--pregeneration-buffer-ms", "0", "--stop-after-workload", "--audit-events",
            "--compiler-reservation-ms", str(spec["reservation_ms"]), "--compiler-pair-consumption", spec["consumption"],
            "--request-duration-ms", str(spec["request_duration_ms"]),
            "--preparation-trigger", spec["trigger"], "--predecessor-distance", str(spec["predecessor_distance"]),
            "--planning-mode", spec["planning"], "--output", str(output)]
    argv += ["--all-chain-hops"] if spec["chain_hops"] is None else ["--chain-hops-prepared", str(spec["chain_hops"])]
    argv += ["--no-congestion-threshold"] if spec["congestion"] is None else ["--congestion-threshold", str(spec["congestion"])]
    return argv + list(spec["flags"])


def quantiles(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    at = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]
    return dict(n=len(values), mean=statistics.fmean(values), p10=at(0.1), p50=at(0.5), p90=at(0.9), max=ordered[-1])


def request_classes(pairs: list[dict]) -> dict[int, str]:
    """hit: the pair existed before the request's first submission; late: used, but arrived after it."""
    classes: dict[int, str] = {}
    for pair in pairs:
        if pair["status"] != "used" or pair["actual_request_id"] in ("", None):
            continue
        request = int(float(pair["actual_request_id"]))
        prepared = pair["prepared_before_request"] == "True"
        classes[request] = "hit" if prepared or classes.get(request) == "hit" else "late"
    return classes


def reduce_trial(output: Path, strategy: str, seed: str, requests: dict) -> dict:
    timing = list(csv.DictReader((output / f"timing_{strategy}_{seed}.csv").open()))
    pairs_path = output / f"pairs_{strategy}_{seed}.csv"
    pairs = list(csv.DictReader(pairs_path.open())) if pairs_path.exists() else []
    classes = request_classes(pairs)
    buckets: dict[str, list[dict]] = {}
    for row in timing:
        request = requests[int(row["request_id"])]
        kind = classes.get(int(row["request_id"]), "demand")
        direction = "reverse" if request.source_core > request.destination_core else "forward"
        for key in (kind, f"{kind}_{direction}", direction):
            buckets.setdefault(key, []).append(row)
    mean = lambda rows, name: statistics.fmean(float(r[name]) for r in rows)
    groups = {key: dict(n=len(rows), latency_ms=mean(rows, "total_time_ms"),
                        generation_ms=mean(rows, "entanglement_generation_time_ms"),
                        admission_ms=mean(rows, "admission_wait_time_ms"),
                        retry_wait_ms=mean(rows, "retry_wait_time_ms"),
                        guard_ms=mean(rows, "reservation_start_delay_time_ms"),
                        setup_ms=mean(rows, "reservation_setup_time_ms"))
              for key, rows in buckets.items()}
    prepared, storage, slack, margin = [], [], [], []
    for pair in pairs:
        if pair["generated_at_ps"] in ("", None) or pair["reservation_start_ps"] in ("", None):
            continue
        start = float(pair["reservation_start_ps"])
        prepared.append((float(pair["generated_at_ps"]) - start) / 1e9)
        if pair["target_request_start_ps"] not in ("", None):
            slack.append((float(pair["target_request_start_ps"]) - start) / 1e9)
            margin.append((float(pair["target_request_start_ps"]) - float(pair["generated_at_ps"])) / 1e9)
        if pair["utilized_at_ps"] not in ("", None):
            storage.append((float(pair["utilized_at_ps"]) - float(pair["generated_at_ps"])) / 1e9)
    audit = json.loads((output / f"audit_{strategy}_{seed}.json").read_text())
    return dict(groups=groups, preparation_ms=quantiles(prepared), storage_ms=quantiles(storage),
                slack_ms=quantiles(slack), margin_ms=quantiles(margin),
                pair_status={s: sum(p["status"] == s for p in pairs) for s in {p["status"] for p in pairs}},
                audit_events=audit["events"], audit_violations=len(audit["violations"]))


def reduce_run(spec: dict, output: Path) -> dict:
    kn.add_paths()
    from ace.compiler.compiler_trace import parse_compiler_trace
    trace = parse_compiler_trace(kn.ROOT / spec["trace"])
    requests = {r.request_id: r for r in trace.requests}
    active = {r.layer for r in trace.requests}
    trials = []
    for row in csv.DictReader((output / "summary.csv").open()):
        record = dict(strategy=row["strategy"], seed=int(row["seed"]))
        record.update({name: float(row[name]) for name in SUMMARY_FIELDS if row.get(name) not in ("", None)})
        record.update(reduce_trial(output, row["strategy"], row["seed"], requests))
        all_rows = sum(g["n"] for key, g in record["groups"].items() if key in ("forward", "reverse"))
        weighted = sum(g["n"] * g["latency_ms"] for key, g in record["groups"].items() if key in ("forward", "reverse"))
        record["consistency_latency_error_ms"] = abs(weighted / all_rows - record["request_latency_mean_ms"])
        trials.append(record)
    return dict(spec=spec, layers=trace.layer_count, active_layers=len(active), empty_layers=trace.layer_count - len(active),
                hops=len(trace.requests), trials=trials)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    settings = kn.Knobs(**spec["knobs"])
    args.output.mkdir(parents=True, exist_ok=True)
    config = kn.write_config(args.output / "config.json", settings)
    kn.patch_runtime(settings)
    from ace.cli import run_trace_comparison as cli
    sys.argv = build_argv(spec, config, args.output)
    with contextlib.redirect_stdout(io.StringIO()):
        cli.main()
    reduced = reduce_run(spec, args.output)
    (args.output / "reduced.json").write_text(json.dumps(reduced))
    if not spec.get("keep_raw"):
        for pattern in ("admission_*.json", "audit_*.json", "timing_*.csv", "pairs_*.csv", "config.json"):
            for path in args.output.glob(pattern):
                path.unlink()


if __name__ == "__main__":
    main()
