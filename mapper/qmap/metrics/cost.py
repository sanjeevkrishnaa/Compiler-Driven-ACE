
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from qmap.circuit.slicer import SlicedCircuit
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition

__all__ = ["CostReport", "evaluate", "per_core_activity"]

@dataclass(frozen=True, slots=True)
class CostReport:

    cost: float
    infeasible_operations: int
    hops: float
    migrations: int
    residual_operations: int
    residual_cost: float
    per_slice_cost: tuple[float, ...] = field(default=(), repr=False)
    epr_latency: float = 0.0
    path_quality: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.residual_operations == 0

    @property
    def mean_transfer_cost(self) -> float:
        return self.cost / self.infeasible_operations if self.infeasible_operations else 0.0

    @property
    def transfers(self) -> int:
        """Backward-compatible alias for :attr:`infeasible_operations`."""
        return self.infeasible_operations

    def as_record(self, *, include_hop_count: bool = True) -> dict[str, float | int | bool]:
        record: dict[str, float | int | bool] = {
            "cost": self.cost,
            "epr_latency": self.epr_latency,
            "path_quality": self.path_quality,
            "infeasible_operations": self.infeasible_operations,
            "migrations": self.migrations,
            "mean_transfer_cost": self.mean_transfer_cost,
            "residual_operations": self.residual_operations,
            "residual_cost": self.residual_cost,
            "is_complete": self.is_complete,
        }
        if include_hop_count:
            record["hops"] = self.hops
        return record

    def __str__(self) -> str:
        flag = "" if self.is_complete else f", {self.residual_operations} unresolved"
        return f"cost={self.cost:.3f} ({self.infeasible_operations} infeasible operations{flag})"

def evaluate(
    sliced: SlicedCircuit,
    partition: Partition,
    oracle: DistanceOracle,
) -> CostReport:
    if partition.n_slices != sliced.n_slices:
        raise ValueError(
            f"partition has {partition.n_slices} timeslices but the circuit has "
            f"{sliced.n_slices}"
        )
    if partition.n_qubits != sliced.n_qubits:
        raise ValueError(
            f"partition has {partition.n_qubits} qubits but the circuit has "
            f"{sliced.n_qubits}"
        )

    transfer_hops, transfer_reliability, transfer_cost = oracle.route_matrices(
        partition.route_model
    )
    transfer_epr_latency = oracle.route_epr_latency(partition.route_model)
    total_cost = 0.0
    total_hops = 0.0
    total_epr_latency = 0.0
    total_path_quality = 0.0
    total_transfers = 0
    per_slice: list[float] = [0.0] * partition.n_slices

    for t in range(partition.n_slices):
        interactions = sliced.slices[t].interactions
        if not interactions:
            continue

        previous = partition.previous_placement(t)
        current = partition.placement(t)
        pairs = np.asarray(interactions, dtype=np.intp)
        cores_a = previous[pairs[:, 0]]
        cores_b = previous[pairs[:, 1]]
        infeasible = cores_a != cores_b
        if not infeasible.any():
            continue

        # Eq. (2)/(8) charges transfers into the destination selected for the
        # operation.  Billing the source operands' mutual distance would lose
        # that destination-dependent decision entirely.
        destinations_a = current[pairs[:, 0]]
        destinations_b = current[pairs[:, 1]]
        resolved = infeasible & (destinations_a == destinations_b)
        if not resolved.any():
            continue

        sources_a = cores_a[resolved]
        sources_b = cores_b[resolved]
        destinations = destinations_a[resolved]
        slice_cost = float(
            (
                transfer_cost[sources_a, destinations]
                + transfer_cost[sources_b, destinations]
            ).sum()
        )
        per_slice[t] = slice_cost
        total_cost += slice_cost
        total_hops += float(
            (
                transfer_hops[sources_a, destinations]
                + transfer_hops[sources_b, destinations]
            ).sum()
        )
        total_epr_latency += float(
            (
                transfer_epr_latency[sources_a, destinations]
                + transfer_epr_latency[sources_b, destinations]
            ).sum()
        )

        # A resident operand has no physical path and therefore contributes
        # neither EPR latency nor an artificial empty-path quality of one.
        moved_a = sources_a != destinations
        moved_b = sources_b != destinations
        total_path_quality += float(
            transfer_reliability[sources_a[moved_a], destinations[moved_a]].sum()
            + transfer_reliability[sources_b[moved_b], destinations[moved_b]].sum()
        )
        total_transfers += int(resolved.sum())

    migrations = partition.total_migrations()

    residual_operations = 0
    residual_cost = 0.0
    for t, time_slice in enumerate(sliced.slices):
        if not time_slice.interactions:
            continue
        placement = partition.placement(t)
        pairs = np.asarray(time_slice.interactions, dtype=np.intp)
        cores_a = placement[pairs[:, 0]]
        cores_b = placement[pairs[:, 1]]
        split = cores_a != cores_b
        if split.any():
            residual_operations += int(split.sum())
            residual_cost += float(transfer_cost[cores_a[split], cores_b[split]].sum())

    return CostReport(
        cost=total_cost,
        infeasible_operations=total_transfers,
        hops=total_hops,
        migrations=migrations,
        residual_operations=residual_operations,
        residual_cost=residual_cost,
        per_slice_cost=tuple(per_slice),
        epr_latency=total_epr_latency,
        path_quality=total_path_quality,
    )

def per_core_activity(partition: Partition, n_cores: int) -> np.ndarray:
    activity = np.zeros(n_cores, dtype=np.int64)
    for t in range(partition.n_slices):
        _, sources, destinations = partition.transition(t)
        if sources.size:
            activity += np.bincount(sources, minlength=n_cores)
            activity += np.bincount(destinations, minlength=n_cores)
    return activity
