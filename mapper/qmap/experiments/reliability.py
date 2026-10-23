
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qmap.architecture.reliability import ReliabilityBand, default_bands
from qmap.experiments.runner import TrialResult, prepare_trial, run_trials
from qmap.placement.base import PlacerConfig
from qmap.rng import SeedSequence

__all__ = [
    "ABLATION_PLACERS",
    "RELIABILITY_PLACERS",
    "ReliabilityConfig",
    "run_ablation",
    "run_reliability",
]

logger = logging.getLogger(__name__)

RELIABILITY_PLACERS: tuple[str, ...] = ("HQA", "T-HQA", "TR-HQA", "GTR-QA")
"""Arms for Section 6.3: baseline, both refinements, and the greedy variant."""

ABLATION_PLACERS: tuple[str, ...] = ("HQA", "HQA-NL", "T-HQA", "TR-HQA")
"""Arms for Section 6.4.

Adds ``HQA-NL`` to the Figure 7 set so that look-ahead and topology awareness are
ablated as independent variables rather than confounded (decision D2).
"""

@dataclass(frozen=True)
class ReliabilityConfig:

    grid: str = "4x4"
    benchmark: str = "qft"
    placers: tuple[str, ...] = RELIABILITY_PLACERS
    qubits_per_core: int = 16
    reserved_ancilla: int = 2
    bands: tuple[ReliabilityBand, ...] = field(default_factory=default_bands)
    repeats: int = 10
    placer_config: PlacerConfig = field(default_factory=PlacerConfig)
    topology: str = "mesh"
    width: int | None = None

    def describe(self) -> dict[str, object]:
        return {
            "grid": self.grid,
            "benchmark": self.benchmark,
            "placers": list(self.placers),
            "qubits_per_core": self.qubits_per_core,
            "reserved_ancilla": self.reserved_ancilla,
            "bands": [band.label for band in self.bands],
            "repeats": self.repeats,
            "topology": self.topology,
            "width": self.width,
            "placer_config": self.placer_config.describe(),
        }

def _sweep(
    config: ReliabilityConfig, seed: SeedSequence, label: str
) -> list[TrialResult]:
    results: list[TrialResult] = []

    for band in config.bands:
        for repeat in range(config.repeats):
            trial_seed = seed.for_trial(
                label, config.benchmark, config.grid, band.label, repeat
            )
            setup = prepare_trial(
                grid=config.grid,
                benchmark=config.benchmark,
                seed=trial_seed,
                reliability_band=band,
                qubits_per_core=config.qubits_per_core,
                reserved_ancilla=config.reserved_ancilla,
                topology=config.topology,
                width=config.width,
            )
            logger.info(
                "%s: band %s repeat %d/%d (%d cores, %d qubits)",
                label,
                band.label,
                repeat + 1,
                config.repeats,
                setup.architecture.n_cores,
                setup.sliced.n_qubits,
            )
            results.extend(
                run_trials(
                    setup,
                    config.placers,
                    config.placer_config,
                    benchmark=config.benchmark,
                    repeat=repeat,
                    reliability_band=band.label,
                )
            )
    return results

def run_reliability(config: ReliabilityConfig, seed: SeedSequence) -> list[TrialResult]:
    return _sweep(config, seed, "reliability")

def run_ablation(config: ReliabilityConfig, seed: SeedSequence) -> list[TrialResult]:
    return _sweep(config, seed, "ablation")
