
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from qmap.circuit.ir import Circuit, Gate
from qmap.exceptions import CircuitError, DependencyError

if TYPE_CHECKING:
    from pytket import Circuit as TketCircuit

__all__ = ["DEFAULT_MAX_WIDTH", "from_tket", "load_qasm", "load_qasm_str"]

DEFAULT_MAX_WIDTH = 4096

def _require_pytket() -> Any:
    try:
        from pytket import qasm
    except ImportError as exc:
        raise DependencyError(
            "pytket is required to parse QASM circuits; install it with "
            "`pip install pytket` (see requirements.txt)"
        ) from exc
    return qasm

def _gate_parameters(command: Any) -> tuple[float, ...]:
    try:
        return tuple(float(p) for p in command.op.params)
    except (RuntimeError, TypeError, ValueError):
        return ()

def from_tket(tket_circuit: TketCircuit, name: str) -> Circuit:
    qubits = sorted(tket_circuit.qubits, key=lambda q: (q.reg_name, tuple(q.index)))
    if not qubits:
        raise CircuitError(f"circuit {name!r} declares no qubits")
    index_of = {qubit: i for i, qubit in enumerate(qubits)}

    gates = tuple(
        Gate(
            name=command.op.type.name.lower(),
            qubits=tuple(index_of[q] for q in command.qubits),
            parameters=_gate_parameters(command),
        )
        for command in tket_circuit
    )
    return Circuit(name=name, n_qubits=len(qubits), gates=gates)

def load_qasm(path: str | Path, *, max_width: int = DEFAULT_MAX_WIDTH) -> Circuit:
    qasm_path = Path(path)
    if not qasm_path.is_file():
        raise CircuitError(f"QASM file not found: {qasm_path}")

    qasm = _require_pytket()
    try:
        tket_circuit = qasm.circuit_from_qasm(str(qasm_path), maxwidth=max_width)
    except Exception as exc:
        raise CircuitError(f"failed to parse {qasm_path}: {exc}") from exc
    return from_tket(tket_circuit, name=qasm_path.stem)

def load_qasm_str(
    source: str, *, name: str = "circuit", max_width: int = DEFAULT_MAX_WIDTH
) -> Circuit:
    qasm = _require_pytket()
    try:
        tket_circuit = qasm.circuit_from_qasm_str(source, maxwidth=max_width)
    except Exception as exc:
        raise CircuitError(f"failed to parse QASM source {name!r}: {exc}") from exc
    return from_tket(tket_circuit, name=name)
