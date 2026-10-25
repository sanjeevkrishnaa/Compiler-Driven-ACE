from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.golden_study import studyctl


def contract() -> dict:
    return {
        "schema_version": 1,
        "study_id": "test-study",
        "workloads": {"required_count": 1, "inventory": "workload_inventory.json"},
        "seeds": {"mapping": [], "physics_training": [], "physics_evaluation": []},
        "memory_experiment": {"total_memories_per_core": [2, 4]},
        "routing": {"mesh": ["xy"], "torus": ["dijkstra"]},
        "policy_definitions": {
            "ODG": {}, "CGP": {}, "ACGP": {}, "Dynamic-full-chain": {},
            "Dynamic-first-hop": {},
            "Dynamic-congestion-adaptive": {"parameters": {"congestion_threshold": "MUST_BE_PREREGISTERED"}},
        },
    }


class StudyControlTests(unittest.TestCase):
    def test_contract_accepts_declared_capacity_sweep_without_execution_inputs(self):
        self.assertEqual(studyctl.validate_contract(contract(), run_ready=False), [])

    def test_contract_rejects_unsorted_or_duplicate_capacities(self):
        value = contract()
        value["memory_experiment"]["total_memories_per_core"] = [4, 2, 4]
        self.assertIn("memory capacities must be unique and increasing", studyctl.validate_contract(value, run_ready=False))

    def test_run_ready_requires_explicit_seeds_and_preregistered_adaptation(self):
        errors = studyctl.validate_contract(contract(), run_ready=True)
        self.assertTrue(any("non-empty mapping" in error for error in errors))
        self.assertTrue(any("congestion_threshold" in error for error in errors))

    def test_inventory_hash_is_checked_against_the_registered_trace(self):
        value = contract()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            trace = root / "trace.txt"
            trace.write_text("immutable trace\n", encoding="utf-8")
            digest = hashlib.sha256(trace.read_bytes()).hexdigest()
            (root / "workload_inventory.json").write_text(json.dumps({"workloads": [{
                "id": "one", "trace_path": "trace.txt", "trace_sha256": digest,
            }]}), encoding="utf-8")
            self.assertEqual(studyctl.validate_inventory(root, value), [])
            trace.write_text("changed trace\n", encoding="utf-8")
            self.assertTrue(any("hash does not match" in error for error in studyctl.validate_inventory(root, value)))


if __name__ == "__main__":
    unittest.main()
