import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import make_torus_config as mk                                                   # noqa: E402


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh = json.loads(mk.MESH_CONFIG.read_text(encoding="utf-8"))
        cls.torus = mk.build(cls.mesh)

    def test_counts_are_the_mesh_plus_eight_wrap_links(self):
        self.assertEqual((len(self.mesh["nodes"]), len(self.mesh["qchannels"]), len(self.mesh["cchannels"])), (40, 48, 144))
        self.assertEqual((len(self.torus["nodes"]), len(self.torus["qchannels"]), len(self.torus["cchannels"])), (48, 64, 192))

    def test_every_router_has_exactly_four_neighbours(self):
        neighbours = {}
        for c in self.torus["cchannels"]:
            if c["source"].startswith("router") and c["destination"].startswith("router"):
                neighbours.setdefault(c["source"], set()).add(c["destination"])
        self.assertEqual(len(neighbours), 16)
        self.assertTrue(all(len(v) == 4 for v in neighbours.values()))

    def test_wrap_links_join_opposite_edges(self):
        pairs = {(c["source"], c["destination"]) for c in self.torus["cchannels"]
                 if c["source"].startswith("router") and c["destination"].startswith("router")}
        self.assertIn(("router_0_3", "router_0_0"), pairs)
        self.assertIn(("router_3_2", "router_0_2"), pairs)
        self.assertNotIn(("router_0_0", "router_2_0"), pairs)

    def test_the_mesh_part_and_all_physical_parameters_are_unchanged(self):
        self.assertEqual(self.torus["templates"], self.mesh["templates"])
        self.assertEqual(self.torus["nodes"][:40], self.mesh["nodes"])
        self.assertEqual(self.torus["qchannels"][:48], self.mesh["qchannels"])
        self.assertEqual(self.torus["cchannels"][:144], self.mesh["cchannels"])

    def test_names_and_seeds_are_unique(self):
        names = [n["name"] for n in self.torus["nodes"]]
        self.assertEqual(len(set(names)), len(names))
        # the mesh file numbers routers 0..15 and BSM nodes 0..23 separately, so seeds are unique within a node type
        for kind in ("QuantumRouter", "BSMNode"):
            seeds = [n["seed"] for n in self.torus["nodes"] if n["type"] == kind]
            self.assertEqual(len(set(seeds)), len(seeds), kind)
        self.assertEqual(sorted(n["seed"] for n in self.torus["nodes"] if n["type"] == "BSMNode"), list(range(32)))

    def test_a_wrap_distance_factor_scales_only_the_wrap_links(self):
        longer = mk.build(self.mesh, wrap_distance_factor=3.0)
        self.assertEqual(longer["qchannels"][:48], self.mesh["qchannels"])
        self.assertTrue(all(abs(q["distance"] - 0.075) < 1e-12 for q in longer["qchannels"][48:]))


if __name__ == "__main__":
    unittest.main()
