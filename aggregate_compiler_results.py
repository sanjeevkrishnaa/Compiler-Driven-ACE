"""Aggregate repeated ACE runs and make seed-paired baseline comparisons."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from experiment_statistics import summarize


DEFAULT_METRICS = (
    "completion_rate", "average_request_latency_ms",
    "average_delivered_epr_fidelity", "pregenerated_success_rate",
    "on_demand_fallback_rate", "compiler_expiry_percentage",
    "compiler_waste_percentage", "average_compiler_fidelity_at_utilization",
    "average_compiler_storage_time_ms",
)


def _read(paths: list[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _number(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows: list[dict[str, str]], metrics=DEFAULT_METRICS) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row.get("configuration", row["strategy"])].append(row)
    output = []
    for configuration, group in sorted(groups.items()):
        result = {"configuration": configuration, "strategy": group[0]["strategy"],
                  "seeds": ",".join(sorted({row["seed"] for row in group}, key=int))}
        for metric in metrics:
            values = [_number(row.get(metric)) for row in group]
            stats = summarize([value for value in values if value is not None])
            for name, value in stats.items():
                result[f"{metric}_{name}"] = value
        output.append(result)
    return output


def paired_latency(rows: list[dict[str, str]], baseline: str) -> list[dict]:
    by_config_seed = {
        (row.get("configuration", row["strategy"]), int(row["seed"])): row
        for row in rows
    }
    configurations = sorted({key[0] for key in by_config_seed} - {baseline})
    output = []
    for configuration in configurations:
        seeds = sorted(
            seed for config, seed in by_config_seed
            if config == configuration and (baseline, seed) in by_config_seed
        )
        differences = []
        reductions = []
        for seed in seeds:
            base = _number(by_config_seed[(baseline, seed)]["average_request_latency_ms"])
            candidate = _number(by_config_seed[(configuration, seed)]["average_request_latency_ms"])
            if base is None or candidate is None:
                continue
            differences.append(candidate - base)
            reductions.append(100 * (base - candidate) / base)
        difference_stats = summarize(differences)
        reduction_stats = summarize(reductions)
        result = {"baseline": baseline, "configuration": configuration,
                  "paired_seeds": ",".join(map(str, seeds))}
        result.update({f"latency_difference_ms_{key}": value
                       for key, value in difference_stats.items()})
        result.update({f"latency_reduction_percent_{key}": value
                       for key, value in reduction_stats.items()})
        output.append(result)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--baseline", default="on-demand")
    parser.add_argument("--output", type=Path, default=Path("results/aggregate.csv"))
    parser.add_argument("--paired-output", type=Path,
                        default=Path("results/paired_latency.csv"))
    args = parser.parse_args()
    rows = _read(args.summaries)
    _write(args.output, aggregate(rows))
    _write(args.paired_output, paired_latency(rows, args.baseline))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.paired_output}")


if __name__ == "__main__":
    main()
