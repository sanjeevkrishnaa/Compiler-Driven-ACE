
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.circuit.slicer import SlicedCircuit
from qmap.exceptions import InvalidPartitionError
from qmap.partition import Partition

__all__ = ["ValidationReport", "check_colocation", "validate_partition"]

@dataclass(frozen=True, slots=True)
class ValidationReport:

    n_slices: int
    n_qubits: int
    max_occupancy: int
    capacity: int
    uncolocated_operations: int

    @property
    def is_complete(self) -> bool:
        return self.uncolocated_operations == 0

def validate_partition(
    partition: Partition,
    sliced: SlicedCircuit,
    architecture: MulticoreArchitecture,
) -> ValidationReport:
    if partition.n_slices != sliced.n_slices:
        raise InvalidPartitionError(
            f"partition has {partition.n_slices} timeslices, circuit has {sliced.n_slices}"
        )
    if partition.n_qubits != sliced.n_qubits:
        raise InvalidPartitionError(
            f"partition has {partition.n_qubits} qubits, circuit has {sliced.n_qubits}"
        )

    assignments = partition.assignments
    if assignments.size:
        lo, hi = int(assignments.min()), int(assignments.max())
        if lo < 0 or hi >= architecture.n_cores:
            raise InvalidPartitionError(
                f"partition references core indices [{lo}, {hi}] but "
                f"{architecture.label} has {architecture.n_cores} cores"
            )

    capacity = architecture.capacity
    max_occupancy = 0
    if partition.initial_assignment is not None:
        initial_occupancy = np.bincount(
            partition.initial_assignment, minlength=architecture.n_cores
        )
        initial_peak = int(initial_occupancy.max()) if initial_occupancy.size else 0
        max_occupancy = max(max_occupancy, initial_peak)
        if initial_peak > capacity:
            core = int(np.argmax(initial_occupancy))
            raise InvalidPartitionError(
                f"initial placement: core {core} holds {initial_peak} qubits, exceeding "
                f"capacity {capacity}"
            )
    for t in range(partition.n_slices):
        occupancy = partition.occupancy(t, architecture.n_cores)
        peak = int(occupancy.max()) if occupancy.size else 0
        max_occupancy = max(max_occupancy, peak)
        if peak > capacity:
            core = int(np.argmax(occupancy))
            raise InvalidPartitionError(
                f"timeslice {t}: core {core} holds {peak} qubits, exceeding "
                f"capacity {capacity}"
            )

    return ValidationReport(
        n_slices=partition.n_slices,
        n_qubits=partition.n_qubits,
        max_occupancy=max_occupancy,
        capacity=capacity,
        uncolocated_operations=check_colocation(partition, sliced),
    )

def check_colocation(partition: Partition, sliced: SlicedCircuit) -> int:
    total = 0
    for t, time_slice in enumerate(sliced.slices):
        if not time_slice.interactions:
            continue
        placement = partition.placement(t)
        pairs = np.asarray(time_slice.interactions, dtype=np.intp)
        total += int((placement[pairs[:, 0]] != placement[pairs[:, 1]]).sum())
    return total
