"""Produce hash-backed, audited summaries for the ACE fixed-lead sweep."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import fmean

from audit_compiler_results import audit_payload

TRACE_SHA256 = "61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_path(root: Path, delta: int) -> Path:
    if delta == 4:
        return root / "delta-4-corrected" / "shared-pool-4-cap3-fixed-delta4" / "runs.json"
    return root / f"delta-{delta}-corrected" / "runs.json"


def mean(rows: list[dict], key: str) -> float:
    return fmean(float(row[key]) for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--execution-provenance", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    studies, provenance = [], []
    for delta in range(1, 7):
        raw = raw_path(args.raw_root, delta)
        contract = args.contracts / f"qft_4x4_shared_pool_fixed_delta{delta}_v1.json"
        payload = json.loads(raw.read_text(encoding="utf-8"))
        report = audit_payload(payload)
        rows = [run["summary"] for run in payload["runs"]]
        expected_profile = f"shared-pool-4-cap3-fixed-delta{delta}:fixed"
        errors = list(report["errors"])
        if payload.get("trace_sha256") != TRACE_SHA256:
            errors.append("trace SHA-256 differs from locked QFT trace")
        if {int(row["seed"]) for row in rows} != set(range(30)):
            errors.append("replications are not exactly paired seeds 0..29")
        if any(row["configuration"] != expected_profile or row["strategy"] != "fixed"
               for row in rows):
            errors.append("unexpected profile or strategy")
        contract_hash = digest(contract)
        if payload.get("experiment_contract", {}).get("sha256") != contract_hash:
            errors.append("raw run does not bind to this immutable contract")
        if errors:
            raise ValueError(f"delta {delta} audit failed: {'; '.join(errors)}")
        studies.append({
            "delta": delta,
            "latency_ms": mean(rows, "average_request_latency_ms"),
            "pre_ready_rate": mean(rows, "pregenerated_success_rate"),
            "compiler_fidelity_at_use": mean(rows, "average_compiler_fidelity_at_utilization"),
            "delivered_fidelity": mean(rows, "average_delivered_epr_fidelity"),
            "expiry_percent": mean(rows, "compiler_expiry_percentage"),
            "fallback_rate": mean(rows, "on_demand_fallback_rate"),
            "preparation_attempts": mean(rows, "runtime_launched_preparations"),
            "rejection_count": mean(rows, "runtime_rejection_events"),
        })
        provenance.append({"delta": delta, "raw_runs": str(raw), "raw_runs_sha256": digest(raw),
                           "contract": str(contract), "contract_sha256": contract_hash,
                           "identity_audit": report, "requests": len(rows) * 4954})

    baseline = {
        int(item["summary"]["seed"]): item["summary"]
        for item in json.loads(raw_path(args.raw_root, 2).read_text())["runs"]
    }
    for row in studies:
        candidate = json.loads(raw_path(args.raw_root, row["delta"]).read_text())["runs"]
        effects = [float(baseline[int(item["summary"]["seed"])]["average_request_latency_ms"])
                   - float(item["summary"]["average_request_latency_ms"]) for item in candidate]
        row["paired_latency_minus_delta2_ms"] = fmean(effects)

    args.output.mkdir(parents=True, exist_ok=True)
    fields = list(studies[0])
    with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(studies)
    execution = json.loads(args.execution_provenance.read_text(encoding="utf-8"))
    (args.output / "provenance.json").write_text(json.dumps({
        "trace_sha256": TRACE_SHA256, "paired_seeds": list(range(30)),
        "source": "ACE shared pool cap3 legacy admission", "execution": execution,
        "studies": provenance,
    }, indent=2) + "\n", encoding="utf-8")
    lines = ["# ACE fixed-lead sensitivity, corrected 30-seed sweep", "",
             "All cells use the locked trace, paired seeds 0–29, the listed immutable contracts, and a passing completion and request/pair identity audit.", "",
             "| Delta | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Fallback | Paired latency − delta 2 (ms) |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in studies:
        lines.append(f"| {row['delta']} | {row['latency_ms']:.6f} | {100*row['pre_ready_rate']:.2f}% | {row['compiler_fidelity_at_use']:.4f} | {row['expiry_percent']:.2f}% | {100*row['fallback_rate']:.2f}% | {row['paired_latency_minus_delta2_ms']:.6f} |")
    lines += ["", "Raw `runs.json` files are ignored locally; `provenance.json` records their SHA-256 values and contract bindings.", "", "The historical ACE cap-three implementation is retained for this fixed-lead sweep. It must not be used as a capacity-only comparator for the new cap-four atomic-admission control until a matched cap-three atomic control is run."]
    (args.output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
