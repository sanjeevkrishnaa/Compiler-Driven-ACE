
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.architecture.reliability import ReliabilityBand
from qmap.circuit.ir import Circuit
from qmap.circuit.slicer import SlicedCircuit, slice_circuit
from qmap.metrics.cost import CostReport, evaluate
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition
from qmap.placement.base import PlacerConfig
from qmap.placement.registry import build_placer
from qmap.rng import SeedSequence
from qmap.validation import validate_partition

__all__ = ["TrialResult", "TrialSetup", "prepare_trial", "run_trial", "run_trials"]

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class TrialSetup:

    architecture: MulticoreArchitecture
    oracle: DistanceOracle
    sliced: SlicedCircuit
    seed: SeedSequence

@dataclass(frozen=True)
class TrialResult:

    placer: str
    benchmark: str
    circuit: str
    grid: str
    n_cores: int
    n_qubits: int
    n_slices: int
    n_two_qubit_gates: int
    reliability_band: str
    repeat: int
    cost: CostReport
    runtime_seconds: float
    evictions: int
    rounds: int
    partition: Partition | None = field(default=None, repr=False)

    def as_record(self, *, include_hop_count: bool = True) -> dict[str, object]:
        return {
            "placer": self.placer,
            "benchmark": self.benchmark,
            "circuit": self.circuit,
            "grid": self.grid,
            "n_cores": self.n_cores,
            "n_qubits": self.n_qubits,
            "n_slices": self.n_slices,
            "n_two_qubit_gates": self.n_two_qubit_gates,
            "reliability_band": self.reliability_band,
            "repeat": self.repeat,
            "runtime_seconds": self.runtime_seconds,
            "evictions": self.evictions,
            "rounds": self.rounds,
            **self.cost.as_record(include_hop_count=include_hop_count),
        }

def prepare_trial(
    *,
    grid: str,
    benchmark: str,
    seed: SeedSequence,
    reliability_band: ReliabilityBand,
    qubits_per_core: int,
    reserved_ancilla: int,
    topology: str = "mesh",
    width: int | None = None,
    circuit: Circuit | None = None,
    depth: int | None = None,
    two_qubit_prob: float = 0.5,
) -> TrialSetup:
    architecture = MulticoreArchitecture.build(
        grid,
        qubits_per_core=qubits_per_core,
        reserved_ancilla=reserved_ancilla,
        seed=seed,
        reliability_band=reliability_band,
        topology=topology,
    )

    if circuit is None:
        from qmap.circuit.generators import generate

        target = width if width is not None else architecture.workload_width
        circuit = generate(
            benchmark,
            target,
            seed=seed,
            depth=depth,
            two_qubit_prob=two_qubit_prob,
        )

    return TrialSetup(
        architecture=architecture,
        oracle=DistanceOracle(architecture),
        sliced=slice_circuit(circuit),
        seed=seed,
    )

def run_trial(
    setup: TrialSetup,
    placer_name: str,
    config: PlacerConfig,
    *,
    benchmark: str,
    repeat: int = 0,
    reliability_band: str = "",
    keep_partition: bool = False,
    validate: bool = True,
) -> TrialResult:
    placer = build_placer(placer_name, config)
    outcome = placer.place(setup.sliced, setup.architecture, setup.oracle, setup.seed)

    if validate:
        validate_partition(outcome.partition, setup.sliced, setup.architecture)

    cost = evaluate(setup.sliced, outcome.partition, setup.oracle)

    return TrialResult(
        placer=placer_name,
        benchmark=benchmark,
        circuit=setup.sliced.circuit.name,
        grid="x".join(map(str, setup.architecture.dimensions)),
        n_cores=setup.architecture.n_cores,
        n_qubits=setup.sliced.n_qubits,
        n_slices=setup.sliced.n_slices,
        n_two_qubit_gates=setup.sliced.circuit.n_two_qubit_gates,
        reliability_band=reliability_band,
        repeat=repeat,
        cost=cost,
        runtime_seconds=outcome.runtime_seconds,
        evictions=outcome.evictions,
        rounds=outcome.rounds,
        partition=outcome.partition if keep_partition else None,
    )

def run_trials(
    setup: TrialSetup,
    placer_names: tuple[str, ...],
    config: PlacerConfig,
    *,
    benchmark: str,
    repeat: int = 0,
    reliability_band: str = "",
    keep_partition: bool = False,
) -> list[TrialResult]:
    results: list[TrialResult] = []
    for name in placer_names:
        logger.debug(
            "trial: placer=%s circuit=%s grid=%s repeat=%d",
            name,
            setup.sliced.circuit.name,
            setup.architecture.label,
            repeat,
        )
        results.append(
            run_trial(
                setup,
                name,
                config,
                benchmark=benchmark,
                repeat=repeat,
                reliability_band=reliability_band,
                keep_partition=keep_partition,
            )
        )
    return results
