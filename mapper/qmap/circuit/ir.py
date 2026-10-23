
from __future__ import annotations

from dataclasses import dataclass, field

from qmap.exceptions import CircuitError

__all__ = ["NON_ENTANGLING_OPS", "Circuit", "Gate"]

NON_ENTANGLING_OPS = frozenset({"measure", "reset", "barrier"})
"""Operations excluded from co-location requirements even with two operands.

A ``Measure`` carries a qubit and a classical bit, and a ``Barrier`` may span many
qubits, but neither entangles anything, so neither forces its operands onto one
core. The mapping cost considers only genuine two-qubit gates.
"""

@dataclass(frozen=True, slots=True)
class Gate:

    name: str
    qubits: tuple[int, ...]
    parameters: tuple[float, ...] = field(default=())

    @property
    def n_qubits(self) -> int:
        return len(self.qubits)

    @property
    def requires_colocation(self) -> bool:
        return len(self.qubits) == 2 and self.name not in NON_ENTANGLING_OPS

    def __str__(self) -> str:
        operands = ",".join(f"q{q}" for q in self.qubits)
        return f"{self.name}({operands})"

@dataclass(frozen=True, slots=True)
class Circuit:

    name: str
    n_qubits: int
    gates: tuple[Gate, ...]

    def __post_init__(self) -> None:
        if self.n_qubits <= 0:
            raise CircuitError(f"circuit {self.name!r} has non-positive width {self.n_qubits}")
        for gate in self.gates:
            for q in gate.qubits:
                if not 0 <= q < self.n_qubits:
                    raise CircuitError(
                        f"circuit {self.name!r} declares {self.n_qubits} qubits but "
                        f"gate {gate} references q{q}"
                    )

    @property
    def n_gates(self) -> int:
        return len(self.gates)

    @property
    def n_two_qubit_gates(self) -> int:
        return sum(1 for g in self.gates if g.requires_colocation)

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "n_qubits": self.n_qubits,
            "n_gates": self.n_gates,
            "n_two_qubit_gates": self.n_two_qubit_gates,
        }

    def __str__(self) -> str:
        return (
            f"{self.name} ({self.n_qubits} qubits, {self.n_gates} gates, "
            f"{self.n_two_qubit_gates} two-qubit)"
        )
