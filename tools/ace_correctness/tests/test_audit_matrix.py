import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_matrix                                            # noqa: E402


class MatrixTests(unittest.TestCase):
    def test_a_small_matrix_runs_and_every_cell_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m.csv"
            status = audit_matrix.main(["--workloads", "ghz", "bv", "--strategies", "on-demand", "dynamic",
                                        "--memories", "2", "4", "--seeds", "0", "--jobs", "2", "--output", str(out)])
            with out.open() as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(status, 0)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(r["completed"] == r["requested"] and r["violations"] == "0" for r in rows))

    def test_cells_are_one_per_combination(self):
        with tempfile.TemporaryDirectory() as tmp:
            cells = audit_matrix.build_cells(["ghz"], ["on-demand", "fixed"], [2, 4], [0, 1], "per-qubit", None, Path(tmp))
        self.assertEqual(len(cells), 8)


if __name__ == "__main__":
    unittest.main()
