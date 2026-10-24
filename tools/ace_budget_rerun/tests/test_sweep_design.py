"""The rerun driver must describe the same study as the one that produced the published results."""
import csv
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "ace_budget_rerun"))
import run_budget_sweep as sweep                                  # noqa: E402

PUBLISHED = REPO / "results" / "ace_congestion_budget_2026-10-23" / "results.csv"


class DesignTests(unittest.TestCase):
    def test_the_jobs_cover_exactly_the_published_cells(self):
        with PUBLISHED.open(newline="", encoding="utf-8") as handle:
            published = {(r["workload"], int(r["mapping_seed"]), int(r["total_memories"]), r["strategy"])
                         for r in csv.DictReader(handle)}
        self.assertEqual(set(sweep.enumerate_jobs()), published)
        self.assertEqual(len(sweep.enumerate_jobs()) * 3, 378)

    def test_the_compiler_split_matches_the_published_one(self):
        with PUBLISHED.open(newline="", encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                self.assertEqual(sweep.runtime_compiler_cap(r["strategy"], int(r["total_memories"])),
                                 int(r["compiler_memories"]), r)
                self.assertEqual(int(r["total_memories"]) - sweep.runtime_compiler_cap(r["strategy"], int(r["total_memories"])),
                                 int(r["demand_bank"]))

    def test_the_budget_one_slot_is_held_back_for_demand(self):
        self.assertEqual([sweep.compiler_memories("dynamic", b) for b in (2, 3, 4, 32)], [1, 2, 3, 31])


if __name__ == "__main__":
    unittest.main()


class WallTimeTests(unittest.TestCase):
    def test_a_real_invocation_records_its_wall_time(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            traces = sweep.extract_traces(Path(tmp) / "traces")
            rows = sweep.run_one(("ghz", 42, 4, "on-demand"), traces, Path(tmp), "per-qubit")
            reused = sweep.run_one(("ghz", 42, 4, "on-demand"), traces, Path(tmp), "per-qubit", reuse=True)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(float(r["invocation_wall_seconds"]) > 0 for r in rows))
        self.assertTrue(all(r["invocation_wall_seconds"] == "" for r in reused))     # reused: nothing was run, no time claimed
