"""Create a trace-verified ACE versus native-SeQUeNCe comparison table."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from experiment_statistics import interval_from_summary


def _float(row: dict, name: str) -> float | None:
    value = row.get(name)
    return None if value in (None, "") else float(value)


def _interval(mean, sd, n):
    if mean is None or sd is None:
        return None, None
    return interval_from_summary(float(mean), float(sd), n)


def build_rows(ace_rows: list[dict], native: dict) -> list[dict]:
    ace_by_name = {row["configuration"]: row for row in ace_rows}
    trace_hash = native["trace"]["sha256"]
    output = []
    for ace_name, display in (("on-demand", "odg"),
                              ("fixed-delta2", "fixed"),
                              ("dynamic", "dynamic")):
        row = ace_by_name[ace_name]
        fidelity_prefix = ("average_compiler_fidelity_at_utilization"
                           if display != "odg" else "average_delivered_epr_fidelity")
        output.append({
            "implementation": "ACE + SeQUeNCe 0.8.1",
            "strategy": display,
            "trace_sha256": trace_hash,
            "trials": int(row["average_request_latency_ms_n"]),
            "latency_ms_mean": _float(row, "average_request_latency_ms_mean"),
            "latency_ms_sample_sd": _float(row, "average_request_latency_ms_sample_sd"),
            "latency_ms_ci95_low": _float(row, "average_request_latency_ms_ci95_low"),
            "latency_ms_ci95_high": _float(row, "average_request_latency_ms_ci95_high"),
            "pre_ready_rate_mean": _float(row, "pregenerated_success_rate_mean"),
            "pre_ready_rate_sample_sd": _float(row, "pregenerated_success_rate_sample_sd"),
            "pre_ready_rate_ci95_low": _float(row, "pregenerated_success_rate_ci95_low"),
            "pre_ready_rate_ci95_high": _float(row, "pregenerated_success_rate_ci95_high"),
            "fidelity_at_use_mean": _float(row, f"{fidelity_prefix}_mean"),
            "fidelity_at_use_sample_sd": _float(row, f"{fidelity_prefix}_sample_sd"),
            "fidelity_at_use_ci95_low": _float(row, f"{fidelity_prefix}_ci95_low"),
            "fidelity_at_use_ci95_high": _float(row, f"{fidelity_prefix}_ci95_high"),
            "expiry_percentage_mean": _float(row, "compiler_expiry_percentage_mean"),
            "expiry_percentage_ci95_low": _float(row, "compiler_expiry_percentage_ci95_low"),
            "expiry_percentage_ci95_high": _float(row, "compiler_expiry_percentage_ci95_high"),
        })
    n = int(native["experiment"]["seeds"]["count"])
    for strategy in ("odg", "fixed", "dynamic"):
        item = native["strategies"][strategy]
        latency_ci = _interval(item["latency_ms_mean"],
                               item["latency_ms_sample_stdev"], n)
        ready_mean = item["physically_pre_ready_rate_mean"]
        ready_sd = item.get("physically_pre_ready_rate_sample_stdev", 0.0)
        fidelity_mean = item["fidelity_at_use_mean"]
        fidelity_sd = item.get("fidelity_at_use_sample_stdev", 0.0)
        ready_ci = _interval(ready_mean, ready_sd, n)
        fidelity_ci = _interval(fidelity_mean, fidelity_sd, n)
        expiry_mean = item["expiry_percentage_mean"]
        output.append({
            "implementation": "Native SeQUeNCe",
            "strategy": strategy,
            "trace_sha256": trace_hash,
            "trials": n,
            "latency_ms_mean": item["latency_ms_mean"],
            "latency_ms_sample_sd": item["latency_ms_sample_stdev"],
            "latency_ms_ci95_low": latency_ci[0],
            "latency_ms_ci95_high": latency_ci[1],
            "pre_ready_rate_mean": ready_mean,
            "pre_ready_rate_sample_sd": ready_sd,
            "pre_ready_rate_ci95_low": ready_ci[0],
            "pre_ready_rate_ci95_high": ready_ci[1],
            "fidelity_at_use_mean": fidelity_mean,
            "fidelity_at_use_sample_sd": fidelity_sd,
            "fidelity_at_use_ci95_low": fidelity_ci[0],
            "fidelity_at_use_ci95_high": fidelity_ci[1],
            "expiry_percentage_mean": expiry_mean,
            "expiry_percentage_ci95_low": expiry_mean,
            "expiry_percentage_ci95_high": expiry_mean,
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ace-aggregate", required=True, type=Path)
    parser.add_argument("--ace-audit", required=True, type=Path)
    parser.add_argument("--native-reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.ace_aggregate.open(newline="", encoding="utf-8") as handle:
        ace_rows = list(csv.DictReader(handle))
    ace_audit = json.loads(args.ace_audit.read_text(encoding="utf-8"))
    native = json.loads(args.native_reference.read_text(encoding="utf-8"))
    if not ace_audit.get("passed"):
        raise ValueError("ACE audit did not pass")
    ace_hashes = {artifact.get("trace_sha256")
                  for artifact in ace_audit.get("artifacts", [])}
    if ace_hashes != {native["trace"]["sha256"]}:
        raise ValueError("ACE and native artifacts do not use the same trace hash")
    if len({row.get("requests_mean") for row in ace_rows if row.get("requests_mean")}) > 1:
        raise ValueError("ACE rows do not use a common request count")
    rows = build_rows(ace_rows, native)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
