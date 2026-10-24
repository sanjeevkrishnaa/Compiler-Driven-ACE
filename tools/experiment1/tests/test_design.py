import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_experiment1 as exp                                       # noqa: E402


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.jobs = exp.enumerate_jobs()

    def test_every_workload_mapping_seed_and_budget_is_covered(self):
        for workload in exp.WORKLOADS:
            for seed in exp.MAPPING_SEEDS:
                budgets = {b for w, s, b, p in self.jobs if w == workload and s == seed and p == "on-demand"}
                self.assertEqual(budgets, set(exp.BUDGETS) | ({64} if workload == "qft" else set()), (workload, seed))

    def test_dynamic_needs_at_least_two_memories(self):
        self.assertFalse([j for j in self.jobs if j[3] == "dynamic" and j[2] < 2])
        self.assertTrue([j for j in self.jobs if j[3] == "dynamic" and j[2] == 2])

    def test_counts(self):
        on_demand = 10 * 3 * 8 + 3                                  # plus the 64-memory QFT arm
        dynamic = 10 * 3 * 7 + 3
        self.assertEqual(len(self.jobs), on_demand + dynamic)

    def test_capacity_labels_follow_the_papers_four_communication_qubits(self):
        self.assertEqual(exp.label({"total_memories": "4"})["capacity_status"], "modelled")
        self.assertEqual(exp.label({"total_memories": "6"})["capacity_status"], "counterfactual")

    def test_the_control_workload_is_in_the_design(self):
        self.assertIn("ghz", exp.WORKLOADS)


if __name__ == "__main__":
    unittest.main()


class RecordTests(unittest.TestCase):
    def test_source_constants_are_read_from_the_code(self):
        got = exp.source_constants()
        self.assertEqual((got["classical_delay_base_us"], got["classical_delay_per_hop_us"]), (100, 20))
        self.assertEqual((got["empty_layer_gap_ms"], got["admission_grace_ps"], got["wait_threshold_ms"]), (5.0, 1.0, 1e-3))

    def test_the_physics_record_matches_the_config(self):
        got = exp.ace_physics(exp.REPO_ROOT / "config" / "final_config" / "grid_4x4_ace_3.json")
        self.assertEqual((got["memory_efficiency"], got["memory_coherence_time_s"], got["memory_fidelity"]), (0.95, 1, 0.95))
        self.assertEqual(got["router_to_bsm_links"][0]["distance_m"], 0.025)

    def test_timings_list_each_invocation_once_and_claim_nothing_for_reused_work(self):
        import tempfile
        rows = [{"workload": "ghz", "mapping_seed": 42, "total_memories": 4, "strategy": "on-demand", "invocation_wall_seconds": "3.0"}] * 3
        rows += [{"workload": "ghz", "mapping_seed": 43, "total_memories": 4, "strategy": "on-demand", "invocation_wall_seconds": ""}] * 3
        with tempfile.TemporaryDirectory() as tmp:
            summary = exp.write_timings(rows, Path(tmp), 4, 10.0)
            text = (Path(tmp) / "timings.csv").read_text()
        self.assertEqual(summary["invocations_timed"], 1)
        self.assertEqual(text.count("ghz,"), 1)
