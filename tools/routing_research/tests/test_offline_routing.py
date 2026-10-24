import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import offline_routing as ro                                                  # noqa: E402
sys.path.insert(0, str(HERE.parents[1] / "tools" / "experiment2"))
import split_congestion as split                                              # noqa: E402
from hotspot_analysis import read_trace                                       # noqa: E402

MESH = ro.adjacency("mesh")
TORUS = ro.adjacency("torus")


class PathTests(unittest.TestCase):
    def test_shortest_paths_on_the_mesh_are_the_binomial_count(self):
        self.assertEqual(len(ro.simple_paths(MESH, 0, 15, 6)), 20)               # C(6,3)
        self.assertEqual(len(ro.simple_paths(MESH, 0, 5, 2)), 2)

    def test_the_torus_has_wrap_around_shortcuts(self):
        self.assertEqual(ro.shortest_length(MESH, 0, 3), 3)
        self.assertEqual(ro.shortest_length(TORUS, 0, 3), 1)
        self.assertEqual(ro.shortest_length(TORUS, 0, 10), 4)

    def test_every_candidate_is_a_simple_walk_between_the_endpoints(self):
        for path in ro.simple_paths(MESH, 1, 14, 5):
            self.assertEqual((path[0], path[-1]), (1, 14))
            self.assertEqual(len(set(path)), len(path))
            self.assertTrue(all(b in MESH[a] for a, b in zip(path, path[1:])))

    def test_extra_hops_add_longer_candidates(self):
        self.assertGreater(len(ro.simple_paths(MESH, 5, 6, 3)), len(ro.simple_paths(MESH, 5, 6, 1)))


class DemandTests(unittest.TestCase):
    def test_touches_agree_with_the_experiment2_definition(self):
        path = (0, 1, 2, 6)
        for variant in ("hop", "route"):
            hops = [type("H", (), dict(layer=0, qubit=1, source=a, target=b)) for a, b in zip(path, path[1:])]
            expected = split.layer_demand(hops, variant)
            self.assertEqual(ro.touches(path, variant), {c: v for c, v in expected.items()})


class OptimizerTests(unittest.TestCase):
    def test_a_crossing_that_can_be_avoided_is_avoided(self):
        # capacity 2: three routes 0->10 all through the same middle if they used the same path; spread them out
        paths = [(0, 1, 2, 6, 10)] * 3 + [(4, 5, 6, 7)]
        before = ro.excess(paths, 2, "hop")
        result = ro.optimize_layer(paths, 2, "hop", MESH, extra=0)
        self.assertGreater(before, 0)
        self.assertLess(result.excess, before)
        self.assertEqual(result.excess, ro.excess(result.paths, 2, "hop"))

    def test_the_result_is_never_worse_and_never_below_the_lower_bound(self):
        paths = [(0, 1, 2, 3), (4, 5, 6, 7), (1, 5, 9, 13), (2, 6, 10, 14), (0, 4, 8, 12), (3, 7, 11, 15), (5, 6), (9, 10)]
        for variant in ("hop", "route"):
            for capacity in (1, 2, 3):
                for extra in (0, 2):
                    res = ro.optimize_layer(paths, capacity, variant, MESH, extra=extra)
                    self.assertLessEqual(res.excess, ro.excess(paths, capacity, variant))
                    self.assertGreaterEqual(res.excess, ro.lower_bound(paths, capacity, variant))

    def test_the_volume_bound_holds_and_is_tight_when_everything_is_saturated(self):
        paths = [(0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11), (12, 13, 14, 15)] * 3
        for variant in ("hop", "route"):
            for capacity in (1, 2):
                res = ro.optimize_layer(paths, capacity, variant, MESH, extra=2)
                self.assertGreaterEqual(res.excess, ro.volume_bound(paths, capacity, variant, MESH))
        self.assertEqual(ro.volume_bound([(0, 1)], 1, "hop", MESH), 0)
        self.assertEqual(ro.volume_bound([(0, 1)] * 20, 1, "hop", MESH), 40 - 16)

    def test_endpoints_never_change(self):
        paths = [(0, 1, 2, 6, 10), (3, 2, 1, 5, 9), (12, 13, 14, 10)]
        res = ro.optimize_layer(paths, 1, "hop", MESH, extra=2)
        self.assertEqual([(p[0], p[-1]) for p in res.paths], [(p[0], p[-1]) for p in paths])

    def test_a_layer_with_no_overload_is_left_alone(self):
        paths = [(0, 1), (4, 5)]
        self.assertEqual(ro.optimize_layer(paths, 4, "hop", MESH).paths, [tuple(p) for p in paths])

    def test_when_only_endpoints_overload_nothing_can_be_gained(self):
        paths = [(5, 6)] * 5                                                       # five routes ending at core 6
        res = ro.optimize_layer(paths, 2, "hop", MESH, extra=2)
        self.assertEqual(res.excess, ro.lower_bound(paths, 2, "hop"))


class TraceTests(unittest.TestCase):
    def test_a_rerouted_archive_trace_is_valid_and_keeps_every_placement(self):
        import zipfile
        archive = split.ARCHIVE
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(archive) as z:
            original = Path(z.extract(f"{split.PREFIX}/graphstate/seed_42/requests.txt", tmp))
            trace = read_trace(original, 4, 4)
            routes, results = ro.reroute_trace(trace, 2, "hop", MESH, extra=0, time_limit=10)
            written = ro.write_trace(trace, routes, ro.route_qubits(trace), Path(tmp) / "new.txt")
            new = read_trace(written, 4, 4)                                        # validates adjacency and placement
        self.assertEqual(new.layers, trace.layers)
        old_end = {}
        new_end = {}
        for tr, store in ((trace, old_end), (new, new_end)):
            loc = dict(tr.initial)
            for hop in tr.hops:
                loc[hop.qubit] = hop.target
            store.update(loc)
        self.assertEqual(old_end, new_end)
        self.assertEqual(len(new.hops), len(trace.hops))                           # shortest paths only: same hop count
        self.assertTrue(all(r.excess <= r.baseline_excess for r in results.values()))


if __name__ == "__main__":
    unittest.main()


class StudyTests(unittest.TestCase):
    def test_the_study_rows_obey_the_bounds_on_a_small_workload(self):
        import run_routing_study as run_study
        with tempfile.TemporaryDirectory() as tmp:
            import zipfile
            with zipfile.ZipFile(run_study.ARCHIVE) as z:
                path = z.extract(f"{run_study.PREFIX}/graphstate/seed_42/requests.txt", tmp)
            rows = run_study.study_trace((path, "graphstate", 42, "mesh"))
        self.assertEqual(len(rows), len(run_study.CAPACITIES) * len(run_study.VARIANTS) * len(run_study.EXTRAS))
        for r in rows:
            self.assertLessEqual(r["optimised_excess"], r["baseline_excess"])
            self.assertGreaterEqual(r["optimised_excess"], r["best_lower_bound"])
            self.assertGreaterEqual(r["best_lower_bound"], max(r["endpoint_lower_bound"], 0))
            if r["extra_hops"] == 0:
                self.assertEqual(r["added_hops"], 0)
