"""Audit ACE compiler result artifacts before publication or comparison."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def audit_payload(payload: dict) -> dict:
    errors = []
    seen = set()
    total_requests = 0
    total_records = 0
    for run in payload.get("runs", []):
        summary = run["summary"]
        # One named experiment may intentionally contain several strategies.
        # A trial cell is unique only across configuration, strategy, and seed.
        key = (summary["configuration"], summary["strategy"], int(summary["seed"]))
        if key in seen:
            errors.append(f"duplicate configuration/strategy/seed {key}")
        seen.add(key)
        requests = int(summary["requests"])
        completed = int(summary["completed_requests"])
        total_requests += requests
        if completed != requests or float(summary["completion_rate"]) != 1.0:
            errors.append(f"{key}: incomplete requests {completed}/{requests}")

        records = run.get("epr_utilization_trace", [])
        total_records += len(records)
        states = {state: sum(record["status"] == state for record in records)
                  for state in ("used", "expired", "remaining")}
        if len(records) != int(summary["generated_compiler_pairs"]):
            errors.append(f"{key}: generated-pair accounting mismatch")
        if states["used"] != int(summary["utilized_compiler_pairs"]):
            errors.append(f"{key}: utilized-pair accounting mismatch")
        if states["expired"] != int(summary["expired_compiler_pairs"]):
            errors.append(f"{key}: expired-pair accounting mismatch")
        actual_ids = [record["actual_request_id"] for record in records
                      if record["status"] == "used"]
        if len(actual_ids) != len(set(actual_ids)):
            errors.append(f"{key}: one application request used multiple compiler pairs")
        for record in records:
            if record["status"] == "used" and (
                    record["actual_request_id"] != record["target_request_id"]):
                errors.append(f"{key}: compiler pair used by a non-target request")
                break
            for field in ("fidelity_at_creation", "fidelity_at_utilization"):
                value = record.get(field)
                if value is not None and not 0 <= float(value) <= 1:
                    errors.append(f"{key}: {field} outside [0, 1]")
                    break
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_sha256": payload.get("trace_sha256"),
        "runs": len(payload.get("runs", [])),
        "configuration_strategy_seed_cells": len(seen),
        "request_instances": total_requests,
        "compiler_pair_records": total_records,
        "passed": not errors,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--expected-trace-sha256")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reports = []
    for path in args.runs:
        report = audit_payload(json.loads(path.read_text(encoding="utf-8")))
        report["artifact"] = str(path)
        if (args.expected_trace_sha256
                and report["trace_sha256"] != args.expected_trace_sha256):
            report["passed"] = False
            report["errors"].append("trace SHA-256 does not match expected value")
        reports.append(report)
    final = {"passed": all(report["passed"] for report in reports),
             "artifacts": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, indent=2))
    if not final["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
