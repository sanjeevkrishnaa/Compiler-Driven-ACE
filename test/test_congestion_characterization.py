"""Dependency and routing checks for compiler-layer congestion analysis."""
import unittest
from collections import Counter

from tools.trace_analysis.characterize_qft_congestion import (
    pack_waves,
    shortest_mesh_paths,
)


class CongestionAnalysisTests(unittest.TestCase):
    def test_multihop_precedence_is_preserved_with_spare_endpoint_capacity(self):
        requests = [(0, 7, 0, 1), (1, 7, 1, 2), (2, 7, 2, 3), (3, 8, 4, 5)]
        self.assertEqual(pack_waves(requests, 4), [[0, 3], [1], [2]])

    def test_deferred_first_hop_does_not_allow_its_later_hop_to_overtake(self):
        requests = [(0, 0, 0, 1), (1, 1, 1, 2), (2, 1, 2, 3)]
        self.assertEqual(pack_waves(requests, 1), [[0], [1], [2]])

    def test_packed_waves_respect_both_endpoint_capacities(self):
        requests = [(i, i, 0, 1+i % 3) for i in range(11)]
        for capacity in [1, 3, 4]:
            waves = pack_waves(requests, capacity)
            self.assertEqual(sorted(rid for wave in waves for rid in wave), list(range(11)))
            for wave in waves:
                load = Counter(core for rid in wave for core in requests[rid][2:])
                self.assertLessEqual(max(load.values()), capacity)

    def test_shortest_mesh_alternatives_and_mandatory_relays(self):
        self.assertEqual(shortest_mesh_paths(0, 2), ((0, 1, 2),))
        alternatives = shortest_mesh_paths(0, 5)
        self.assertEqual(set(alternatives), {(0, 1, 5), (0, 4, 5)})
        self.assertEqual(set.intersection(*(set(path) for path in alternatives)), {0, 5})
        self.assertEqual(len(shortest_mesh_paths(0, 15)), 20)


if __name__ == '__main__':
    unittest.main()
