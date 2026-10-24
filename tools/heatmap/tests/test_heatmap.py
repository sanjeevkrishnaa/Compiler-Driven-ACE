import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import regenerate_heatmap as heatmap                                   # noqa: E402
from reference_image_values import REFERENCE                           # noqa: E402


class HeatmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = heatmap.compute(4)

    def test_every_cell_matches_the_project_figure_at_its_printed_resolution(self):
        for workload, expected in REFERENCE.items():
            for core, value in enumerate(expected):
                self.assertAlmostEqual(round(self.data[workload]["mean"][core] + 1e-9, 1), value, places=6, msg=(workload, core))

    def test_core_percentages_count_layers_where_demand_exceeds_capacity(self):
        from types import SimpleNamespace
        hop = lambda layer, a, b: SimpleNamespace(layer=layer, source=a, target=b)
        hops = [hop(0, 0, 1)] * 5 + [hop(0, 2, 3)] + [hop(1, 0, 1)]       # layer 0: core 0 and 1 at demand 5
        trace = SimpleNamespace(hops=hops, cores=4)
        percent, active, any_over = heatmap.core_percentages(trace, 4)
        self.assertEqual((active, any_over), (2, 1))
        self.assertEqual(percent, [50.0, 50.0, 0.0, 0.0])

    def test_a_larger_capacity_never_increases_overload(self):
        looser = heatmap.compute(8)
        for workload in REFERENCE:
            for core in range(16):
                self.assertLessEqual(looser[workload]["mean"][core], self.data[workload]["mean"][core] + 1e-9)


if __name__ == "__main__":
    unittest.main()
