"""Audit trace-driven physical ACE ODG/CGP/ACGP result artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def _close(left, right, tolerance=1e-9) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def audit_payload(payload: dict) -> dict:
    errors, seen = [], set()
    request_instances = pair_records = 0
    for run in payload.get("runs", []):
        summary = run.get("summary", {})
        key = (summary.get("strategy"), summary.get("seed"))
        if key in seen:
            errors.append(f"duplicate strategy/seed {key}")
        seen.add(key)
        requests = int(summary.get("requests", 0))
        completed = int(summary.get("completed_requests", -1))
        request_instances += requests
        if completed != requests or not _close(summary.get("completion_rate", 0), 1):
            errors.append(f"{key}: incomplete requests {completed}/{requests}")

        records = run.get("adaptive_pair_trace", [])
        pair_records += len(records)
        used_ids = []
        generated = used = expired = remaining = 0
        for record in records:
            generated += 1
            generated_at = record.get("generated_at_ps")
            used_at = record.get("used_at_ps")
            expired_at = record.get("expired_at_ps")
            if generated_at is None:
                errors.append(f"{key}: pair has no generation timestamp")
                continue
            if used_at is not None and expired_at is not None:
                errors.append(f"{key}: pair is both used and expired")
            elif used_at is not None:
                used += 1
                used_ids.append(record.get("used_by_request_id"))
                if int(used_at) < int(generated_at):
                    errors.append(f"{key}: use precedes generation")
                fidelity = record.get("fidelity_at_use")
                if fidelity is None or not 0 <= float(fidelity) <= 1:
                    errors.append(f"{key}: used pair has invalid fidelity")
            elif expired_at is not None:
                expired += 1
                if int(expired_at) < int(generated_at):
                    errors.append(f"{key}: expiry precedes generation")
            else:
                remaining += 1
        if None in used_ids or len(used_ids) != len(set(used_ids)):
            errors.append(f"{key}: invalid or duplicate pair utilization request id")
        expected = {
            "adaptive_generated_pairs": generated,
            "adaptive_utilized_pairs": used,
            "adaptive_expired_pairs": expired,
            "adaptive_remaining_pairs": remaining,
        }
        for field, value in expected.items():
            if int(summary.get(field, -1)) != value:
                errors.append(f"{key}: {field} does not match trace")
        if generated != used + expired + remaining:
            errors.append(f"{key}: adaptive pair lifecycle does not conserve pairs")
        expiry = 100 * expired / generated if generated else 0.0
        waste = 100 * (expired + remaining) / generated if generated else 0.0
        if not _close(summary.get("adaptive_expiry_percentage", 0), expiry):
            errors.append(f"{key}: adaptive expiry percentage does not match trace")
        if not _close(summary.get("adaptive_waste_percentage", 0), waste):
            errors.append(f"{key}: adaptive waste percentage does not match trace")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_sha256": payload.get("resolved", {}).get("trace_sha256"),
        "runs": len(payload.get("runs", [])),
        "strategy_seed_cells": len(seen),
        "request_instances": request_instances,
        "adaptive_pair_records": pair_records,
        "passed": not errors,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--expected-trace-sha256")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reports = []
    for path in args.runs:
        report = audit_payload(json.loads(path.read_text(encoding="utf-8")))
        report["artifact"] = str(path)
        if args.expected_trace_sha256 and report["trace_sha256"] != args.expected_trace_sha256:
            report["passed"] = False
            report["errors"].append("trace SHA-256 does not match expected value")
        reports.append(report)
    final = {"passed": all(item["passed"] for item in reports), "artifacts": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, indent=2))
    if not final["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
