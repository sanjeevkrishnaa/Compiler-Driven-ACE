
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from qmap.circuit.ir import Circuit
from qmap.exceptions import CircuitError, ConfigurationError, DependencyError
from qmap.rng import SeedSequence

__all__ = [
    "BENCHMARKS",
    "DEFAULT_BASIS_GATES",
    "BenchmarkSpec",
    "generate",
    "list_benchmarks",
    "to_qasm",
]

DEFAULT_BASIS_GATES = ("rz", "sx", "cx")

DEFAULT_TWO_QUBIT_PROB = 0.5
"""Probability that a random-circuit gate is two-qubit (decision D13)."""

@dataclass(frozen=True, slots=True)
class BenchmarkSpec:

    name: str
    description: str
    width_of: Callable[[int], int]
    build: Callable[[int], Any]
    min_size: int = 1

def _require_qiskit() -> Any:
    try:
        import qiskit
    except ImportError as exc:
        raise DependencyError(
            "qiskit is required to synthesise benchmark circuits; install it with "
            "`pip install qiskit` (see requirements.txt)"
        ) from exc
    return qiskit

def _build_qft(n: int) -> Any:
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import QFT

    circuit = QuantumCircuit(n)
    circuit.append(QFT(n, do_swaps=True).to_gate(), range(n))
    return circuit.decompose(reps=2)

def _build_cuccaro(n: int) -> Any:
    from qiskit.circuit.library import CDKMRippleCarryAdder

    return CDKMRippleCarryAdder(n, kind="fixed").decompose(reps=2)

def _build_draper(n: int) -> Any:
    from qiskit.circuit.library import DraperQFTAdder

    return DraperQFTAdder(n, kind="fixed").decompose(reps=3)

BENCHMARKS: dict[str, BenchmarkSpec] = {
    "qft": BenchmarkSpec(
        name="qft",
        description="Quantum Fourier Transform (Coppersmith)",
        width_of=lambda n: n,
        build=_build_qft,
        min_size=2,
    ),
    "cuccaro": BenchmarkSpec(
        name="cuccaro",
        description="Cuccaro ripple-carry adder (CDKM), width 2n+2",
        width_of=lambda n: 2 * n + 2,
        build=_build_cuccaro,
        min_size=1,
    ),
    "draper": BenchmarkSpec(
        name="draper",
        description="Draper QFT-based adder, width 2n",
        width_of=lambda n: 2 * n,
        build=_build_draper,
        min_size=1,
    ),
}
"""Structured benchmark families. ``random`` is handled separately by :func:`generate`."""

def list_benchmarks() -> list[str]:
    return sorted([*BENCHMARKS, "random"])

def _largest_size_within(spec: BenchmarkSpec, target_width: int) -> int:
    if spec.width_of(spec.min_size) > target_width:
        raise ConfigurationError(
            f"benchmark {spec.name!r} needs at least "
            f"{spec.width_of(spec.min_size)} qubits, but the target width is "
            f"{target_width}; use a larger architecture"
        )
    low, high = spec.min_size, spec.min_size
    while spec.width_of(high * 2) <= target_width:
        high *= 2
    low, high = high, high * 2
    while low < high:
        mid = (low + high + 1) // 2
        if spec.width_of(mid) <= target_width:
            low = mid
        else:
            high = mid - 1
    return low

def _random_circuit(
    n_qubits: int, depth: int, two_qubit_prob: float, rng: np.random.Generator
) -> Any:
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(n_qubits)
    for _ in range(depth):
        if n_qubits > 1 and rng.random() < two_qubit_prob:
            a, b = rng.choice(n_qubits, size=2, replace=False)
            circuit.cx(int(a), int(b))
        else:
            q = int(rng.integers(n_qubits))
            choice = rng.integers(3)
            if choice == 0:
                circuit.x(q)
            elif choice == 1:
                circuit.h(q)
            else:
                circuit.rz(float(rng.uniform(0.0, 2.0 * math.pi)), q)
    return circuit

def generate(
    benchmark: str,
    width: int,
    *,
    seed: SeedSequence,
    depth: int | None = None,
    two_qubit_prob: float = DEFAULT_TWO_QUBIT_PROB,
    basis_gates: tuple[str, ...] = DEFAULT_BASIS_GATES,
    optimization_level: int = 0,
    name: str | None = None,
) -> Circuit:
    from qiskit import QuantumCircuit, transpile

    if width <= 0:
        raise ConfigurationError(f"circuit width must be positive, got {width}")
    if not 0.0 <= two_qubit_prob <= 1.0:
        raise ConfigurationError(
            f"two_qubit_prob must lie in [0, 1], got {two_qubit_prob}"
        )
    _require_qiskit()

    key = benchmark.lower()
    circuit_name = name or f"{key}_{width}"

    if key == "random":
        gate_count = depth if depth is not None else 2 * width
        if gate_count < 0:
            raise ConfigurationError(f"depth must be non-negative, got {gate_count}")
        raw = _random_circuit(
            width, gate_count, two_qubit_prob, seed.stream("random-circuit").generator()
        )
    else:
        if key not in BENCHMARKS:
            raise ConfigurationError(
                f"unknown benchmark {benchmark!r}; available: {', '.join(list_benchmarks())}"
            )
        spec = BENCHMARKS[key]
        size = _largest_size_within(spec, width)
        raw = spec.build(size)

        if raw.num_qubits < width:
            padded = QuantumCircuit(width)
            padded.compose(raw, qubits=range(raw.num_qubits), inplace=True)
            raw = padded

    try:
        transpiled = transpile(
            raw, basis_gates=list(basis_gates), optimization_level=optimization_level
        )
    except Exception as exc:
        raise CircuitError(f"failed to transpile {circuit_name!r}: {exc}") from exc

    return _from_qiskit(transpiled, circuit_name, width)

def _from_qiskit(qiskit_circuit: Any, name: str, width: int) -> Circuit:
    from qmap.circuit.ir import Gate

    if qiskit_circuit.num_qubits != width:
        raise CircuitError(
            f"circuit {name!r} has width {qiskit_circuit.num_qubits}, expected {width}"
        )
    index_of = {bit: i for i, bit in enumerate(qiskit_circuit.qubits)}

    gates: list[Gate] = []
    for instruction in qiskit_circuit.data:
        operation = instruction.operation
        parameters: tuple[float, ...] = ()
        try:
            parameters = tuple(float(p) for p in operation.params)
        except (TypeError, ValueError):
            parameters = ()
        gates.append(
            Gate(
                name=operation.name.lower(),
                qubits=tuple(index_of[q] for q in instruction.qubits),
                parameters=parameters,
            )
        )
    return Circuit(name=name, n_qubits=width, gates=tuple(gates))

def to_qasm(circuit: Circuit) -> str:
    lines = [
        "OPENQASM 2.0;",
        'include "qelib1.inc";',
        f"qreg q[{circuit.n_qubits}];",
    ]
    for gate in circuit.gates:
        operands = ", ".join(f"q[{q}]" for q in gate.qubits)
        if gate.parameters:
            params = ", ".join(f"{p:.17g}" for p in gate.parameters)
            lines.append(f"{gate.name}({params}) {operands};")
        else:
            lines.append(f"{gate.name} {operands};")
    return "\n".join(lines) + "\n"
