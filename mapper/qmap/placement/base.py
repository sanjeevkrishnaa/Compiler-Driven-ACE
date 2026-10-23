
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.circuit.slicer import SlicedCircuit
from qmap.exceptions import UnplaceableOperationError
from qmap.metrics.distance import DistanceOracle
from qmap.metrics.interaction import DEFAULT_HORIZON, LookaheadWeights
from qmap.partition import Partition
from qmap.placement.assignment import AssignmentSolver
from qmap.placement.cost import (
    DEFAULT_LOOKAHEAD_WEIGHT,
    DEFAULT_NORMALIZATION,
    CostNormalization,
    TransferModel,
    build_cost_matrix,
)
from qmap.placement.initial import DEFAULT_INITIAL_PLACEMENT, initial_placement
from qmap.placement.lambda_scaling import DEFAULT_LAMBDA_SCALING, resolve_lambda
from qmap.rng import SeedSequence

__all__ = ["PlacementResult", "Placer", "PlacerConfig"]

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class PlacerConfig:

    initial_placement: str = DEFAULT_INITIAL_PLACEMENT
    lookahead: int = DEFAULT_HORIZON
    lookahead_weight: float = DEFAULT_LOOKAHEAD_WEIGHT
    normalization: CostNormalization = DEFAULT_NORMALIZATION
    lambda_scaling: str = DEFAULT_LAMBDA_SCALING
    allow_eviction: bool = True
    strict: bool = False
    max_rounds: int = 4

    def describe(self) -> dict[str, object]:
        return {
            "initial_placement": self.initial_placement,
            "lookahead": self.lookahead,
            "lookahead_weight": self.lookahead_weight,
            "normalization": self.normalization.value,
            "lambda_scaling": self.lambda_scaling,
            "allow_eviction": self.allow_eviction,
            "strict": self.strict,
            "max_rounds": self.max_rounds,
        }

@dataclass(frozen=True, slots=True)
class PlacementResult:

    partition: Partition
    placer: str
    runtime_seconds: float
    unplaced_operations: int = 0
    evictions: int = 0
    rounds: int = 0

    def describe(self) -> dict[str, object]:
        return {
            "placer": self.placer,
            "runtime_seconds": self.runtime_seconds,
            "unplaced_operations": self.unplaced_operations,
            "evictions": self.evictions,
            "rounds": self.rounds,
        }

class Placer(ABC):

    name: str

    transfer_model: TransferModel

    # Mapping cost and physical routing are separate decisions. Existing
    # algorithms keep conventional shortest-hop routing; a placer may opt in
    # to another route without changing the matrix used for assignment.
    physical_route_model: str = "shortest"

    uses_lookahead: bool = True

    description: str = ""

    def __init__(self, config: PlacerConfig | None = None) -> None:
        self.config = config or PlacerConfig()

    @abstractmethod
    def make_solver(self) -> AssignmentSolver:
        pass

    def place(
        self,
        sliced: SlicedCircuit,
        architecture: MulticoreArchitecture,
        oracle: DistanceOracle,
        seed: SeedSequence,
    ) -> PlacementResult:
        capacity = architecture.capacity
        n_cores = architecture.n_cores
        solver = self.make_solver()

        weights = (
            LookaheadWeights(sliced, self.config.lookahead)
            if self.uses_lookahead and self.config.lookahead > 0
            else None
        )

        effective_lambda = resolve_lambda(
            self.config.lambda_scaling,
            self.config.lookahead_weight,
            self.transfer_model.matrix(oracle),
        )

        start = time.perf_counter()

        placement = initial_placement(
            self.config.initial_placement,
            sliced.n_qubits,
            n_cores,
            architecture.workload_capacity,
            capacity,
            seed,
            sliced=sliced,
            oracle=oracle,
        )
        initial = placement.copy()
        placements: list[np.ndarray] = []

        unplaced_total = 0
        eviction_total = 0
        round_total = 0

        # ``initial`` is Algorithm 1's A_0.  Every real circuit timeslice,
        # including slice zero in the Python representation, is mapped.
        for t in range(sliced.n_slices):
            placement, stats = self._place_timeslice(
                t, sliced, placement, oracle, solver, capacity, n_cores, weights,
                effective_lambda,
            )
            placements.append(placement.copy())
            unplaced_total += stats[0]
            eviction_total += stats[1]
            round_total += stats[2]

        runtime = time.perf_counter() - start

        if unplaced_total:
            logger.warning(
                "%s: %d operation(s) could not be placed on %s (circuit %s); "
                "they are reported as residuals",
                self.name,
                unplaced_total,
                architecture.label,
                sliced.circuit.name,
            )

        return PlacementResult(
            partition=Partition.from_sequence(
                placements,
                initial_assignment=initial,
                route_model=self.physical_route_model,
            ),
            placer=self.name,
            runtime_seconds=runtime,
            unplaced_operations=unplaced_total,
            evictions=eviction_total,
            rounds=round_total,
        )

    def _place_timeslice(
        self,
        t: int,
        sliced: SlicedCircuit,
        previous: np.ndarray,
        oracle: DistanceOracle,
        solver: AssignmentSolver,
        capacity: int,
        n_cores: int,
        weights: LookaheadWeights | None,
        effective_lambda: float,
    ) -> tuple[np.ndarray, tuple[int, int, int]]:
        placement = previous.copy()
        interactions = sliced.slices[t].interactions
        if not interactions:
            return placement, (0, 0, 0)

        pending = [
            i for i, (a, b) in enumerate(interactions) if placement[a] != placement[b]
        ]
        if not pending:
            return placement, (0, 0, 0)

        evictions = 0
        rounds = 0
        max_rounds = max(1, self.config.max_rounds * len(pending))

        while pending and rounds < max_rounds:
            rounds += 1
            subset = tuple(interactions[i] for i in pending)

            cost = build_cost_matrix(
                subset,
                placement,
                oracle,
                self.transfer_model,
                capacity=capacity,
                weights=weights,
                timeslice=t,
                lookahead_weight=effective_lambda,
                normalization=self.config.normalization,
            )
            occupancy = np.bincount(placement, minlength=n_cores)
            required = self._required_slots(subset, placement, n_cores)

            assignment = solver.solve(cost, occupancy, required, capacity)

            if not assignment:

                if not self.config.allow_eviction:
                    break
                freed = self._evict(subset, placement, oracle, capacity, n_cores, sliced, t)
                evictions += freed
                if freed == 0:
                    break
                continue

            assigned: set[int] = set()
            for row, core in zip(assignment.operations, assignment.cores, strict=True):
                q_alpha, q_beta = subset[int(row)]
                placement[q_alpha] = core
                placement[q_beta] = core
                assigned.add(int(row))

            pending = [op for i, op in enumerate(pending) if i not in assigned]

        if pending and self.config.strict:
            raise UnplaceableOperationError(
                f"{self.name}: {len(pending)} operation(s) in timeslice {t} of "
                f"circuit {sliced.circuit.name!r} could not be placed"
            )

        return placement, (len(pending), evictions, rounds)

    @staticmethod
    def _required_slots(
        interactions: tuple[tuple[int, int], ...],
        placement: np.ndarray,
        n_cores: int,
    ) -> np.ndarray:
        required = np.full((len(interactions), n_cores), 2, dtype=np.int64)
        for row, (q_alpha, q_beta) in enumerate(interactions):
            required[row, placement[q_alpha]] -= 1
            required[row, placement[q_beta]] -= 1
        return required

    def _evict(
        self,
        interactions: tuple[tuple[int, int], ...],
        placement: np.ndarray,
        oracle: DistanceOracle,
        capacity: int,
        n_cores: int,
        sliced: SlicedCircuit,
        t: int,
    ) -> int:
        transfer = self.transfer_model.matrix(oracle)
        active = sliced.slices[t].active_qubits
        occupancy = np.bincount(placement, minlength=n_cores)

        wanted: set[int] = set()
        for q_alpha, q_beta in interactions:
            wanted.add(int(placement[q_alpha]))
            wanted.add(int(placement[q_beta]))

        moved = 0
        for core in sorted(wanted):
            if occupancy[core] + 2 <= capacity:
                continue
            idle = [
                q
                for q in np.flatnonzero(placement == core)
                if int(q) not in active
            ]
            if not idle:
                continue

            room = np.flatnonzero(occupancy + 1 <= capacity)
            room = room[room != core]
            if room.size == 0:
                continue

            destination = int(room[np.argmin(transfer[core, room])])
            qubit = int(idle[0])

            placement[qubit] = destination
            occupancy[core] -= 1
            occupancy[destination] += 1
            moved += 1

        return moved

    def __str__(self) -> str:
        return f"{self.name}({self.transfer_model.value})"
