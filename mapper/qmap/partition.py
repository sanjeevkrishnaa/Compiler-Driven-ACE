
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from qmap.exceptions import InvalidPartitionError

__all__ = ["CORE_DTYPE", "Partition"]

CORE_DTYPE = np.int32
"""Storage dtype for core indices. 32 bits covers any plausible core count."""

@dataclass(frozen=True)
class Partition:

    assignments: np.ndarray
    initial_assignment: np.ndarray | None = None
    """Pre-circuit placement :math:`A_0`.

    ``assignments[t]`` is the placement *after* resolving circuit timeslice
    ``t``.  Keeping the seed placement separate is essential: the first
    circuit timeslice must be mapped just like every later one, rather than
    treating the seed as its output.  ``None`` preserves compatibility with
    partitions constructed by older callers, where slice zero is also used as
    the pre-slice placement.
    """
    route_model: str = "shortest"
    """Physical route used to bill transfers: ``shortest`` or ``reliability``."""

    def __post_init__(self) -> None:
        if self.route_model not in {"shortest", "reliability"}:
            raise InvalidPartitionError(
                "physical route model must be 'shortest' or 'reliability', got "
                f"{self.route_model!r}"
            )
        if self.assignments.ndim != 2:
            raise InvalidPartitionError(
                f"partition must be 2-D (n_slices, n_qubits), got shape {self.assignments.shape}"
            )
        if self.assignments.size and self.assignments.min() < 0:
            raise InvalidPartitionError("partition contains negative core indices")
        if self.initial_assignment is not None:
            if self.initial_assignment.shape != (self.assignments.shape[1],):
                raise InvalidPartitionError(
                    "initial placement must have one core index per qubit; got "
                    f"shape {self.initial_assignment.shape}, expected "
                    f"({self.assignments.shape[1]},)"
                )
            if self.initial_assignment.size and self.initial_assignment.min() < 0:
                raise InvalidPartitionError("initial placement contains negative core indices")
            self.initial_assignment.setflags(write=False)
        self.assignments.setflags(write=False)

    @classmethod
    def from_sequence(
        cls,
        placements: Sequence[np.ndarray],
        *,
        initial_assignment: np.ndarray | None = None,
        route_model: str = "shortest",
    ) -> Partition:
        if not placements:
            raise InvalidPartitionError("cannot build a partition from zero timeslices")
        widths = {int(p.shape[0]) for p in placements}
        if len(widths) != 1:
            raise InvalidPartitionError(
                f"placement vectors have inconsistent widths: {sorted(widths)}"
            )
        initial = (
            None
            if initial_assignment is None
            else np.asarray(initial_assignment, dtype=CORE_DTYPE).copy()
        )
        return cls(
            np.asarray(placements, dtype=CORE_DTYPE),
            initial,
            route_model,
        )

    @property
    def n_slices(self) -> int:
        return int(self.assignments.shape[0])

    @property
    def n_qubits(self) -> int:
        return int(self.assignments.shape[1])

    def placement(self, t: int) -> np.ndarray:
        return self.assignments[t]

    def previous_placement(self, t: int) -> np.ndarray:
        """Return the placement immediately before circuit timeslice ``t``."""
        if not 0 <= t < self.n_slices:
            raise InvalidPartitionError(
                f"timeslice {t} is out of range for {self.n_slices} timeslices"
            )
        if t == 0:
            return (
                self.initial_assignment
                if self.initial_assignment is not None
                else self.assignments[0]
            )
        return self.assignments[t - 1]

    def occupancy(self, t: int, n_cores: int) -> np.ndarray:
        return np.bincount(self.assignments[t], minlength=n_cores)

    def migrations(self, t: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if t < 1:
            raise InvalidPartitionError(
                f"migrations are defined between consecutive timeslices; got t={t}"
            )
        previous = self.assignments[t - 1]
        current = self.assignments[t]
        moved = np.flatnonzero(previous != current)
        return moved, previous[moved], current[moved]

    def transition(self, t: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return migrations from the placement before timeslice ``t`` to its output."""
        previous = self.previous_placement(t)
        current = self.assignments[t]
        moved = np.flatnonzero(previous != current)
        return moved, previous[moved], current[moved]

    def total_migrations(self) -> int:
        between_slices = (
            0
            if self.n_slices < 2
            else int(np.count_nonzero(self.assignments[1:] != self.assignments[:-1]))
        )
        initial = (
            0
            if self.initial_assignment is None or self.n_slices == 0
            else int(np.count_nonzero(self.assignments[0] != self.initial_assignment))
        )
        return initial + between_slices

    def to_records(self, coordinate_of) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for t in range(self.n_slices):
            placement = self.assignments[t]
            records.append(
                {
                    "timeslice": t,
                    "placement": {
                        int(q): {
                            "core": int(c),
                            "coordinate": list(coordinate_of(int(c))),
                        }
                        for q, c in enumerate(placement)
                    },
                }
            )
        return records

    def __len__(self) -> int:
        return self.n_slices

    def __str__(self) -> str:
        return f"Partition({self.n_slices} timeslices x {self.n_qubits} qubits)"
