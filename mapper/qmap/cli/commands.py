
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.architecture.reliability import ReliabilityBand, parse_bands
from qmap.architecture.topology import list_topologies
from qmap.circuit.generators import list_benchmarks
from qmap.exceptions import ConfigurationError
from qmap.experiments.reliability import (
    ABLATION_PLACERS,
    ReliabilityConfig,
    run_ablation,
    run_reliability,
)
from qmap.experiments.runner import TrialResult, prepare_trial, run_trials
from qmap.experiments.scaling import ScalingConfig, run_scaling
from qmap.experiments.timing import TIMING_PLACERS, TimingSpec
from qmap.io.results import ResultWriter, collect_metadata, summarise
from qmap.io.traces import build_trace, trace_summary, write_trace
from qmap.placement.base import PlacerConfig
from qmap.placement.cost import CostNormalization
from qmap.placement.initial import list_initial_placements
from qmap.placement.registry import DEFAULT_PLACERS, describe_placers
from qmap.rng import SeedSequence

__all__ = [
    "command_ablation",
    "command_describe",
    "command_list",
    "command_reliability",
    "command_run",
    "command_scaling",
]

logger = logging.getLogger(__name__)

def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())

def _placer_config(args: argparse.Namespace) -> PlacerConfig:
    return PlacerConfig(
        initial_placement=args.initial_placement,
        normalization=CostNormalization(args.cost_normalization),
        lookahead=args.lookahead,
        lookahead_weight=args.lookahead_weight,
        lambda_scaling=args.lambda_scaling,
        allow_eviction=not args.no_eviction,
    )

def _output_directory(args: argparse.Namespace, default: str) -> Path:
    return Path(args.output) if args.output else Path("results") / default

def _report(
    results: list[TrialResult], *, include_hop_count: bool = False
) -> list[dict[str, Any]]:
    summary = summarise(results, include_hop_count=include_hop_count)
    if not summary:
        print("no results")
        return summary

    header = (
        f"{'benchmark':<10} {'grid':>6} {'band':>12} {'placer':<8} "
        f"{'cost':>12} {'EPR latency':>12} {'path quality':>12} {'infeasible':>10}"
    )
    if include_hop_count:
        header += f" {'hops':>10}"
    header += f" {'runtime(s)':>11} {'gain':>7}"
    print(header)
    print("-" * len(header))
    for row in summary:
        gain = row["gain_vs_HQA"]
        gain_text = f"{gain:6.2f}x" if gain is not None else "     --"
        flag = "" if row["all_complete"] else f"  [{row['residual_operations']} residual]"
        line = (
            f"{row['benchmark']:<10} {row['grid']:>6} {row['reliability_band']:>12} "
            f"{row['placer']:<8} {row['mean_cost']:12.2f} "
            f"{row['mean_epr_latency']:12.2f} {row['mean_path_quality']:12.2f} "
            f"{row['mean_infeasible_operations']:10.0f}"
        )
        if include_hop_count:
            line += f" {row['mean_hops']:10.2f}"
        line += f" {row['min_runtime_seconds']:11.4f} {gain_text}{flag}"
        print(line)
    return summary

def _persist(
    args: argparse.Namespace,
    results: list[TrialResult],
    summary: list[dict[str, Any]],
    *,
    default_stem: str,
    configuration: dict[str, Any],
) -> None:
    if args.no_write:
        return

    directory = _output_directory(args, default_stem)
    stem = args.stem or default_stem
    metadata = collect_metadata(
        seed=args.seed,
        seed_path=str(args.seed),
        configuration=configuration,
    )
    metadata["configuration"]["hop_count"] = args.hop_count
    written = ResultWriter(directory=directory, stem=stem).write(
        results, metadata, include_hop_count=args.hop_count
    )
    for label, path in written.items():
        print(f"wrote {label}: {path}")

    if args.plot:
        _plot(default_stem, summary, directory)

def _plot(kind: str, summary: list[dict[str, Any]], directory: Path) -> None:
    from qmap.viz import plot_ablation, plot_reliability, plot_runtime, plot_scaling

    paths: list[Path] = []
    if kind == "scaling":
        for benchmark in sorted({str(row["benchmark"]) for row in summary}):
            paths.append(plot_scaling(summary, directory, benchmark=benchmark))
            paths.append(plot_runtime(summary, directory, benchmark=benchmark))
    elif kind == "reliability":
        paths.append(plot_reliability(summary, directory))
    elif kind == "ablation":
        paths.append(plot_ablation(summary, directory))
    for path in paths:
        print(f"wrote figure: {path}")

def command_run(args: argparse.Namespace) -> int:
    seed = SeedSequence.from_seed(args.seed)
    band = ReliabilityBand(args.reliability_min, 1.0)
    placers = _split(args.placers)

    if args.measure_time:
        if args.trace:
            raise ConfigurationError("--trace cannot be combined with --measure-time")
        if args.hop_count:
            raise ConfigurationError(
                "--hop-count cannot be combined with --measure-time; timing intentionally "
                "excludes mapping evaluation"
            )
        if args.plot:
            raise ConfigurationError("--plot cannot be combined with --measure-time")
        if args.timing_processes < 1 or args.timing_values < 1 or args.timing_warmups < 0:
            raise ConfigurationError("timing process/value counts must be positive")
        if args.timing_min_time <= 0.0:
            raise ConfigurationError("--timing-min-time must be positive")
        try:
            import pyperf  # noqa: F401
        except ImportError as exc:
            raise ConfigurationError(
                "--measure-time requires pyperf; install the project's dev dependencies"
            ) from exc

        requested = set(placers)
        defaults = set(DEFAULT_PLACERS)
        allowed = set(TIMING_PLACERS)
        if requested not in (defaults, allowed):
            raise ConfigurationError(
                "--measure-time always compares HQA, TR-HQA and GTR-QA; "
                "omit --placers or set it to HQA,TR-HQA,GTR-QA"
            )

        benchmark = args.benchmark or "qasm"
        output = _output_directory(args, "timing")
        spec = TimingSpec(
            grid=args.grid,
            benchmark=benchmark,
            qasm=str(Path(args.qasm).resolve()) if args.qasm else None,
            seed=args.seed,
            reliability_min=args.reliability_min,
            qubits_per_core=args.qubits_per_core,
            reserved_ancilla=args.reserved_ancilla,
            topology=args.topology,
            width=args.width,
            depth=args.depth,
            two_qubit_prob=args.two_qubit_prob,
            placer_config=_placer_config(args).describe(),
            processes=args.timing_processes,
            values=args.timing_values,
            warmups=args.timing_warmups,
            min_time=args.timing_min_time,
            output_directory=str(output),
            stem=args.stem or "timing",
            persist=not args.no_write,
        )
        if args.no_write:
            with tempfile.TemporaryDirectory(prefix="qmap-timing-") as temporary:
                temporary_spec = spec.with_output_directory(temporary)
                return _run_timing_subprocess(temporary_spec)
        return _run_timing_subprocess(spec)

    circuit = None
    benchmark = args.benchmark or "qasm"
    if args.qasm:
        from qmap.circuit.loader import load_qasm

        circuit = load_qasm(args.qasm)

    trial_seed = seed.for_trial(benchmark, args.topology, args.grid, 0)
    setup = prepare_trial(
        grid=args.grid,
        benchmark=benchmark,
        seed=trial_seed,
        reliability_band=band,
        qubits_per_core=args.qubits_per_core,
        reserved_ancilla=args.reserved_ancilla,
        topology=args.topology,
        width=args.width,
        circuit=circuit,
        depth=args.depth,
        two_qubit_prob=args.two_qubit_prob,
    )

    print(f"architecture : {setup.architecture}")
    print(f"circuit      : {setup.sliced.circuit}")
    print(f"timeslices   : {setup.sliced.n_slices}")
    print()

    results = run_trials(
        setup,
        placers,
        _placer_config(args),
        benchmark=benchmark,
        reliability_band=band.label,
        keep_partition=bool(args.trace),
    )
    summary = _report(results, include_hop_count=args.hop_count)

    if args.trace:
        best = min(results, key=lambda r: r.cost.cost)
        if best.partition is not None:
            transfers = build_trace(best.partition, setup.architecture, setup.oracle)
            written = write_trace(
                transfers,
                Path(args.trace),
                summary=trace_summary(transfers, setup.architecture),
            )
            for label, path in written.items():
                print(f"wrote {label}: {path} ({len(transfers)} transfers, "
                      f"placer {best.placer})")

    _persist(
        args,
        results,
        summary,
        default_stem="run",
        configuration={
            "command": "run",
            "grid": args.grid,
            "benchmark": benchmark,
            "qasm": args.qasm,
            "placers": list(placers),
            "reliability_min": args.reliability_min,
            "qubits_per_core": args.qubits_per_core,
            "reserved_ancilla": args.reserved_ancilla,
            "topology": args.topology,
            "placer_config": _placer_config(args).describe(),
        },
    )
    return 0


def _run_timing_subprocess(spec: TimingSpec) -> int:
    """Run the pyperf coordinator in a clean process before NumPy/SciPy import."""

    with tempfile.TemporaryDirectory(prefix="qmap-timing-spec-") as temporary:
        spec_path = Path(temporary) / "timing-spec.json"
        spec_path.write_text(spec.to_json(), encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "qmap.experiments.timing",
            "--spec",
            str(spec_path),
            "--processes",
            str(spec.processes),
            "--values",
            str(spec.values),
            "--warmups",
            str(spec.warmups),
            "--min-time",
            str(spec.min_time),
        ]
        completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise ConfigurationError(f"mapper timing failed with exit status {completed.returncode}")
    return 0

def command_scaling(args: argparse.Namespace) -> int:
    config = ScalingConfig(
        grids=_split(args.grids),
        benchmarks=_split(args.benchmarks),
        placers=_split(args.placers),
        qubits_per_core=args.qubits_per_core,
        reserved_ancilla=args.reserved_ancilla,
        reliability_min=args.reliability_min,
        repeats=args.repeats,
        placer_config=_placer_config(args),
        topology=args.topology,
    )
    results = run_scaling(config, SeedSequence.from_seed(args.seed))
    summary = _report(results, include_hop_count=args.hop_count)
    _persist(
        args, results, summary, default_stem="scaling", configuration=config.describe()
    )
    return 0

def _reliability_config(args: argparse.Namespace, placers: tuple[str, ...]) -> ReliabilityConfig:
    return ReliabilityConfig(
        grid=args.grid,
        benchmark=args.benchmark,
        placers=placers,
        qubits_per_core=args.qubits_per_core,
        reserved_ancilla=args.reserved_ancilla,
        bands=parse_bands(args.bands),
        repeats=args.repeats,
        placer_config=_placer_config(args),
        topology=args.topology,
        width=args.width,
    )

def command_reliability(args: argparse.Namespace) -> int:
    config = _reliability_config(args, _split(args.placers))
    results = run_reliability(config, SeedSequence.from_seed(args.seed))
    summary = _report(results, include_hop_count=args.hop_count)
    _persist(
        args,
        results,
        summary,
        default_stem="reliability",
        configuration={"experiment": "reliability", **config.describe()},
    )
    return 0

def command_ablation(args: argparse.Namespace) -> int:

    chosen = _split(args.placers)
    placers = chosen if set(chosen) != set(DEFAULT_PLACERS) else ABLATION_PLACERS
    config = _reliability_config(args, placers)
    results = run_ablation(config, SeedSequence.from_seed(args.seed))
    summary = _report(results, include_hop_count=args.hop_count)
    _persist(
        args,
        results,
        summary,
        default_stem="ablation",
        configuration={"experiment": "ablation", **config.describe()},
    )
    return 0

def command_list(args: argparse.Namespace) -> int:
    registry = args.registry

    if registry in ("placers", "all"):
        print("algorithms:")
        for name, description in describe_placers().items():
            print(f"  {name:<8} {description}")
    if registry in ("benchmarks", "all"):
        print("\nbenchmarks:" if registry == "all" else "benchmarks:")
        for name in list_benchmarks():
            print(f"  {name}")
    if registry in ("topologies", "all"):
        print("\ntopologies:" if registry == "all" else "topologies:")
        for name in list_topologies():
            print(f"  {name}")
    if registry in ("initial-placements", "all"):
        print("\ninitial placements:" if registry == "all" else "initial placements:")
        for name in list_initial_placements():
            print(f"  {name}")
    return 0

def command_describe(args: argparse.Namespace) -> int:
    architecture = MulticoreArchitecture.build(
        args.grid,
        qubits_per_core=args.qubits_per_core,
        reserved_ancilla=args.reserved_ancilla,
        seed=SeedSequence.from_seed(args.seed),
        reliability_band=ReliabilityBand(args.reliability_min, 1.0),
        topology=args.topology,
    )
    from qmap.metrics.distance import DistanceOracle

    oracle = DistanceOracle(architecture)
    description = architecture.describe()

    print(f"{architecture}\n")
    for key, value in description.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for sub_key, sub_value in value.items():
                print(f"    {sub_key}: {sub_value}")
        else:
            print(f"  {key}: {value}")
    print("\n  distances:")
    for key, value in oracle.summary().items():
        print(f"    {key}: {value:.4f}")
    return 0

def dispatch(args: argparse.Namespace) -> int:
    commands = {
        "run": command_run,
        "scaling": command_scaling,
        "reliability": command_reliability,
        "ablation": command_ablation,
        "list": command_list,
        "describe": command_describe,
    }
    handler = commands.get(args.command)
    if handler is None:
        raise ConfigurationError(f"unknown command {args.command!r}")
    return handler(args)
