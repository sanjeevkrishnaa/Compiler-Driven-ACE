"""Generate the MQT Bench circuits used by this project as OpenQASM 2 files.

Same recipe as the original single-benchmark script: ``get_benchmark(name, BenchmarkLevel.ALG, circuit_size=n)``, then
``qiskit.qasm2.dumps``, saved as ``benchmarks/<name>/<name>_<n>.qasm``.  Additions:

* every benchmark in ``BENCHMARKS`` in one run (the two BMW circuits are ``bmw_quark_cardinality`` and ``bmw_quark_copula``);
* ``graphstate`` gets ``seed=10``: without a seed MQT draws a new random graph every call, so the file could not be
  reproduced (checked: two unseeded calls give different circuits).  10 is MQT's own default seed for QAOA and QPE;
* ``manifest.json`` records the package versions, the options and a SHA-256 of every file.

Run with MQT Bench 2.3.0 (the latest release) and Qiskit 2.6.1:

    python benchmarks/generate.py               # 128 qubits, as in the original script
    python benchmarks/generate.py --sizes 128 224
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import qiskit
from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit.circuit.library import get_standard_gate_name_mapping
from qiskit.qasm2 import dumps

HERE = Path(__file__).resolve().parent
BENCHMARKS = ("qft", "bv", "ghz", "dj", "qpeexact", "qaoa", "draper_qft_adder", "graphstate",
              "bmw_quark_cardinality", "bmw_quark_copula")
OPTIONS = {"graphstate": {"seed": 10}}          # everything else is deterministic with MQT's defaults


STANDARD = set(get_standard_gate_name_mapping()) | {"measure", "barrier", "reset"}


def flatten(qc) -> list[tuple[str, tuple[int, ...], tuple[float, ...]]]:
    """Every operation as (name, qubit indices, parameters), with custom blocks (MQT's ``qft``, DJ's oracle, Draper's
    ``circuit_*``) expanded into the standard gates they are defined by.  At the ALG level some benchmarks are one big
    block, so counting top-level operations would miss all their two-qubit gates."""
    out = []

    def walk(circuit, wires):
        for inst in circuit.data:
            op = inst.operation
            qubits = tuple(wires[circuit.find_bit(q).index] for q in inst.qubits)
            if op.name not in STANDARD and op.definition is not None:
                walk(op.definition, qubits)
            else:
                out.append((op.name, qubits, tuple(float(p) for p in op.params)))

    walk(qc, tuple(range(qc.num_qubits)))
    return out


def raw_circuit(name: str, size: int):
    """Exactly what MQT Bench returns at the ALG level."""
    return get_benchmark(benchmark=name, level=BenchmarkLevel.ALG, circuit_size=size, **OPTIONS.get(name, {}))


def expand(qc):
    """Replace MQT's custom blocks by the standard gates that define them, nothing else.

    Two readers mishandle the blocks: the mapper's pytket loader keeps ``gate qft`` (and DJ's oracle, Draper's
    ``circuit_*``) as one opaque 128-qubit gate, so it sees no two-qubit gates at all, and Qiskit's strict QASM 2 parser
    rejects the ``cp`` used inside the block.  The expanded circuit has exactly the same gates (checked by verify.py).
    """
    while True:
        custom = {inst.operation.name for inst in qc.data if inst.operation.name not in STANDARD}
        if not custom:
            return qc
        qc = qc.decompose(gates_to_decompose=sorted(custom))


def circuit(name: str, size: int):
    return expand(raw_circuit(name, size))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", type=int, nargs="+", default=[128])
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args()
    files = []
    for size in args.sizes:
        for name in BENCHMARKS:
            qc = circuit(name, size)
            text = dumps(qc)
            path = args.out / name / f"{name}_{size}.qasm"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            flat = flatten(qc)
            ops = {}
            for op, _, _ in flat:
                ops[op] = ops.get(op, 0) + 1
            ops = dict(sorted(ops.items()))
            two_qubit = sum(1 for op, qubits, _ in flat if len(qubits) == 2 and op not in ("barrier", "measure"))
            wider = sorted({op for op, qubits, _ in flat if len(qubits) > 2 and op != "barrier"})
            files.append(dict(benchmark=name, requested_size=size, file=str(path.relative_to(args.out)),
                              qubits=qc.num_qubits, clbits=qc.num_clbits, depth=qc.depth(), two_qubit_gates=two_qubit,
                              ops_after_expansion=ops, gates_wider_than_two_qubits=wider,
                              top_level_ops=dict(sorted(qc.count_ops().items())), options=OPTIONS.get(name, {}), sha256=hashlib.sha256(text.encode()).hexdigest()))
            print(f"Saved: {path}  qubits={qc.num_qubits} two-qubit gates={two_qubit}")
    manifest = dict(generator="benchmarks/generate.py", level="ALG", format="OpenQASM 2 (qiskit.qasm2.dumps)",
                    custom_blocks="expanded into their standard gates (qft, DJ oracle, Draper circuit_*); gates unchanged",
                    reading_note="cp, rzz and rxx are not in qelib1.inc: read with qiskit.qasm2.loads(text, "
                                 "custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS) or pytket",
                    mqt_bench=version("mqt.bench"), qiskit=qiskit.__version__, python=platform.python_version(),
                    random_parameter_rule="MQT binds free parameters with numpy default_rng(10), uniform in [0, 2 pi)",
                    files=files)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


if __name__ == "__main__":
    main()
