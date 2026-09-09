"""Tests for publication-artifact consistency checks."""

import unittest

from audit_compiler_results import audit_payload


def _run(strategy):
    return {
        "summary": {
            "configuration": "cap3",
            "strategy": strategy,
            "seed": 0,
            "requests": 1,
            "completed_requests": 1,
            "completion_rate": 1.0,
            "generated_compiler_pairs": 0,
            "utilized_compiler_pairs": 0,
            "expired_compiler_pairs": 0,
        },
        "epr_utilization_trace": [],
    }


class AuditCompilerResultsTests(unittest.TestCase):
    def test_different_strategies_can_share_configuration_and_seed(self):
        report = audit_payload({"runs": [_run("fixed"), _run("dynamic")]})
        self.assertTrue(report["passed"])
        self.assertEqual(report["configuration_strategy_seed_cells"], 2)

    def test_identical_configuration_strategy_seed_is_duplicate(self):
        report = audit_payload({"runs": [_run("fixed"), _run("fixed")]})
        self.assertFalse(report["passed"])
        self.assertIn("duplicate configuration/strategy/seed", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
