"""Unit tests for trace-driven adaptive baseline artifact auditing."""

import unittest

from audit_adaptive_baseline_results import audit_payload


class AdaptiveBaselineAuditTests(unittest.TestCase):
    def test_valid_used_and_expired_pair_records_pass(self):
        summary = {
            "strategy": "cgp", "seed": 0, "requests": 2,
            "completed_requests": 2, "completion_rate": 1.0,
            "adaptive_generated_pairs": 2, "adaptive_utilized_pairs": 1,
            "adaptive_expired_pairs": 1, "adaptive_remaining_pairs": 0,
            "adaptive_expiry_percentage": 50.0,
            "adaptive_waste_percentage": 50.0,
        }
        records = [
            {"generated_at_ps": 1, "used_at_ps": 2, "used_by_request_id": 3,
             "fidelity_at_use": 0.9, "expired_at_ps": None},
            {"generated_at_ps": 1, "used_at_ps": None, "used_by_request_id": None,
             "fidelity_at_use": None, "expired_at_ps": 3},
        ]
        report = audit_payload({"resolved": {"trace_sha256": "trace"},
                                "runs": [{"summary": summary,
                                          "adaptive_pair_trace": records}]})
        self.assertTrue(report["passed"], report["errors"])

    def test_duplicate_use_is_rejected(self):
        summary = {
            "strategy": "cgp", "seed": 0, "requests": 2,
            "completed_requests": 2, "completion_rate": 1.0,
            "adaptive_generated_pairs": 2, "adaptive_utilized_pairs": 2,
            "adaptive_expired_pairs": 0, "adaptive_remaining_pairs": 0,
            "adaptive_expiry_percentage": 0.0, "adaptive_waste_percentage": 0.0,
        }
        record = {"generated_at_ps": 1, "used_at_ps": 2, "used_by_request_id": 3,
                  "fidelity_at_use": 0.9, "expired_at_ps": None}
        report = audit_payload({"runs": [{"summary": summary,
                                           "adaptive_pair_trace": [record, record]}]})
        self.assertFalse(report["passed"])
        self.assertTrue(any("duplicate" in error for error in report["errors"]))
