
from __future__ import annotations

import csv
import json
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from qmap import __version__
from qmap.experiments.runner import TrialResult

__all__ = ["ResultWriter", "collect_metadata", "summarise"]

_TRACKED_PACKAGES = ("numpy", "scipy", "networkx", "pytket", "qiskit", "matplotlib")

def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _TRACKED_PACKAGES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "not installed"
    return versions

def collect_metadata(
    *,
    seed: int,
    seed_path: str,
    configuration: dict[str, Any],
    command: str | None = None,
) -> dict[str, Any]:
    return {
        "qmap_version": __version__,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "seed": seed,
        "seed_path": seed_path,
        "command": command or " ".join(sys.argv),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": _package_versions(),
        "configuration": configuration,
    }

def summarise(
    results: list[TrialResult], *, include_hop_count: bool = True
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[TrialResult]] = {}
    for result in results:
        key = (result.benchmark, result.grid, result.reliability_band, result.placer)
        grouped.setdefault(key, []).append(result)

    baseline: dict[tuple[Any, ...], float] = {}
    for (benchmark, grid, band, placer), group in grouped.items():
        if placer == "HQA":
            baseline[(benchmark, grid, band)] = sum(r.cost.cost for r in group) / len(group)

    rows: list[dict[str, Any]] = []
    for (benchmark, grid, band, placer), group in sorted(grouped.items(), key=str):
        n = len(group)
        mean_cost = sum(r.cost.cost for r in group) / n
        reference = baseline.get((benchmark, grid, band))
        row: dict[str, Any] = {
                "benchmark": benchmark,
                "grid": grid,
                "reliability_band": band,
                "placer": placer,
                "repeats": n,
                "n_cores": group[0].n_cores,
                "n_qubits": group[0].n_qubits,
                "n_slices": group[0].n_slices,
                "mean_cost": mean_cost,
                "min_cost": min(r.cost.cost for r in group),
                "max_cost": max(r.cost.cost for r in group),
                "mean_epr_latency": sum(r.cost.epr_latency for r in group) / n,
                "mean_path_quality": sum(r.cost.path_quality for r in group) / n,
                "mean_infeasible_operations": (
                    sum(r.cost.infeasible_operations for r in group) / n
                ),
                "min_runtime_seconds": min(r.runtime_seconds for r in group),
                "mean_runtime_seconds": sum(r.runtime_seconds for r in group) / n,
                "residual_operations": sum(r.cost.residual_operations for r in group),
                "all_complete": all(r.cost.is_complete for r in group),
                "gain_vs_HQA": (
                    reference / mean_cost if reference and mean_cost > 0 else None
                ),
            }
        if include_hop_count:
            row["mean_hops"] = sum(r.cost.hops for r in group) / n
        rows.append(row)
    return rows

@dataclass(frozen=True, slots=True)
class ResultWriter:

    directory: Path
    stem: str

    def write(
        self,
        results: list[TrialResult],
        metadata: dict[str, Any],
        *,
        include_hop_count: bool = True,
    ) -> dict[str, Path]:
        if not results:
            raise ValueError("no results to write; the experiment produced no trials")

        self.directory.mkdir(parents=True, exist_ok=True)
        records = [result.as_record(include_hop_count=include_hop_count) for result in results]
        summary = summarise(results, include_hop_count=include_hop_count)

        csv_path = self.directory / f"{self.stem}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)

        json_path = self.directory / f"{self.stem}.json"
        json_path.write_text(
            json.dumps({"trials": records, "summary": summary}, indent=2),
            encoding="utf-8",
        )

        metadata_path = self.directory / f"{self.stem}.metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        summary_path = self.directory / f"{self.stem}.summary.csv"
        with summary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)

        return {
            "csv": csv_path,
            "json": json_path,
            "metadata": metadata_path,
            "summary": summary_path,
        }
