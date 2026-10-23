
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qmap.circuit.ir import Circuit, Gate

__all__ = ["SlicedCircuit", "TimeSlice", "slice_circuit"]

@dataclass(frozen=True, slots=True)
class TimeSlice:

    index: int
    gates: tuple[Gate, ...]
    interactions: tuple[tuple[int, int], ...]

    @property
    def active_qubits(self) -> frozenset[int]:
        return frozenset(q for gate in self.gates for q in gate.qubits)

    def __len__(self) -> int:
        return len(self.gates)

    def __str__(self) -> str:
        return f"TimeSlice({self.index}: {len(self.gates)} gates, {len(self.interactions)} 2q)"

@dataclass(frozen=True)
class SlicedCircuit:

    circuit: Circuit
    slices: tuple[TimeSlice, ...]

    @property
    def n_slices(self) -> int:
        return len(self.slices)

    @property
    def n_qubits(self) -> int:
        return self.circuit.n_qubits

    def interaction_matrix(self) -> np.ndarray:
        matrix = np.zeros((self.n_qubits, self.n_qubits), dtype=np.int32)
        for slice_ in self.slices:
            for a, b in slice_.interactions:
                matrix[a, b] += 1
                matrix[b, a] += 1
        return matrix

    def describe(self) -> dict[str, object]:
        return {
            **self.circuit.describe(),
            "n_slices": self.n_slices,
            "max_slice_width": max((len(s) for s in self.slices), default=0),
        }

    def __len__(self) -> int:
        return self.n_slices

    def __str__(self) -> str:
        return f"SlicedCircuit({self.circuit.name}: {self.n_slices} slices)"

def slice_circuit(circuit: Circuit) -> SlicedCircuit:
    if not circuit.gates:
        return SlicedCircuit(circuit=circuit, slices=(TimeSlice(0, (), ()),))

    frontier = [0] * circuit.n_qubits
    buckets: list[list[Gate]] = []

    for gate in circuit.gates:
        target = max((frontier[q] for q in gate.qubits), default=0)
        if target >= len(buckets):
            buckets.extend([] for _ in range(target - len(buckets) + 1))
        buckets[target].append(gate)
        for q in gate.qubits:
            frontier[q] = target + 1

    slices = tuple(
        TimeSlice(
            index=i,
            gates=tuple(gates),
            interactions=tuple(
                (g.qubits[0], g.qubits[1]) for g in gates if g.requires_colocation
            ),
        )
        for i, gates in enumerate(buckets)
    )
    return SlicedCircuit(circuit=circuit, slices=slices)
