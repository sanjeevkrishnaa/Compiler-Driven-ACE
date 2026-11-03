# Benchmarks

Ten MQT Bench circuits at 128 qubits, OpenQASM 2, one folder each: `<name>/<name>_128.qasm`.

| Folder | Algorithm | Two-qubit gates |
| --- | --- | --- |
| qft | Quantum Fourier transform | 8192 |
| bv | Bernstein-Vazirani | 63 |
| ghz | GHZ state | 127 |
| dj | Deutsch-Jozsa (balanced oracle) | 127 |
| qpeexact | Quantum phase estimation, exactly representable phase | 8191 |
| qaoa | QAOA, 2 layers, random graph (seed 10) | 8212 |
| draper_qft_adder | Draper QFT adder, two 64-qubit registers | 6112 |
| graphstate | Graph state, random 2-regular graph (seed 10) | 128 |
| bmw_quark_cardinality | BMW QUARK cardinality circuit | 381 |
| bmw_quark_copula | BMW QUARK copula circuit | 8128 |

**Source.** MQT Bench 2.3.0 (latest release), Qiskit 2.6.1, `get_benchmark(name, BenchmarkLevel.ALG, circuit_size=128)`,
written with `qiskit.qasm2.dumps`. Regenerate with `python benchmarks/generate.py [--sizes ...]`.

**Two deliberate changes to the plain recipe, both needed for correct files.**
1. `graphstate` uses `seed=10`. Without a seed MQT draws a new random graph on every call, so the file could not be
   reproduced.
2. MQT's custom blocks (`gate qft`, the DJ oracle, Draper's `circuit_*`) are expanded into the standard gates that
   define them. Left as blocks, the mapper's pytket reader sees each as one opaque 128-qubit gate, so QFT, DJ and Draper
   would show no two-qubit gates at all, and Qiskit's strict parser rejects the files. The gates are unchanged.

**Reading.** `cp`, `rzz` and `rxx` are not in `qelib1.inc`. Read with pytket (the mapper's loader) or with
`qiskit.qasm2.loads(text, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)`; `tools/congestion_study/run_study.py`
does the latter.

**Verification** (`python benchmarks/verify.py --main-dir <files generated with MQT Bench main>`, log in
`verification.txt`, 100 checks, all pass):
- SHA-256 per file in `manifest.json`; regenerating gives byte-identical files;
- each file has exactly MQT's gates, wires and parameters (same gate sequence on every qubit), at most two qubits per gate,
  no unbound parameter;
- gates equal those of MQT Bench `main` (commit 8f919416). Only measurements differ: the release QAOA has none and
  `main`'s Draper measures only the sum register. The graph state's gate order differs, and both prepare the same state;
- the algorithms themselves: GHZ, BV (reads the secret 0101...), DJ (balanced), and the graph state's stabilizers are
  simulated exactly at 128 qubits; QFT equals the DFT matrix at 3-6 qubits; exact QPE reads its phase with probability 1
  at 4-8 qubits; the Draper adder gives a + b mod 2^k for every input at 4 and 6 qubits; QAOA and graph-state graphs are
  rebuilt from the published seed rule edge by edge; gate counts match the formulas at 128 qubits.
