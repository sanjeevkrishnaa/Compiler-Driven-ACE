
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qmap.architecture.reliability import ReliabilityBand
from qmap.experiments.runner import TrialResult, prepare_trial, run_trials
from qmap.placement.base import PlacerConfig
from qmap.placement.registry import DEFAULT_PLACERS
from qmap.rng import SeedSequence

__all__ = ["ScalingConfig", "run_scaling"]

logger = logging.getLogger(__name__)

DEFAULT_GRIDS: tuple[str, ...] = ("2x2", "4x4", "8x4", "8x8")
"""Mesh sizes from Table 1: 4, 16, 32 and 64 cores."""

DEFAULT_BENCHMARKS: tuple[str, ...] = ("qft", "cuccaro", "draper", "random")
"""Circuit families from Table 1."""

@dataclass(frozen=True)
class ScalingConfig:

    grids: tuple[str, ...] = DEFAULT_GRIDS
    benchmarks: tuple[str, ...] = DEFAULT_BENCHMARKS
    placers: tuple[str, ...] = DEFAULT_PLACERS
    qubits_per_core: int = 8
    reserved_ancilla: int = 2
    reliability_min: float = 0.4
    repeats: int = 3
    placer_config: PlacerConfig = field(default_factory=PlacerConfig)
    topology: str = "mesh"

    def describe(self) -> dict[str, object]:
        return {
            "experiment": "scaling",
            "grids": list(self.grids),
            "benchmarks": list(self.benchmarks),
            "placers": list(self.placers),
            "qubits_per_core": self.qubits_per_core,
            "reserved_ancilla": self.reserved_ancilla,
            "reliability_min": self.reliability_min,
            "repeats": self.repeats,
            "topology": self.topology,
            "placer_config": self.placer_config.describe(),
        }

def run_scaling(config: ScalingConfig, seed: SeedSequence) -> list[TrialResult]:
    band = ReliabilityBand(config.reliability_min, 1.0)
    results: list[TrialResult] = []

    for grid in config.grids:
        for benchmark in config.benchmarks:
            for repeat in range(config.repeats):
                trial_seed = seed.for_trial(benchmark, config.topology, grid, repeat)

                setup = prepare_trial(
                    grid=grid,
                    benchmark=benchmark,
                    seed=trial_seed,
                    reliability_band=band,
                    qubits_per_core=config.qubits_per_core,
                    reserved_ancilla=config.reserved_ancilla,
                    topology=config.topology,
                )
                logger.info(
                    "scaling: %s on %s (%d cores, %d qubits, %d slices) repeat %d/%d",
                    benchmark,
                    setup.architecture.label,
                    setup.architecture.n_cores,
                    setup.sliced.n_qubits,
                    setup.sliced.n_slices,
                    repeat + 1,
                    config.repeats,
                )
                results.extend(
                    run_trials(
                        setup,
                        config.placers,
                        config.placer_config,
                        benchmark=benchmark,
                        repeat=repeat,
                        reliability_band=band.label,
                    )
                )
    return results
