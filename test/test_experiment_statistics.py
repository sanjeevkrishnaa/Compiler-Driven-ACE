import unittest
from argparse import Namespace
from pathlib import Path

from aggregate_compiler_results import aggregate, paired_latency
from calibrate_physical_lead import derive_profile, quantile
from experiment_statistics import interval_from_summary, summarize
from run_research_matrix import runner_command


class ExperimentStatisticsTests(unittest.TestCase):
    def test_student_t_interval_for_ten_samples(self):
        result = summarize([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(result["n"], 10)
        self.assertAlmostEqual(result["mean"], 5.5)
        self.assertAlmostEqual(result["sample_sd"], 3.0276503541)
        self.assertAlmostEqual(result["ci95_low"], 3.3341494, places=5)
        self.assertAlmostEqual(result["ci95_high"], 7.6658506, places=5)
        low, high = interval_from_summary(result["mean"], result["sample_sd"], 10)
        self.assertAlmostEqual(low, result["ci95_low"])
        self.assertAlmostEqual(high, result["ci95_high"])

    def test_aggregate_and_paired_comparison_match_by_seed(self):
        rows = [
            {"configuration": "on-demand", "strategy": "on-demand", "seed": "0",
             "average_request_latency_ms": "10", "completion_rate": "1"},
            {"configuration": "on-demand", "strategy": "on-demand", "seed": "1",
             "average_request_latency_ms": "12", "completion_rate": "1"},
            {"configuration": "dynamic-cap2", "strategy": "dynamic", "seed": "0",
             "average_request_latency_ms": "8", "completion_rate": "1"},
            {"configuration": "dynamic-cap2", "strategy": "dynamic", "seed": "1",
             "average_request_latency_ms": "9", "completion_rate": "1"},
        ]
        output = aggregate(rows, metrics=("average_request_latency_ms",))
        dynamic = next(row for row in output if row["configuration"] == "dynamic-cap2")
        self.assertEqual(dynamic["average_request_latency_ms_mean"], 8.5)
        paired = paired_latency(rows, "on-demand")[0]
        self.assertEqual(paired["latency_difference_ms_mean"], -2.5)
        self.assertEqual(paired["paired_seeds"], "0,1")

    def test_physical_lead_calibration_uses_declared_quantiles(self):
        payload = {"trace_sha256": "trace", "config_sha256": "config", "runs": [{
            "simulator_timing_breakdown": {
                "0": {"total_time_ms": 2}, "1": {"total_time_ms": 6}
            },
            "simulator_layer_latencies_ms": {"0": 1, "1": 3},
        }]}
        self.assertEqual(quantile([2, 6], 0.5), 4)
        profile = derive_profile(payload, 0.5, 0.5, 1.5)
        self.assertEqual(profile["service_bound_ms"], 6)
        self.assertEqual(profile["reference_layer_duration_ms"], 2)
        self.assertEqual(profile["dynamic_min_lead_layers"], 3)

    def test_matrix_runner_passes_policy_specific_fixed_delta(self):
        args = Namespace(
            trace=Path("trace.txt"), config=Path("config.json"), seeds="0,1"
        )
        command = runner_command(
            args, Path("out"), "fixed-delta2-cap3", "fixed", 3, 3,
            delta_layers=2,
        )
        self.assertEqual(command[command.index("--delta-layers") + 1], "2")


if __name__ == "__main__":
    unittest.main()
