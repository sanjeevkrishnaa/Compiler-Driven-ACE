"""Check every benchmark file: integrity, reproducibility, QASM round trip, agreement with MQT Bench ``main``, and that each
circuit computes what its algorithm should.

    python benchmarks/verify.py [--main-dir DIR]     # DIR: the same files generated with MQT Bench main (optional)

Exit status 1 if any check fails.  Checks per file:

1. the SHA-256 in manifest.json matches the file, and regenerating gives byte-identical QASM (reproducible);
2. the file parses back to exactly the circuit that was generated (gates, wires, parameters), with every operation on
   at most two qubits once MQT's custom blocks are expanded, and no unbound parameter;
3. with ``--main-dir``: the gates equal those MQT Bench ``main`` generates (measurements and barriers listed separately);
4. a check of the algorithm itself, independent of MQT's code:
   GHZ / BV / DJ / graphstate are Clifford circuits and are simulated exactly at full size with a stabilizer simulator;
   QFT, QPE and the Draper adder are simulated exactly at small sizes (same generator) and counted against formulas at
   full size; the QAOA and graphstate graphs are rebuilt from the published seed rule and compared edge by edge;
   the BMW circuits are counted against the formulas in their source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import product
from math import comb
from pathlib import Path
import sys

import networkx as nx
import numpy as np
from qiskit import QuantumCircuit, qasm2
from qiskit.quantum_info import Operator, Pauli, StabilizerState, Statevector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import BENCHMARKS, HERE, STANDARD, circuit, flatten, raw_circuit  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)


def gates_only(flat):
    return [item for item in flat if item[0] not in ("measure", "barrier")]


def per_qubit(flat):
    """The sequence of gates on every qubit.  Two circuits with equal sequences on every qubit are the same circuit
    (the same DAG); they may only list gates on disjoint qubits in a different order, as Qiskit's decompose does."""
    wires = {}
    for name, qubits, params in flat:
        if name == "barrier":
            continue
        for q in qubits:
            wires.setdefault(q, []).append((name, qubits, params))
    return wires


def same(flat_a, flat_b) -> bool:
    a, b = per_qubit(flat_a), per_qubit(flat_b)
    if a.keys() != b.keys():
        return False
    for q in a:
        if len(a[q]) != len(b[q]):
            return False
        for (name_a, qubits_a, params_a), (name_b, qubits_b, params_b) in zip(a[q], b[q]):
            if (name_a, qubits_a, len(params_a)) != (name_b, qubits_b, len(params_b)):
                return False
            if not np.allclose(params_a, params_b, rtol=0, atol=1e-12):
                return False
    return True


def unitary_part(qc: QuantumCircuit) -> QuantumCircuit:
    """The circuit without measurements and barriers, built from the expanded gate list."""
    out = QuantumCircuit(qc.num_qubits)
    lookup = {name: getattr(out, name) for name in ("h", "x", "cx", "cz", "cp", "swap", "rx", "rz", "rzz", "rxx")}
    for name, qubits, params in gates_only(flatten(qc)):
        lookup[name](*params, *qubits)
    return out


def measured_qubit_of_clbit(qc: QuantumCircuit) -> dict[int, int]:
    return {qc.find_bit(inst.clbits[0]).index: qc.find_bit(inst.qubits[0]).index
            for inst in qc.data if inst.operation.name == "measure"}


def deterministic_bits(state: StabilizerState, qubits) -> list[int | None]:
    bits = []
    for q in qubits:
        p = state.probabilities_dict(qargs=[q])
        bits.append(int(max(p, key=p.get)) if max(p.values()) > 1 - 1e-9 else None)
    return bits


# ------------------------------------------------------------------ algorithm checks
def check_ghz(qc, n):
    state = StabilizerState(unitary_part(qc))
    probabilities = state.probabilities_dict()
    check(probabilities == {"0" * n: 0.5, "1" * n: 0.5}, "GHZ: only |0...0> and |1...1>, each with probability 1/2")


def check_bv(qc, n):
    hidden = "".join(str(i % 2) for i in range(n - 1))          # MQT's default secret
    state = StabilizerState(unitary_part(qc))
    to_qubit = measured_qubit_of_clbit(qc)
    bits = deterministic_bits(state, [to_qubit[c] for c in range(n - 1)])
    check(None not in bits, "BV: every measured bit is deterministic")
    check("".join(map(str, bits)) == hidden, "BV: classical bit i reads hidden-string character i (alternating 0101...)")


def check_dj(qc, n):
    state = StabilizerState(unitary_part(qc))
    to_qubit = measured_qubit_of_clbit(qc)
    bits = deterministic_bits(state, [to_qubit[c] for c in range(n - 1)])
    check(None not in bits, "DJ: the outcome is deterministic")
    check(any(bits), "DJ: the outcome is not all zeros, so the oracle is balanced (a constant one gives 0...0)")


def check_graphstate(qc, n):
    edges = sorted(tuple(sorted(qubits)) for name, qubits, _ in flatten(qc) if name == "cz")
    reference = nx.random_regular_graph(2, n, seed=10)
    index = {node: i for i, node in enumerate(reference)}
    expected = sorted(tuple(sorted((index[a], index[b]))) for a, b in reference.edges)
    check(edges == expected, "graphstate: CZ edges equal networkx random_regular_graph(2, n, seed=10)")
    degrees = np.bincount(np.array(edges).ravel(), minlength=n)
    check(len(set(edges)) == n and set(degrees.tolist()) == {2}, "graphstate: 2-regular graph, n edges, no repeated edge")
    state = StabilizerState(unitary_part(qc))
    neighbours = {v: set() for v in range(n)}
    for a, b in edges:
        neighbours[a].add(b)
        neighbours[b].add(a)
    good = True
    for v in range(n):
        label = ["I"] * n
        label[v] = "X"
        for u in neighbours[v]:
            label[u] = "Z"
        good &= abs(state.expectation_value(Pauli("".join(reversed(label)))) - 1) < 1e-9
    check(good, "graphstate: every stabilizer X_v Z_N(v) has expectation +1")


def check_qft(qc, n):
    ops = {}
    for name, _, _ in gates_only(flatten(qc)):
        ops[name] = ops.get(name, 0) + 1
    check(ops == {"h": n, "cp": n * (n - 1) // 2, "swap": n // 2}, f"QFT: h = n, cp = n(n-1)/2, swap = n/2 at n = {n}")
    for small in (3, 4, 5, 6):
        size = 2 ** small
        dft = np.array([[np.exp(2j * np.pi * j * k / size) for k in range(size)] for j in range(size)]) / np.sqrt(size)
        check(Operator(unitary_part(circuit("qft", small))).equiv(Operator(dft)),
              f"QFT: the {small}-qubit circuit equals the DFT matrix (up to global phase)")


def check_qpe(qc, n):
    counting = n - 1
    ops = {}
    for name, _, _ in gates_only(flatten(qc)):
        ops[name] = ops.get(name, 0) + 1
    check(ops == {"x": 1, "h": 2 * counting, "cp": counting + counting * (counting - 1) // 2, "swap": counting // 2},
          f"QPE: x = 1, h = 2(n-1), cp = (n-1) + (n-1)(n-2)/2, swap = (n-1)/2 at n = {n}")
    for small in (4, 5, 6, 7, 8):
        sc = circuit("qpeexact", small)
        sv = Statevector(unitary_part(sc))
        to_qubit = measured_qubit_of_clbit(sc)
        p = sv.probabilities_dict(qargs=[to_qubit[c] for c in range(small - 1)])
        check(max(p.values()) > 1 - 1e-9, f"QPE exact: the {small}-qubit circuit reads its phase with probability 1")


def check_draper(qc, n):
    half = n // 2
    ops = {}
    for name, _, _ in gates_only(flatten(qc)):
        ops[name] = ops.get(name, 0) + 1
    qft_cp = half * (half - 1) // 2
    check(ops == {"h": 2 * half, "cp": 2 * qft_cp + half * (half + 1) // 2},
          f"Draper: h = n, cp = 2*QFT({half}) + {half}({half}+1)/2 at n = {n}")
    for small in (4, 6):
        sc = circuit("draper_qft_adder", small)
        k = small // 2
        a_reg, b_reg = (sc.qregs[0], sc.qregs[1])
        a_idx = [sc.find_bit(q).index for q in a_reg]
        b_idx = [sc.find_bit(q).index for q in b_reg]
        body = unitary_part(sc)
        good = True
        for a, b in product(range(2 ** k), repeat=2):
            prep = QuantumCircuit(small)
            for i in range(k):
                if a >> i & 1:
                    prep.x(a_idx[i])
                if b >> i & 1:
                    prep.x(b_idx[i])
            state = Statevector(prep.compose(body))
            outcome = int(max(state.probabilities_dict(), key=state.probabilities_dict().get), 2)
            prob = max(state.probabilities())
            got_a = sum((outcome >> a_idx[i] & 1) << i for i in range(k))
            got_b = sum((outcome >> b_idx[i] & 1) << i for i in range(k))
            good &= prob > 1 - 1e-9 and got_a == a and got_b == (a + b) % 2 ** k
        check(good, f"Draper: for all {4 ** k} inputs at {small} qubits, a stays a and b becomes (a + b) mod 2^{k}")


def check_qaoa(qc, n):
    rng = np.random.default_rng(10)                       # MQT's rule: upper triangle of a random 0/1 matrix, seed 10
    adjacency = np.triu(rng.integers(0, 2, size=(n, n)), 1)
    expected = sorted((int(i), int(j)) for i, j in zip(*np.nonzero(adjacency)))
    rzz = [tuple(sorted(qubits)) for name, qubits, _ in flatten(qc) if name == "rzz"]
    layers = 2
    check(len(rzz) == layers * len(expected), f"QAOA: rzz count = 2 layers x {len(expected)} graph edges")
    check(sorted(rzz[:len(expected)]) == expected and sorted(rzz[len(expected):]) == expected,
          "QAOA: each layer applies rzz on exactly the edges of the seed-10 graph")
    check(len(qc.parameters) == 0, "QAOA: no unbound parameter")


def check_bmw_cardinality(qc, n, depth=3):
    ops = {}
    for name, _, _ in gates_only(flatten(qc)):
        ops[name] = ops.get(name, 0) + 1
    rx = n + sum(n for d in range(depth) if d < depth - 2) + (2 * n if depth >= 2 else 0)
    rz = n + sum(n for d in range(depth) if d < depth - 2) + (n if depth >= 2 else 0)
    check(ops == {"rx": rx, "rz": rz, "rxx": depth * (n - 1)}, "BMW cardinality: rx, rz and rxx counts match its source")
    check(len(qc.parameters) == 0, "BMW cardinality: no unbound parameter")


def check_bmw_copula(qc, n, depth=2):
    ops = {}
    for name, _, _ in gates_only(flatten(qc)):
        ops[name] = ops.get(name, 0) + 1
    half = n // 2
    check(ops == {"h": half, "cx": half, "rz": 2 * n * depth, "rx": n * depth, "rxx": depth * 2 * comb(half, 2)},
          "BMW copula: h, cx, rz, rx and rxx counts match its source")
    check(len(qc.parameters) == 0, "BMW copula: no unbound parameter")


ALGORITHM = {"ghz": check_ghz, "bv": check_bv, "dj": check_dj, "graphstate": check_graphstate, "qft": check_qft,
             "qpeexact": check_qpe, "draper_qft_adder": check_draper, "qaoa": check_qaoa,
             "bmw_quark_cardinality": check_bmw_cardinality, "bmw_quark_copula": check_bmw_copula}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--main-dir", type=Path, help="the same files generated with MQT Bench main")
    args = parser.parse_args()
    manifest = json.loads((HERE / "manifest.json").read_text())
    print(f"MQT Bench {manifest['mqt_bench']}, Qiskit {manifest['qiskit']}, Python {manifest['python']}")
    sizes = sorted({f["requested_size"] for f in manifest["files"]})
    for size in sizes:
        check(sorted(f["benchmark"] for f in manifest["files"] if f["requested_size"] == size) == sorted(BENCHMARKS),
              f"manifest lists every benchmark once at {size} qubits")
    for entry in manifest["files"]:
        name, size, path = entry["benchmark"], entry["requested_size"], HERE / entry["file"]
        print(f"\n{name} ({path.relative_to(HERE)})")
        text = path.read_text()
        check(hashlib.sha256(text.encode()).hexdigest() == entry["sha256"], "file matches the SHA-256 in manifest.json")
        check(qasm2.dumps(circuit(name, size)) == text, "regenerating gives byte-identical QASM")
        loaded = qasm2.loads(text, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
        check(not any(inst.operation.name not in STANDARD for inst in loaded.data), "no custom block left in the file")
        flat_file, flat_mqt = flatten(loaded), flatten(raw_circuit(name, size))
        check(same(flat_file, flat_mqt), "the file has exactly MQT's gates, wires and parameters (its blocks expanded)")
        check(loaded.num_qubits == size, f"{size} qubits")
        check(all(len(q) <= 2 for op, q, _ in flat_file if op not in ("barrier", "measure")),
              "every gate acts on at most two qubits after expansion")
        if args.main_dir is not None:
            other = flatten(qasm2.loads((args.main_dir / entry["file"]).read_text(),
                                        custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS))
            if same(gates_only(flat_file), gates_only(other)):
                check(True, "gates equal those of MQT Bench main (same gate sequence on every qubit)")
            else:
                # graphstate: the release interleaves H and CZ differently; a Clifford state comparison settles it
                equal_state = (all(op in ("h", "cz", "cx", "x", "swap") for op, _, _ in gates_only(flat_file + other))
                               and StabilizerState(unitary_part(loaded)).equiv(
                                   StabilizerState(unitary_part(qasm2.loads((args.main_dir / entry["file"]).read_text(),
                                   custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)))))
                check(equal_state, "gate order differs from MQT Bench main, but both prepare exactly the same state")
            mine = sorted(q for op, q, _ in flat_file if op == "measure")
            theirs = sorted(q for op, q, _ in other if op == "measure")
            if mine != theirs:
                print(f"  note  measurements differ from main: {len(mine)} measured qubits here, {len(theirs)} in main")
        ALGORITHM[name](loaded, size)
    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
