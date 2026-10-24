import csv
import io
import sys
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import split_congestion as split                                           # noqa: E402
sys.path.insert(0, str(HERE.parents[1] / "tools" / "heatmap"))
from reference_image_values import REFERENCE                               # noqa: E402


def hop(layer, qubit, source, target):
    return SimpleNamespace(layer=layer, qubit=qubit, source=source, target=target)


class DefinitionTests(unittest.TestCase):
    def test_a_one_hop_route_has_two_endpoints_and_no_relay(self):
        self.assertEqual(split.layer_demand([hop(0, 1, 0, 1)], "hop"), {0: (1, 1), 1: (1, 1)})

    def test_a_relay_core_is_touched_twice_and_neither_touch_is_an_endpoint(self):
        got = split.layer_demand([hop(0, 1, 0, 1), hop(0, 1, 1, 2)], "hop")       # qubit 1 moves 0 -> 1 -> 2
        self.assertEqual(got, {0: (1, 1), 1: (2, 0), 2: (1, 1)})

    def test_under_route_counting_a_relay_needs_one_memory_at_a_time(self):
        got = split.layer_demand([hop(0, 1, 0, 1), hop(0, 1, 1, 2)], "route")
        self.assertEqual(got, {0: (1, 1), 1: (1, 0), 2: (1, 1)})

    def test_different_qubits_make_different_routes(self):
        got = split.layer_demand([hop(0, 1, 0, 1), hop(0, 2, 1, 2)], "hop")       # two single-hop routes meeting at core 1
        self.assertEqual(got[1], (2, 2))

    def test_a_route_that_returns_to_its_start_counts_both_ends(self):
        got = split.layer_demand([hop(0, 1, 0, 1), hop(0, 1, 1, 0)], "hop")
        self.assertEqual(got[0], (2, 2))
        self.assertEqual(got[1], (2, 0))

    def test_own_and_relay_only_are_disjoint_and_add_up_to_the_overloaded_layers(self):
        # capacity 2: core 1 has D_end = 1 + 1 = 2 from two ends... build one own overload and one relay-only overload
        hops = [hop(0, q, 0, 1) for q in range(3)]                                   # layer 0: core 1 endpoint demand 3 > 2
        hops += [hop(1, 0, 4, 1), hop(1, 0, 1, 5), hop(1, 1, 1, 2)]                  # layer 1: core 1 relay 2 + end 1 = 3, D_end 1
        trace = SimpleNamespace(hops=hops, cores=16)
        row = split.split_trace(trace, 2, "hop")[1]
        self.assertEqual((row["own_layers"], row["relay_only_layers"], row["overloaded_layers"]), (1, 1, 2))
        self.assertAlmostEqual(row["own_percent"] + row["relay_only_percent"], row["overloaded_percent"])

    def test_the_relay_share_of_the_excess_is_what_endpoint_demand_alone_would_not_cause(self):
        hops = [hop(0, 0, 4, 1), hop(0, 0, 1, 5)] + [hop(0, q, 1, 2) for q in (1, 2)]     # core 1: relay 2 + 2 ends = D 4, D_end 2
        row = split.split_trace(SimpleNamespace(hops=hops, cores=16), 2, "hop")[1]
        self.assertEqual(row["overloaded_layers"], 1)
        self.assertAlmostEqual(row["relay_share_of_excess"], (2 - 0) / 2)                 # excess 2, endpoints alone 0


class AgainstTheArchiveTests(unittest.TestCase):
    """The split must reproduce what the archive already says."""

    @classmethod
    def setUpClass(cls):
        cls.data = split.compute(4, "hop")

    def test_own_plus_relay_only_reproduces_every_cell_of_the_project_heatmap(self):
        for workload, expected in REFERENCE.items():
            for core, value in enumerate(expected):
                total = (split.mean_over_seeds(self.data, workload, core, "own_percent")
                         + split.mean_over_seeds(self.data, workload, core, "relay_only_percent"))
                self.assertAlmostEqual(round(total + 1e-9, 1), value, places=6, msg=(workload, core))

    def test_relay_incidences_and_incident_hops_reproduce_the_archives_per_core_columns(self):
        with zipfile.ZipFile(split.ARCHIVE) as archive:
            rows = list(csv.DictReader(io.TextIOWrapper(archive.open(f"{split.PREFIX}/all_trials_cores.csv"))))
        self.assertEqual(len(rows), 480)
        for r in rows:
            mine = self.data[r["workload"]][int(r["seed"])][int(r["core"])]
            self.assertEqual(mine["relay_incidences"], int(r["internal_relay_incidences"]), r)
            self.assertEqual(mine["incident_hops"], int(r["incident_hops"]), r)
            self.assertEqual(mine["peak_demand"], int(r["peak_layer_demand"]), r)

    def test_the_two_sets_add_up_for_every_core_and_seed(self):
        for workload in self.data:
            for seed in split.SEEDS:
                for row in self.data[workload][seed].values():
                    self.assertEqual(row["own_layers"] + row["relay_only_layers"], row["overloaded_layers"])

    def test_route_counting_never_reports_more_overload_than_hop_counting(self):
        routes = split.compute(4, "route")
        for workload in self.data:
            for seed in split.SEEDS:
                for core in range(16):
                    self.assertLessEqual(routes[workload][seed][core]["overloaded_layers"],
                                         self.data[workload][seed][core]["overloaded_layers"])


if __name__ == "__main__":
    unittest.main()
