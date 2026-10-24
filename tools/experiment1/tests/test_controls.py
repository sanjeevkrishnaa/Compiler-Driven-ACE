import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze                                                           # noqa: E402


def row(workload, strategy, budget, ms, seed, latency, fidelity="0.95", makespan="100.0", ok=True, completion="1.0"):
    return {"workload": workload, "strategy": strategy, "total_memories": str(budget), "mapping_seed": str(ms),
            "seed": str(seed), "average_eligible_latency_ms": str(latency), "average_delivered_epr_fidelity": fidelity,
            "end_to_end_latency_ms": makespan, "run_status": "ok" if ok else "FAILED", "completion_rate": completion}


def verdicts(rows):
    return {name.split(":")[0].split(" does")[0]: ok for name, ok, _ in analyze.controls(rows, None)}


class ControlTests(unittest.TestCase):
    def base(self):
        rows = []
        for seed in (0, 1, 2):
            for budget, latency in ((1, 5.0), (2, 2.0), (4, 1.2), (8, 1.1)):
                rows.append(row("qaoa", "on-demand", budget, 42, seed, latency + 0.01 * seed))
                rows.append(row("ghz", "on-demand", budget, 42, seed, 1.17))
        return rows

    def test_a_clean_dataset_passes_every_control(self):
        self.assertTrue(all(ok for _, ok, _ in analyze.controls(self.base(), None)))

    def test_a_ghz_latency_that_moves_with_the_budget_fails_the_zero_congestion_control(self):
        rows = self.base()
        rows.append(row("ghz", "on-demand", 16, 42, 0, 1.30))
        failed = [n for n, ok, _ in analyze.controls(rows, None) if not ok]
        self.assertTrue(any("GHZ" in n for n in failed))

    def test_a_tiny_rise_within_the_seed_spread_is_noise_and_a_large_rise_fails(self):
        rows = self.base()
        for seed in (0, 1, 2):                                                 # +0.0005 against a seed spread of 0.01
            rows.append(row("qaoa", "on-demand", 16, 42, seed, 1.1 + 0.01 * seed + 0.0005))
        self.assertTrue(all(ok for _, ok, _ in analyze.controls(rows, None)))
        for seed in (0, 1, 2):
            rows.append(row("qaoa", "on-demand", 32, 42, seed, 1.1 + 0.01 * seed + 0.5))     # clearly higher
        failed = [n for n, ok, _ in analyze.controls(rows, None) if not ok]
        self.assertTrue(any("rise" in n for n in failed))

    def test_saturation_tolerates_a_picosecond_but_not_a_real_difference(self):
        rows = [row("qft", "dynamic", b, 42, 0, lat) for b, lat in ((32, 0.25), (64, 0.25 + 2e-12))]
        self.assertTrue(all(ok for n, ok, _ in analyze.controls(rows, None) if "saturation" in n))
        rows = [row("qft", "dynamic", b, 42, 0, lat) for b, lat in ((32, 0.25), (64, 0.26))]
        self.assertFalse(all(ok for n, ok, _ in analyze.controls(rows, None) if "saturation" in n))

    def test_an_incomplete_run_fails(self):
        rows = self.base() + [row("qft", "on-demand", 4, 42, 0, 1.0, completion="0.9")]
        self.assertFalse(analyze.controls(rows, None)[0][1])


if __name__ == "__main__":
    unittest.main()
