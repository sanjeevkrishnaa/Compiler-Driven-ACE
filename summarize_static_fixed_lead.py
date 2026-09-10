"""Produce audited, hash-backed ACE static fixed-lead summaries."""
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

def mean(rows: list[dict], key: str) -> float:
    return fmean(float(row[key]) for row in rows)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--profile", required=True, choices=("1plus1", "2plus2", "3plus1"))
    parser.add_argument("--execution-provenance", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    prefix = f"static-{args.profile}-fixed-delta"
    studies, provenance = [], []
    raw_by_delta: dict[int, list[dict]] = {}
    for delta in range(1, 7):
        profile = f"{prefix}{delta}"
        raw = args.raw_root / profile / "runs.json"
        contract = args.contracts / f"qft_4x4_static-{args.profile}_fixed_delta{delta}_v1.json"
        payload = json.loads(raw.read_text(encoding="utf-8"))
        audit = audit_payload(payload)
        rows = [run["summary"] for run in payload["runs"]]
        errors = list(audit["errors"])
        if payload.get("trace_sha256") != TRACE_SHA256:
            errors.append("trace SHA-256 differs from locked QFT trace")
        if {int(row["seed"]) for row in rows} != set(range(30)):
            errors.append("replications are not exactly paired seeds 0..29")
        if any(row["configuration"] != f"{profile}:fixed" or row["strategy"] != "fixed" for row in rows):
            errors.append("unexpected profile or strategy")
        contract_hash = digest(contract)
        if payload.get("experiment_contract", {}).get("sha256") != contract_hash:
            errors.append("raw run does not bind to this immutable contract")
        if errors:
            raise ValueError(f"{profile} audit failed: {'; '.join(errors)}")
        raw_by_delta[delta] = rows
        studies.append({"delta": delta, "latency_ms": mean(rows, "average_request_latency_ms"),
                        "pre_ready_rate": mean(rows, "pregenerated_success_rate"),
                        "compiler_fidelity_at_use": mean(rows, "average_compiler_fidelity_at_utilization"),
                        "delivered_fidelity": mean(rows, "average_delivered_epr_fidelity"),
                        "expiry_percent": mean(rows, "compiler_expiry_percentage"),
                        "fallback_rate": mean(rows, "on_demand_fallback_rate"),
                        "preparation_attempts": mean(rows, "runtime_launched_preparations"),
                        "rejection_count": mean(rows, "runtime_rejection_events")})
        provenance.append({"delta": delta, "raw_runs": str(raw), "raw_runs_sha256": digest(raw),
                           "contract": str(contract), "contract_sha256": contract_hash,
                           "identity_audit": audit, "request_instances": len(rows) * 4954})
    baseline = {int(row["seed"]): row for row in raw_by_delta[2]}
    for item in studies:
        item["paired_latency_minus_delta2_ms"] = fmean(
            float(baseline[int(row["seed"])]["average_request_latency_ms"])
            - float(row["average_request_latency_ms"]) for row in raw_by_delta[item["delta"]])
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(studies[0]))
        writer.writeheader(); writer.writerows(studies)
    execution = json.loads(args.execution_provenance.read_text(encoding="utf-8"))
    (args.output / "provenance.json").write_text(json.dumps({"trace_sha256": TRACE_SHA256,
        "paired_seeds": list(range(30)), "profile": args.profile, "execution": execution,
        "studies": provenance}, indent=2) + "\n", encoding="utf-8")
    lines = [f"# ACE static {args.profile} fixed-lead sensitivity, audited 30-seed sweep", "",
             "All cells use immutable contracts, paired seeds 0--29, the locked trace, raw SHA-256 provenance, and a passing completion and request/pair-identity audit.", "",
             "| Delta | Latency (ms) | Pre-ready | Fidelity at use | Expiry | Fallback | Paired latency minus delta 2 (ms) |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for item in studies:
        lines.append(f"| {item['delta']} | {item['latency_ms']:.6f} | {100*item['pre_ready_rate']:.2f}% | {item['compiler_fidelity_at_use']:.4f} | {item['expiry_percent']:.2f}% | {100*item['fallback_rate']:.2f}% | {item['paired_latency_minus_delta2_ms']:.6f} |")
    lines += ["", "Raw `runs.json` files remain local and ignored. `provenance.json` binds each raw artifact and immutable contract by SHA-256."]
    (args.output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
if __name__ == "__main__":
    main()
