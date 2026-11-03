"""Permanent defaults for the quota-six, demand-guarded compiler policy."""

import unittest

from ace.compiler.settings import DEFAULT_COMPILER_POLICY, DEFAULT_COMPILER_RESERVATION_MS


class CompilerPolicyDefaultTests(unittest.TestCase):
    def test_quota_scheduling_and_timing_defaults(self):
        policy = DEFAULT_COMPILER_POLICY
        self.assertEqual(policy.total_memories, 8)
        self.assertEqual(policy.compiler_memories, 6)
        self.assertEqual(policy.generation_capacity, 8)
        self.assertEqual((policy.planner_lead_layers, policy.dynamic_lookahead_layers), (2, 8))
        self.assertEqual(policy.coherence_time_layers, 10)
        self.assertEqual(policy.dynamic_layer_basis, "active")
        self.assertEqual(policy.empty_layer_gap_ms, 0.00001)

    def test_execution_and_lifecycle_defaults(self):
        policy = DEFAULT_COMPILER_POLICY
        self.assertEqual(policy.scheduler, "per-qubit")
        self.assertTrue(policy.demand_first)
        self.assertTrue(policy.refill_on_release)
        self.assertEqual(policy.preparation_priority, "chain-length")
        self.assertEqual(DEFAULT_COMPILER_RESERVATION_MS, 50.0)


if __name__ == "__main__":
    unittest.main()
