from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.golden_study.plan_execution import expand, validate_spec


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExecutionPlanTests(unittest.TestCase):
    def fixture(self, root: Path) -> dict:
        config = root / "config.json"
        config.write_text("{}\n", encoding="utf-8")
        trace = root / "traces" / "mesh" / "T-HQA" / "demo" / "42" / "xy" / "requests.txt"
        trace.parent.mkdir(parents=True)
        trace.write_text("trace\n", encoding="utf-8")
        audit = root / "audit.csv"
        with audit.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=("topology", "mapping_algorithm", "workload", "mapping_seed", "route_policy", "request_trace_sha256"))
            writer.writeheader()
            writer.writerow({"topology": "mesh", "mapping_algorithm": "T-HQA", "workload": "demo", "mapping_seed": 42, "route_policy": "xy", "request_trace_sha256": digest(trace)})
        return {
            "schema": "golden-study-execution-v1", "study_id": "test", "phase": "base", "repository_root": ".",
            "mapping_audit": "audit.csv",
            "trace_path_template": "traces/{topology}/{mapping_algorithm}/{workload}/{mapping_seed}/{route_policy}/requests.txt",
            "trace_selector": {"mapping_algorithm": "T-HQA", "required_workload_count": 1, "mapping_seeds": [42], "topology_routes": {"mesh": ["xy"]}, "deduplicate_exact_trace_hashes": True},
            "physics_seeds": {"training": [10], "evaluation": [0, 1]},
            "topology_configs": {"mesh": "config.json", "torus": "config.json"},
            "memory": {"total_memories_per_core": [2], "generation_capacity_rule": "max(1, compiler_memories_per_core)"},
            "execution_groups": [
                {"id": "ODG", "runner_strategies": ["on-demand"], "compiler_allocations": [0], "chain_hops_prepared": None, "congestion_threshold": None},
                {"id": "FULL", "runner_strategies": ["continuous", "dynamic"], "compiler_allocations": "all", "chain_hops_prepared": None, "congestion_threshold": None},
            ],
            "runner_parameters": {
                "mesh": "4x4", "delta_layers": 6, "preparation_trigger": "layer-start",
                "preparation_delay_ms": 0.0, "planner_lead_layers": 1, "predecessor_distance": 1,
                "dynamic_lookahead_layers": 8, "coherence_time_layers": 10.0,
                "fidelity_threshold": 0.01, "pregeneration_buffer_ms": 0.0,
                "compiler_reservation_ms": 1000.0, "request_duration_ms": 50.0,
                "stop_time_s": 200.0, "scheduler": "per-qubit", "admission": "event",
                "autonomous_cache_follows_compiler_memories": True,
                "stop_after_workload": True, "starvation_guard": True, "max_layers": None,
            },
        }

    def test_expands_every_memory_allocation_and_counts_simulations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = self.fixture(root)
            jobs, summary = expand(root, spec)
            self.assertEqual(len(jobs), 3)  # ODG plus FULL at C=0 and C=1
            self.assertEqual(summary["simulator_policy_seed_evaluations"], 10)
            self.assertEqual({job["compiler_memories_per_core"] for job in jobs}, {0, 1})

    def test_rejects_overlap_between_training_and_evaluation_seeds(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.fixture(Path(directory))
            spec["physics_seeds"]["training"] = [1]
            with self.assertRaisesRegex(ValueError, "disjoint"):
                validate_spec(spec)


if __name__ == "__main__":
    unittest.main()
