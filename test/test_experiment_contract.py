"""Tests for the shared cross-repository experiment contract."""

import unittest
import os
from pathlib import Path

from compiler_trace import parse_compiler_trace
from experiment_contract import (
    load_contract, select_profile, serialize_conflict_layers,
    serialization_sha256, validate_workload,
)


CONTRACT = Path(__file__).parents[1] / "experiments/qft_4x4_comparison_v1.json"


class ExperimentContractTests(unittest.TestCase):
    def test_memory_profiles_have_explicit_partitions(self):
        contract = load_contract(CONTRACT)
        expected = {
            "full-odg-4": (4, 0, 4),
            "static-3plus1": (4, 3, 1),
            "static-2plus2": (4, 2, 2),
            "static-1plus1": (2, 1, 1),
        }
        actual = {
            profile["id"]: (
                profile["total_entanglement_memories_per_core"],
                profile["compiler_memories_per_core"],
                profile["on_demand_memories_per_core"],
            )
            for profile in contract["profiles"]
        }
        self.assertEqual(actual, expected)

    def test_exact_workload_is_accepted_and_mismatch_is_rejected(self):
        contract = load_contract(CONTRACT)
        workload = contract["workload"]
        validate_workload(
            contract, trace_sha256=workload["trace_sha256"], mesh="4x4",
            cores=16, logical_qubits=96, layers=766, requests=4954,
        )
        with self.assertRaisesRegex(ValueError, "does not satisfy"):
            validate_workload(
                contract, trace_sha256=workload["trace_sha256"], mesh="4x4",
                cores=16, logical_qubits=96, layers=766, requests=4953,
            )

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown experiment profile"):
            select_profile(load_contract(CONTRACT), "3+2")

    def test_qft_serialization_matches_contract_fingerprint(self):
        trace_name = os.environ.get("QFT_TRACE")
        if not trace_name:
            self.skipTest("set QFT_TRACE to validate the full serialization fingerprint")
        trace_path = Path(trace_name)
        contract = load_contract(CONTRACT)
        trace = parse_compiler_trace(trace_path)
        mapping, batches, _ = serialize_conflict_layers(trace.requests, trace.layer_count)
        self.assertEqual(len(batches), contract["workload"]["serialized_sublayers"])
        self.assertEqual(
            serialization_sha256(mapping),
            contract["workload"]["serialization_map_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
