from __future__ import annotations

import unittest
from pathlib import Path

from tools.golden_study.run_execution import build_command, interpreter_path


class ExecutionRunnerTests(unittest.TestCase):
    def test_interpreter_path_does_not_resolve_venv_symlink(self):
        path = interpreter_path(Path(".venv/bin/python"), Path("/repo"))
        self.assertEqual(path, Path("/repo/.venv/bin/python"))

    def test_command_spells_out_optional_semantics(self):
        job = {
            "trace_path": "trace.txt", "config_path": "config.json", "topology": "mesh",
            "runner_strategies": ["dynamic"], "physics_seeds": [0, 1],
            "total_memories_per_core": 4, "compiler_memories_per_core": 3,
            "generation_capacity_per_core": 3, "chain_hops_prepared": None,
            "congestion_threshold": None,
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
        command = build_command(Path("/python"), Path("/repo"), Path("/study"), job, Path("/out"))
        for flag in ("--all-chain-hops", "--no-congestion-threshold", "--starvation-guard", "--all-layers"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--seeds") + 1], "0,1")


if __name__ == "__main__":
    unittest.main()
