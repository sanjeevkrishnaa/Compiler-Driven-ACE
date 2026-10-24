"""Topology awareness of trace validation and the config guard."""
import json
import sys
import unittest
from pathlib import Path

from compiler_trace import cores_adjacent, config_topology, validate_neighbor_requests, CompilerRequest, CompilerTrace

ROOT = Path(__file__).resolve().parents[1]
MESH = json.loads((ROOT / "config" / "final_config" / "grid_4x4_ace_3.json").read_text())
TORUS = json.loads((ROOT / "config" / "final_config" / "grid_4x4_torus_ace_3.json").read_text())


def trace(*hops):
    requests = tuple(CompilerRequest(i, 0, i, 0, a, b) for i, (a, b) in enumerate(hops))
    return CompilerTrace(16, 8, 1, {0: 0}, requests, 1)


class AdjacencyTests(unittest.TestCase):
    def test_mesh_and_torus_neighbours(self):
        self.assertTrue(cores_adjacent(0, 1, 4, 4) and cores_adjacent(0, 4, 4, 4))
        self.assertFalse(cores_adjacent(0, 3, 4, 4) or cores_adjacent(0, 12, 4, 4))
        self.assertTrue(cores_adjacent(0, 3, 4, 4, "torus") and cores_adjacent(0, 12, 4, 4, "torus") and cores_adjacent(15, 3, 4, 4, "torus"))
        self.assertFalse(cores_adjacent(0, 10, 4, 4, "torus") or cores_adjacent(5, 5, 4, 4, "torus"))

    def test_a_wrap_hop_is_refused_on_a_mesh_and_accepted_on_a_torus(self):
        wrap = trace((0, 3))
        with self.assertRaises(ValueError):
            validate_neighbor_requests(wrap, 4, 4)
        validate_neighbor_requests(wrap, 4, 4, "torus")

    def test_the_mesh_default_is_unchanged(self):
        validate_neighbor_requests(trace((0, 1), (1, 5)), 4, 4)
        with self.assertRaises(ValueError):
            validate_neighbor_requests(trace((0, 5)), 4, 4)


class ConfigGuardTests(unittest.TestCase):
    def test_the_two_topology_files_are_recognised(self):
        self.assertEqual(config_topology(MESH, 4, 4), "mesh")
        self.assertEqual(config_topology(TORUS, 4, 4), "torus")


class TorusLoadsInAce(unittest.TestCase):
    def test_ace_builds_the_torus_and_every_router_has_four_quantum_neighbours(self):
        from router_net_topo_adaptive import RouterNetTopoAdaptive
        from sequence.topology.router_net_topo import RouterNetTopo
        topo = RouterNetTopoAdaptive(str(ROOT / "config" / "final_config" / "grid_4x4_torus_ace_3.json"))
        routers = topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER)
        self.assertEqual(len(routers), 16)
        for router in routers:
            bsm_links = [q for q in topo.qchannels if q.sender.name == router.name]
            self.assertEqual(len(bsm_links), 4, router.name)


if __name__ == "__main__":
    unittest.main()
