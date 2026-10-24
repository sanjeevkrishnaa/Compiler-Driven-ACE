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
