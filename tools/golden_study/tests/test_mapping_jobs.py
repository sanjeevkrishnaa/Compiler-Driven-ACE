from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.golden_study.map_inputs import validate_jobs


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MappingJobsTests(unittest.TestCase):
    def write_fixture(self, root: Path, *, torus_routes: list[str]) -> dict:
        qasm = root / "inputs" / "demo" / "circuit.qasm"
        qasm.parent.mkdir(parents=True)
        qasm.write_bytes(b"OPENQASM 2.0;\n")
        (root / "inputs" / "manifest.json").write_text(json.dumps({"inputs": [{
            "id": "demo", "qasm_path": "inputs/demo/circuit.qasm", "qasm_sha256": _sha(qasm.read_bytes()),
        }]}), encoding="utf-8")
        return {
            "schema": "golden-study-mapping-jobs-v1",
            "input_manifest": "inputs/manifest.json",
            "workloads": ["demo"],
            "mapping_algorithms": ["T-HQA"],
            "mapping_seeds": [7],
            "architecture": {
                "grid": "2x2", "data_qubits_per_core": 2, "reserved_ancilla": 0,
                "initial_placement": "oee", "reliability_min": 0.5,
                "reliability_max": 1.0, "seed_derivation": "mapper-cli-trial-v1",
            },
            "routing": {"mesh": ["xy"], "torus": torus_routes},
        }

    def test_valid_jobs_expand_one_unit_per_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, units = validate_jobs(root, self.write_fixture(root, torus_routes=["dijkstra"]))
            self.assertEqual(set(inputs), {"demo"})
            self.assertEqual(len(units), 2)
            self.assertEqual({unit["topology"] for unit in units}, {"mesh", "torus"})

    def test_rejects_unapproved_torus_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "torus policy"):
                validate_jobs(root, self.write_fixture(root, torus_routes=["xy"]))


if __name__ == "__main__":
    unittest.main()
