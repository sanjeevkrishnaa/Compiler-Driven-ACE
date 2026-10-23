
from __future__ import annotations

from dataclasses import dataclass

from qmap.exceptions import ArchitectureError

__all__ = ["Core"]

@dataclass(frozen=True, slots=True)
class Core:

    index: int
    coordinate: tuple[int, ...]
    qubits_per_core: int
    reserved_ancilla: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ArchitectureError(f"core index must be non-negative, got {self.index}")
        if self.qubits_per_core <= 0:
            raise ArchitectureError(
                f"qubits_per_core must be positive, got {self.qubits_per_core}"
            )
        if self.reserved_ancilla < 0:
            raise ArchitectureError(
                f"reserved_ancilla must be non-negative, got {self.reserved_ancilla}"
            )
        if self.reserved_ancilla >= self.qubits_per_core:
            raise ArchitectureError(
                f"reserved_ancilla ({self.reserved_ancilla}) must be smaller than "
                f"qubits_per_core ({self.qubits_per_core}); no slots would remain "
                f"for logical qubits"
            )

    @property
    def capacity(self) -> int:
        return self.qubits_per_core

    @property
    def workload_capacity(self) -> int:
        return self.qubits_per_core - self.reserved_ancilla

    @property
    def label(self) -> str:
        return f"c{self.index}({','.join(map(str, self.coordinate))})"

    def __str__(self) -> str:
        return self.label
