"""Process-isolated mapper execution-time measurements.

The module is deliberately runnable as ``python -m qmap.experiments.timing``.
The user-facing CLI writes a compact specification then starts this coordinator
in a fresh process.  This lets the coordinator constrain numerical-library
threads before NumPy/SciPy import, and lets :mod:`pyperf` launch its own fresh
worker processes for every timing sample.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter
from typing import Any

TIMING_PLACERS = ("HQA", "TR-HQA", "GTR-QA")
"""The three mapper variants compared by ``qmap run --measure-time``."""

_THREAD_ENVIRONMENT = {
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}


@dataclass(frozen=True, slots=True)
class TimingSpec:
    """Serializable input to an isolated mapper-timing study."""

    grid: str
    benchmark: str
    qasm: str | None
    seed: int
    reliability_min: float
    qubits_per_core: int
    reserved_ancilla: int
    topology: str
    width: int | None
    depth: int | None
    two_qubit_prob: float
    placer_config: dict[str, object]
    processes: int
    values: int
    warmups: int
    min_time: float
    output_directory: str
    stem: str
    # When supplied by a sweep, time precisely the already-derived trial
    # fixture instead of deriving a second seed path from ``seed``.
    trial_seed: int | None = None
    reliability_max: float = 1.0
    persist: bool = True
    placers: tuple[str, ...] = TIMING_PLACERS

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> TimingSpec:
        payload = json.loads(text)
        payload["placers"] = tuple(payload["placers"])
        return cls(**payload)

    def with_output_directory(self, output_directory: str) -> TimingSpec:
        return TimingSpec(**{**asdict(self), "output_directory": output_directory})


def _set_single_thread_environment() -> dict[str, str]:
    """Constrain common numerical backends before they are imported."""

    for name, value in _THREAD_ENVIRONMENT.items():
        os.environ[name] = value
    return {name: os.environ[name] for name in _THREAD_ENVIRONMENT}


def _placer_config(payload: dict[str, object]):
    from qmap.placement.base import PlacerConfig
    from qmap.placement.cost import CostNormalization

    return PlacerConfig(
        initial_placement=str(payload["initial_placement"]),
        lookahead=int(payload["lookahead"]),
        lookahead_weight=float(payload["lookahead_weight"]),
        normalization=CostNormalization(str(payload["normalization"])),
        lambda_scaling=str(payload["lambda_scaling"]),
        allow_eviction=bool(payload["allow_eviction"]),
        strict=bool(payload["strict"]),
        max_rounds=int(payload["max_rounds"]),
    )


def _prepare_setup(spec: TimingSpec):
    from qmap.architecture.reliability import ReliabilityBand
    from qmap.circuit.loader import load_qasm
    from qmap.experiments.runner import prepare_trial
    from qmap.rng import SeedSequence

    circuit = load_qasm(spec.qasm) if spec.qasm else None
    seed = (
        SeedSequence.from_seed(spec.trial_seed)
        if spec.trial_seed is not None
        else SeedSequence.from_seed(spec.seed).for_trial(
            spec.benchmark, spec.topology, spec.grid, 0
        )
    )
    return prepare_trial(
        grid=spec.grid,
        benchmark=spec.benchmark,
        seed=seed,
        reliability_band=ReliabilityBand(spec.reliability_min, spec.reliability_max),
        qubits_per_core=spec.qubits_per_core,
        reserved_ancilla=spec.reserved_ancilla,
        topology=spec.topology,
        width=spec.width,
        circuit=circuit,
        depth=spec.depth,
        two_qubit_prob=spec.two_qubit_prob,
    )


def _mapper_time_function(spec: TimingSpec, placer_name: str):
    """Return a pyperf callback with fixture preparation outside its timer."""

    from qmap.metrics.distance import DistanceOracle
    from qmap.placement.registry import build_placer

    setup = None
    config = _placer_config(spec.placer_config)

    def measure(loops: int) -> float:
        nonlocal setup
        if setup is None:
            setup = _prepare_setup(spec)

        # Start before the mapper creates its route oracle.  It therefore
        # includes model-specific preprocessing, look-ahead construction,
        # initial placement and every assignment round, but not input setup.
        started = perf_counter()
        for _ in range(loops):
            oracle = DistanceOracle(setup.architecture)
            build_placer(placer_name, config).place(
                setup.sliced, setup.architecture, oracle, setup.seed
            )
        return perf_counter() - started

    return measure


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_is_dirty() -> bool | None:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("networkx", "numpy", "pyperf", "scipy"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    return versions


def _metadata(spec: TimingSpec) -> dict[str, object]:
    setup = _prepare_setup(spec)
    return {
        "measurement_scope": (
            "mapper execution: fresh DistanceOracle and placer; includes algorithm-specific "
            "route preprocessing, look-ahead, initial placement and mapping; excludes input "
            "generation/loading, architecture construction, validation, evaluation and I/O"
        ),
        "timer": "pyperf wall-clock time (time.perf_counter)",
        "thread_environment": _set_single_thread_environment(),
        "git_revision": _git_revision(),
        "git_dirty": _git_is_dirty(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "packages": _package_versions(),
        "configuration": asdict(spec),
        "input": {
            "architecture": setup.architecture.label,
            "n_cores": setup.architecture.n_cores,
            "circuit": setup.sliced.circuit.name,
            "n_qubits": setup.sliced.n_qubits,
            "n_slices": setup.sliced.n_slices,
            "n_two_qubit_gates": setup.sliced.circuit.n_two_qubit_gates,
        },
    }


def _load_pyperf():
    """Load pyperf, tolerating a sandboxed optional psutil metadata probe."""

    try:
        import pyperf
    except ImportError as exc:
        raise RuntimeError("pyperf is required; install the project's dev dependencies") from exc

    try:
        import psutil

        psutil.boot_time()
    except (ImportError, PermissionError):
        # pyperf's timing logic is independent from psutil.  On sandboxed
        # macOS hosts, psutil's optional boot-time metadata uses a prohibited
        # sysctl call; omit only that automatic metadata collection.
        import pyperf._collect_metadata as collect_metadata

        collect_metadata.psutil = None
    return pyperf


def _row(benchmark: Any) -> dict[str, object]:
    values = benchmark.get_values()
    return {
        "placer": benchmark.get_name(),
        "samples": len(values),
        "minimum_seconds": min(values),
        "p25_seconds": benchmark.percentile(25),
        "median_seconds": benchmark.median(),
        "p75_seconds": benchmark.percentile(75),
        "mean_seconds": benchmark.mean(),
        "stdev_seconds": benchmark.stdev() if len(values) > 1 else 0.0,
        "p95_seconds": benchmark.percentile(95),
        "maximum_seconds": max(values),
    }


def _write_results(spec: TimingSpec, benchmarks, metadata: dict[str, object]) -> None:
    import pyperf

    directory = Path(spec.output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = [_row(benchmark) for benchmark in benchmarks]
    suite = pyperf.BenchmarkSuite(benchmarks)
    suite.dump(str(directory / f"{spec.stem}.pyperf.json"))

    with (directory / f"{spec.stem}.timing.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (directory / f"{spec.stem}.timing.json").write_text(
        json.dumps({"summary": rows, "metadata": metadata}, indent=2), encoding="utf-8"
    )
    (directory / f"{spec.stem}.timing.metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def _print_summary(
    rows: list[dict[str, object]], directory: Path, stem: str, *, persist: bool
) -> None:
    print("\nmapper execution time (wall clock; input setup and I/O excluded)")
    print(f"{'placer':<8} {'samples':>8} {'median (ms)':>14} {'mean (ms)':>12} {'p95 (ms)':>11}")
    print("-" * 61)
    for row in rows:
        print(
            f"{row['placer']:<8} {row['samples']:8d} "
            f"{1000 * row['median_seconds']:14.3f} "
            f"{1000 * row['mean_seconds']:12.3f} "
            f"{1000 * row['p95_seconds']:11.3f}"
        )
    if persist:
        print(f"wrote pyperf raw samples: {directory / f'{stem}.pyperf.json'}")
        print(f"wrote timing summary:     {directory / f'{stem}.timing.csv'}")


def run(spec: TimingSpec, spec_path: str) -> int:
    """Coordinate the same pyperf study in parent and worker processes."""

    pyperf = _load_pyperf()
    metadata = _metadata(spec)
    runner = pyperf.Runner(
        values=spec.values,
        processes=spec.processes,
        warmups=spec.warmups,
        min_time=spec.min_time,
        # pyperf's raw metadata schema accepts scalar values only.  The full
        # structured reproducibility record is written beside its JSON suite.
        metadata={"description": "QMap mapper execution time"},
        show_name=False,
        program_args=("-m", "qmap.experiments.timing", "--spec", spec_path),
    )

    benchmarks = []
    for placer in spec.placers:
        benchmark = runner.bench_time_func(placer, _mapper_time_function(spec, placer))
        if benchmark is not None:
            benchmarks.append(benchmark)

    if runner.args.worker:
        return 0

    if spec.persist:
        _write_results(spec, benchmarks, metadata)
    rows = [_row(benchmark) for benchmark in benchmarks]
    _print_summary(rows, Path(spec.output_directory), spec.stem, persist=spec.persist)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    parsed, runner_arguments = parser.parse_known_args(argv)

    # ``pyperf.Runner`` owns its command-line parser.  Leave it only pyperf's
    # flags while retaining the specification path in ``program_args`` above.
    sys.argv = [sys.argv[0], *runner_arguments]
    _set_single_thread_environment()
    spec = TimingSpec.from_json(Path(parsed.spec).read_text(encoding="utf-8"))
    return run(spec, parsed.spec)


if __name__ == "__main__":
    raise SystemExit(main())
