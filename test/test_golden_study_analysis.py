from __future__ import annotations

import unittest

from tools.golden_study.analyze_memory_sweep import observed_minima, validate_grid


def row(policy: str, compiler_memories: int, latency: float) -> dict[str, str]:
    result = {
        "workload": "unit", "mapping_algorithm": "T-HQA", "topology": "mesh",
        "route_policy": "xy", "total_memories_per_core": "2",
        "compiler_memories_per_core": str(compiler_memories), "policy": policy,
        "physics_seed_count": "30", "completion_rate_mean": "1.0",
        "raw_output_path": "raw/unit",
    }
    metrics = (
        "request_latency_mean_ms", "request_latency_p95_ms", "end_to_end_latency_ms",
        "average_delivered_epr_fidelity", "average_admission_wait_ms",
        "requests_that_waited_fraction", "intended_request_hit_rate",
        "on_demand_fallback_rate", "protocol_waste_percentage",
        "compiler_waste_percentage", "compiler_expiry_percentage",
        "average_storage_time_ms",
    )
    for metric in metrics:
        result[f"{metric}_mean"] = str(latency)
        result[f"{metric}_sd"] = "0.0"
    return result


def complete_rows() -> list[dict[str, str]]:
    rows = [row("ODG", 0, 2.0)]
    for policy in ("CGP", "ACGP", "Dynamic-first-hop", "Dynamic-full-chain"):
        rows.extend((row(policy, 0, 2.0), row(policy, 1, 1.0)))
    return rows


class MemorySweepAnalysisTests(unittest.TestCase):
    def test_complete_triangular_grid_is_accepted(self) -> None:
        rows = complete_rows()
        self.assertEqual(validate_grid(rows, 30), [2])
        minima = observed_minima(rows, [2])
        dynamic = next(item for item in minima if item["policy"] == "Dynamic-full-chain")
        self.assertEqual(dynamic["selected_compiler_memories_per_core"], 1)

    def test_missing_compiler_allocation_is_rejected(self) -> None:
        rows = [item for item in complete_rows()
                if not (item["policy"] == "CGP" and item["compiler_memories_per_core"] == "1")]
        with self.assertRaisesRegex(ValueError, "incomplete grid"):
            validate_grid(rows, 30)

    def test_wrong_seed_count_is_rejected(self) -> None:
        rows = complete_rows()
        rows[0]["physics_seed_count"] = "29"
        with self.assertRaisesRegex(ValueError, "seed-count mismatch"):
            validate_grid(rows, 30)


if __name__ == "__main__":
    unittest.main()
