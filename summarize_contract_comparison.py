"""Summarize audited ACE and native-SeQUeNCe contract matrices.

The two backends intentionally model different protocols, so this utility reports
their absolute results side by side but only computes paired policy effects within
each backend and memory profile.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from experiment_statistics import summarize


PROFILES = ("full-odg-4", "static-3plus1", "static-2plus2", "static-1plus1")
METRICS = (
    "latency_ms", "pre_ready_rate", "fidelity_at_use", "expiry_percent",
    "fallback_rate", "preparation_attempts",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_contract(contract_path: Path, metadata: dict, profile: str) -> None:
    digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if metadata.get("sha256") != digest:
        raise ValueError(f"{profile}: contract SHA-256 mismatch")
    if metadata.get("profile") != profile:
        raise ValueError(f"{profile}: artifact profile mismatch")
    if not metadata.get("replications_complete"):
        raise ValueError(f"{profile}: artifact is a limited validation run")


def _ace_trials(root: Path, contract: Path, profile: str) -> list[dict]:
    payload = _load(root / profile / "runs.json")
    _verify_contract(contract, payload["experiment_contract"], profile)
    rows = []
    for run in payload["runs"]:
        trial = run["summary"]
        strategy = trial["strategy"]
        if strategy == "on-demand":
            strategy = "odg"
        rows.append({
            "backend": "ACE", "profile": profile, "strategy": strategy,
            "seed": int(trial["seed"]),
            "latency_ms": trial["average_request_latency_ms"],
            "pre_ready_rate": trial["pregenerated_success_rate"],
            "fidelity_at_use": trial["average_compiler_fidelity_at_utilization"],
            "expiry_percent": trial["compiler_expiry_percentage"],
            "fallback_rate": trial["on_demand_fallback_rate"],
            "preparation_attempts": trial["runtime_accepted_preparations"],
        })
    return rows


def _native_trials(root: Path, contract: Path, profile: str) -> list[dict]:
    payload = _load(root / profile / "study.json")
    _verify_contract(contract, payload["experiment_contract"], profile)
    if payload.get("status") != "complete":
        raise ValueError(f"{profile}: native study status is not complete")
    rows = []
    for trial in payload["trials"]:
        strategy = "matched-on-demand" if trial["strategy"] == "matched-odg" else trial["strategy"]
        rows.append({
            "backend": "native-SeQUeNCe", "profile": profile,
            "strategy": strategy, "seed": int(trial["seed"]),
            "latency_ms": trial["average_latency_ms"],
            "pre_ready_rate": trial["pregenerated_transfer_success_rate"],
            "fidelity_at_use": trial["average_compiler_epr_fidelity_at_utilization"],
            "expiry_percent": trial["expiry_percentage"],
            "fallback_rate": trial["compiler_on_demand_fallbacks"] / trial["requests"],
            "preparation_attempts": trial["compiler_preparation_attempts"],
        })
    return rows


def _fmt(value: float | None, digits: int = 6) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--ace-root", required=True, type=Path)
    parser.add_argument("--native-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    contract = _load(args.contract)
    replication = contract["replications"]
    expected_seeds = set(range(
        replication["seed_start"],
        replication["seed_start"] + replication["seed_count"],
    ))
    trials = []
    for profile in PROFILES:
        trials.extend(_ace_trials(args.ace_root, args.contract, profile))
        trials.extend(_native_trials(args.native_root, args.contract, profile))

    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for trial in trials:
        grouped.setdefault((trial["backend"], trial["profile"], trial["strategy"]), []).append(trial)
    for key, rows in grouped.items():
        seeds = {row["seed"] for row in rows}
        if seeds != expected_seeds:
            raise ValueError(f"{key}: seeds differ from contract: {sorted(seeds)}")

    aggregate_rows = []
    for key in sorted(grouped):
        rows = grouped[key]
        record = {"backend": key[0], "profile": key[1], "strategy": key[2], "n": len(rows)}
        for metric in METRICS:
            stats = summarize([row[metric] for row in rows if row[metric] is not None])
            record[f"{metric}_mean"] = stats["mean"]
            record[f"{metric}_ci95_low"] = stats["ci95_low"]
            record[f"{metric}_ci95_high"] = stats["ci95_high"]
        aggregate_rows.append(record)

    paired_rows = []
    for backend in ("ACE", "native-SeQUeNCe"):
        for profile in PROFILES[1:]:
            for candidate, baseline in (("fixed", "matched-on-demand"),
                                        ("dynamic", "matched-on-demand"),
                                        ("dynamic", "fixed")):
                base = {r["seed"]: r for r in grouped[(backend, profile, baseline)]}
                cand = {r["seed"]: r for r in grouped[(backend, profile, candidate)]}
                deltas = [base[s]["latency_ms"] - cand[s]["latency_ms"] for s in sorted(expected_seeds)]
                pct = [100 * (base[s]["latency_ms"] - cand[s]["latency_ms"]) / base[s]["latency_ms"]
                       for s in sorted(expected_seeds)]
                dstat, pstat = summarize(deltas), summarize(pct)
                paired_rows.append({
                    "backend": backend, "profile": profile, "candidate": candidate,
                    "baseline": baseline, "n": len(deltas),
                    "latency_reduction_ms_mean": dstat["mean"],
                    "latency_reduction_ms_ci95_low": dstat["ci95_low"],
                    "latency_reduction_ms_ci95_high": dstat["ci95_high"],
                    "latency_reduction_percent_mean": pstat["mean"],
                    "latency_reduction_percent_ci95_low": pstat["ci95_low"],
                    "latency_reduction_percent_ci95_high": pstat["ci95_high"],
                })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("aggregates.csv", aggregate_rows), ("paired_effects.csv", paired_rows)):
        with (args.output_dir / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(rows[0]),
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)

    lines = [
        "# Shared QFT 4×4 contract: 30-seed results", "",
        f"Contract: `{contract['study_id']}`. All rows contain 30 paired seeds and 4,954 requests per seed.", "",
        "> Absolute latency is not comparable across backends: ACE and native SeQUeNCe implement different physical protocols and latency boundaries. Compare policy effects within a backend/profile only.", "",
        "## Aggregate results", "",
        "| Backend | Memory profile | Policy | Latency (ms, mean [95% CI]) | Pre-ready | Fidelity at use | Expiry | Fallback |", "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in aggregate_rows:
        ci = f"{_fmt(r['latency_ms_mean'])} [{_fmt(r['latency_ms_ci95_low'])}, {_fmt(r['latency_ms_ci95_high'])}]"
        lines.append(f"| {r['backend']} | {r['profile']} | {r['strategy']} | {ci} | {_fmt(r['pre_ready_rate_mean'],4)} | {_fmt(r['fidelity_at_use_mean'],4)} | {_fmt(r['expiry_percent_mean'],4)}% | {_fmt(r['fallback_rate_mean'],4)} |")
    lines += ["", "## Paired latency effects", "", "Positive reduction means the candidate is faster than the baseline.", "", "| Backend | Profile | Candidate vs baseline | Mean reduction | 95% CI |", "|---|---|---|---:|---:|"]
    for r in paired_rows:
        lines.append(f"| {r['backend']} | {r['profile']} | {r['candidate']} vs {r['baseline']} | {_fmt(r['latency_reduction_percent_mean'],3)}% | [{_fmt(r['latency_reduction_percent_ci95_low'],3)}, {_fmt(r['latency_reduction_percent_ci95_high'],3)}]% |")
    lines += ["", "## Interpretation rule", "", "The shared trace, seeds, memory budgets, scheduling parameters, and deterministic conflict serialization are identical. Protocol semantics are not identical; therefore this is a reproducible cross-implementation consistency study, not a claim that one simulator is faster than the other.", ""]
    (args.output_dir / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
