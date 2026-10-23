"""Reproducible Table 1 and configuration-sweep experiment runners."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

from qmap.architecture.reliability import ReliabilityBand
from qmap.experiments.runner import prepare_trial, run_trials
from qmap.placement.base import PlacerConfig
from qmap.placement.cost import CostNormalization
from qmap.rng import SeedSequence

__all__ = ["main", "run_extensive", "run_table1"]

SEED = 20260101
BENCHMARKS = ("qft", "cuccaro", "draper", "random")
TOPOLOGIES = ("mesh", "torus", "line", "tree")
GRIDS = ("2x2", "4x4", "8x4", "8x8")
LINE_RELIABILITY_MIN = 0.95
INITIAL_PLACEMENTS = ("sequential", "oee", "oee_cost")
NORMALIZATIONS = (CostNormalization.NONE, CostNormalization.MINMAX)
RELIABILITY_FLOORS = (0.1, 0.4, 0.7, 0.9)

TABLE1_CONFIGURATIONS = {
    "qft": ("oee", CostNormalization.NONE, 0.7),
    "cuccaro": ("sequential", CostNormalization.MINMAX, 0.1),
    "draper": ("oee_cost", CostNormalization.MINMAX, 0.1),
    "random": ("oee", CostNormalization.MINMAX, 0.1),
}

PUBLISHED_GAINS = {
    "qft": {
        "mesh": (1.36, 1.75, 2.64, 2.77),
        "torus": (1.38, 1.61, 2.24, 2.48),
        "line": (1.40, 2.27, 3.46, 2.18),
        "tree": (1.38, 1.39, 2.40, 2.57),
    },
    "cuccaro": {
        "mesh": (1.63, 1.81, 2.72, 2.74),
        "torus": (1.61, 2.21, 2.85, 3.16),
        "line": (1.50, 1.95, 2.11, 2.40),
        "tree": (1.80, 3.03, 5.67, 5.60),
    },
    "draper": {
        "mesh": (1.02, 1.74, 2.22, 1.66),
        "torus": (1.03, 1.88, 2.28, 1.79),
        "line": (0.87, 2.00, 1.96, 1.68),
        "tree": (1.10, 2.06, 2.03, 1.93),
    },
    "random": {
        "mesh": (0.61, 1.04, 1.14, 1.19),
        "torus": (0.74, 1.15, 1.11, 1.19),
        "line": (0.74, 1.28, 1.19, 1.25),
        "tree": (0.82, 1.11, 1.12, 1.29),
    },
}


def _run_cell(
    *,
    benchmark: str,
    topology: str,
    grid: str,
    initial_placement: str,
    normalization: CostNormalization,
    reliability_min: float,
    experiment: str,
) -> dict[str, object]:
    effective_min = LINE_RELIABILITY_MIN if topology == "line" else reliability_min
    seed = SeedSequence.from_seed(SEED).for_trial(
        experiment,
        benchmark,
        initial_placement,
        normalization.value,
        reliability_min,
        topology,
        grid,
    )
    setup = prepare_trial(
        grid=grid,
        benchmark=benchmark,
        seed=seed,
        reliability_band=ReliabilityBand(effective_min, 1.0),
        qubits_per_core=8,
        reserved_ancilla=2,
        topology=topology,
    )
    config = PlacerConfig(
        initial_placement=initial_placement,
        lookahead=8,
        lookahead_weight=1.0,
        normalization=normalization,
        lambda_scaling="fixed",
        allow_eviction=True,
    )
    costs = {
        result.placer: result.cost
        for result in run_trials(
            setup,
            ("HQA", "TR-HQA"),
            config,
            benchmark=benchmark,
            reliability_band=f"{effective_min:.2f}-1.00",
        )
    }
    hqa, tr_hqa = costs["HQA"], costs["TR-HQA"]
    return {
        "benchmark": benchmark,
        "topology": topology,
        "grid": grid,
        "initial_placement": initial_placement,
        "normalization": normalization.value,
        "reliability_floor": reliability_min,
        "reliability_band": f"U[{effective_min:.2f}, 1.00]",
        "hqa_cost": hqa.cost,
        "tr_hqa_cost": tr_hqa.cost,
        "measured_gain": hqa.cost / tr_hqa.cost if tr_hqa.cost else math.nan,
        "hqa_infeasible_operations": hqa.infeasible_operations,
        "tr_hqa_infeasible_operations": tr_hqa.infeasible_operations,
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows: list[dict[str, object]] = list(csv.DictReader(handle))
    for row in rows:
        for field in ("hqa_cost", "tr_hqa_cost", "measured_gain"):
            row[field] = float(row[field])
        for field in ("hqa_infeasible_operations", "tr_hqa_infeasible_operations"):
            row[field] = int(row[field])
        for field in ("published_gain", "gain_delta"):
            if field in row:
                row[field] = float(row[field])
    return rows


def run_table1(output: Path) -> list[dict[str, object]]:
    """Run all 64 selected Table 1 cells and write CSV and Markdown output."""
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / "measurements.csv"
    rows = _read_csv(checkpoint)
    completed = {(row["benchmark"], row["topology"], row["grid"]) for row in rows}
    for benchmark in BENCHMARKS:
        initial, normalization, floor = TABLE1_CONFIGURATIONS[benchmark]
        for topology in TOPOLOGIES:
            for index, grid in enumerate(GRIDS):
                if (benchmark, topology, grid) in completed:
                    continue
                row = _run_cell(
                    benchmark=benchmark,
                    topology=topology,
                    grid=grid,
                    initial_placement=initial,
                    normalization=normalization,
                    reliability_min=floor,
                    experiment="table1",
                )
                row["published_gain"] = PUBLISHED_GAINS[benchmark][topology][index]
                row["gain_delta"] = float(row["measured_gain"]) - float(row["published_gain"])
                rows.append(row)
                _write_csv(checkpoint, rows)
                print(f"completed {len(rows)}/64: {benchmark} {topology} {grid}", flush=True)
    if len(rows) != 64:
        return rows
    gains = [float(row["measured_gain"]) for row in rows]
    lines = [
        "# Table 1 reproduction",
        "",
        "Metric: sum of reliability-weighted shortest-path costs over infeasible "
        "two-qubit operations in every time slice.",
        "",
        "| Benchmark | Initial placement | Normalization | Other-topology reliability |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {benchmark} | {initial} | {normalization.value} | U[{floor:.2f}, 1.00] |"
        for benchmark, (initial, normalization, floor) in TABLE1_CONFIGURATIONS.items()
    )
    lines += [
        "",
        f"Mean measured gain: **{sum(gains) / len(gains):.3f}x**.",
        "",
        "| Benchmark | Topology | Grid | HQA cost | TR-HQA cost | Gain | Published gain | Delta |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    row_template = (
        "| {benchmark} | {topology} | {grid} | {hqa_cost:.3f} | {tr_hqa_cost:.3f} | "
        "{measured_gain:.3f} | {published_gain:.2f} | {gain_delta:+.3f} |"
    )
    lines.extend(row_template.format(**row) for row in rows)
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def run_extensive(output: Path) -> list[dict[str, object]]:
    """Sweep all benchmarks, placement strategies, normalizations, and bands."""
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / "measurements.csv"
    rows = _read_csv(checkpoint)
    completed = {
        (
            row["benchmark"],
            row["initial_placement"],
            row["normalization"],
            row["reliability_floor"],
            row["topology"],
            row["grid"],
        )
        for row in rows
    }
    for benchmark in BENCHMARKS:
        for initial in INITIAL_PLACEMENTS:
            for normalization in NORMALIZATIONS:
                for floor in RELIABILITY_FLOORS:
                    for topology in TOPOLOGIES:
                        for grid in GRIDS:
                            key = (
                                benchmark,
                                initial,
                                normalization.value,
                                floor,
                                topology,
                                grid,
                            )
                            if key in completed:
                                continue
                            rows.append(
                                _run_cell(
                                    benchmark=benchmark,
                                    topology=topology,
                                    grid=grid,
                                    initial_placement=initial,
                                    normalization=normalization,
                                    reliability_min=floor,
                                    experiment="extensive",
                                )
                            )
                            _write_csv(checkpoint, rows)
                            print(f"completed {len(rows)}/1536", flush=True)
    if len(rows) != 1536:
        return []
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row["benchmark"]),
                str(row["initial_placement"]),
                str(row["normalization"]),
                f"U[{float(row['reliability_floor']):.2f}, 1.00]",
            )
        ].append(row)
    summaries = []
    for (benchmark, initial, normalization, band), group in grouped.items():
        gains = [float(row["measured_gain"]) for row in group]
        summaries.append(
            {
                "benchmark": benchmark,
                "initial_placement": initial,
                "normalization": normalization,
                "reliability_band": band,
                "mean_measured_gain": sum(gains) / len(gains),
                "median_measured_gain": sorted(gains)[len(gains) // 2],
                "minimum_measured_gain": min(gains),
                "tr_hqa_wins": sum(gain > 1.0 for gain in gains),
            }
        )
    summaries.sort(key=lambda row: (str(row["benchmark"]), -float(row["mean_measured_gain"])))
    _write_csv(output / "summary.csv", summaries)
    winners = [
        next(row for row in summaries if row["benchmark"] == benchmark) for benchmark in BENCHMARKS
    ]
    lines = [
        "# Extensive configuration sweep",
        "",
        "Every initial-placement strategy, cost normalization, and reliability floor is "
        "evaluated. The line topology uses `U[0.95, 1.00]`.",
        "",
        "| Benchmark | Initial placement | Normalization | Reliability band | Mean gain | "
        "Median gain | Minimum gain | TR-HQA wins |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    winner_template = (
        "| {benchmark} | {initial_placement} | {normalization} | {reliability_band} | "
        "{mean_measured_gain:.3f} | {median_measured_gain:.3f} | "
        "{minimum_measured_gain:.3f} | {tr_hqa_wins}/16 |"
    )
    lines.extend(winner_template.format(**row) for row in winners)
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run reproducible mapping experiments.")
    parser.add_argument("experiment", choices=("table1", "extensive"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    (run_table1 if args.experiment == "table1" else run_extensive)(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
