"""Unit tests for compiler-specific EPR lifecycle behavior."""

import unittest

from adaptive_continuous import AdaptiveContinuousProtocol
from parallel_core import reseed_topology_nodes, serialize_core_conflicts
from reservation import (
    ReservationAdaptive, ResourceReservationProtocolAdaptive,
    eg_rule_condition_one_shot,
)


class _MemoryInfo:
    state = "RAW"
    index = 0


class CompilerOneShotTests(unittest.TestCase):
    def test_static_partition_keeps_compiler_and_demand_timecards_disjoint(self):
        class Owner:
            name = "router_0_0"

        class Card:
            def __init__(self, index):
                self.memory_index = index
                self.reservations = []

            def add(self, reservation):
                self.reservations.append(reservation)
                return True

            def remove(self, reservation):
                self.reservations.remove(reservation)

        class ApplicationReservation:
            initiator = "router_0_0"
            responder = "router_0_1"
            memory_size = 1

        protocol = ResourceReservationProtocolAdaptive.__new__(
            ResourceReservationProtocolAdaptive
        )
        protocol.owner = Owner()
        protocol.timecards = [Card(index) for index in range(4)]
        protocol.set_static_memory_partition(2)
        compiler = ReservationAdaptive(
            "router_0_0", "router_0_1", 1, 2, 1, 0.9,
            compiler_target_request_id=1,
        )
        self.assertTrue(protocol.schedule(compiler))
        self.assertTrue(protocol.schedule(ApplicationReservation()))
        self.assertEqual(protocol.timecards[0].reservations, [compiler])
        self.assertEqual(protocol.timecards[1].reservations, [])
        self.assertEqual(protocol.timecards[2].reservations[0].__class__,
                         ApplicationReservation)
        self.assertEqual(protocol.timecards[3].reservations, [])

    def test_experiment_seed_reseeds_every_node_but_preserves_seed_zero(self):
        class Node:
            def __init__(self, name, seed):
                self.name, self.seed = name, seed

            def get_seed(self):
                return self.seed

            def set_seed(self, seed):
                self.seed = seed

        class Topology:
            nodes = {"router": [Node("r0", 0), Node("r1", 1)],
                     "bsm": [Node("b0", 0)]}

            def get_nodes(self):
                return self.nodes

        topology = Topology()
        self.assertEqual(
            reseed_topology_nodes(topology, 0),
            {"b0": 0, "r0": 0, "r1": 1},
        )
        self.assertEqual(
            reseed_topology_nodes(topology, 2),
            {"b0": 2_000_006, "r0": 2_000_006, "r1": 2_000_007},
        )
    def test_core_conflicts_are_split_but_disjoint_requests_stay_parallel(self):
        requests = [[
            (0, "a", "b", 1, 0.01, 1),
            (1, "b", "c", 1, 0.01, 1),
            (2, "d", "e", 1, 0.01, 1),
        ]]
        batches, origins = serialize_core_conflicts(requests)

        self.assertEqual([[request[0] for request in batch] for batch in batches], [[0, 2], [1]])
        self.assertEqual(origins, [0, 0])

    def test_bipartite_edge_coloring_uses_the_minimum_number_of_batches(self):
        edges = [
            (0, "c", "d", 1, 0.01, 1), (1, "a", "b", 1, 0.01, 1),
            (2, "b", "f", 1, 0.01, 1), (3, "f", "g", 1, 0.01, 1),
            (4, "g", "h", 1, 0.01, 1), (5, "h", "i", 1, 0.01, 1),
            (6, "i", "j", 1, 0.01, 1), (7, "j", "k", 1, 0.01, 1),
            (8, "k", "l", 1, 0.01, 1), (9, "l", "d", 1, 0.01, 1),
        ]
        batches, origins = serialize_core_conflicts([edges])
        self.assertEqual(len(batches), 2)  # maximum endpoint degree is two
        self.assertEqual(origins, [0, 0])
        self.assertEqual(sum(map(len, batches)), len(edges))
        for batch in batches:
            endpoints = [endpoint for request in batch for endpoint in request[1:3]]
            self.assertEqual(len(endpoints), len(set(endpoints)))

    def test_generation_rule_stops_after_first_compiler_pair(self):
        reservation = ReservationAdaptive(
            "router_0_0", "router_0_1", 1, 2, 1, 0.9,
            compiler_target_request_id=7,
        )
        args = {"memory_indices": [0], "reservation": reservation}
        memory_info = _MemoryInfo()

        self.assertEqual(
            eg_rule_condition_one_shot(memory_info, None, args),
            [memory_info],
        )
        reservation.compiler_pair_generated = True
        self.assertEqual(
            eg_rule_condition_one_shot(memory_info, None, args),
            [],
        )

    def test_future_compiler_pair_is_not_stolen_by_another_request(self):
        protocol = AdaptiveContinuousProtocol.__new__(AdaptiveContinuousProtocol)
        targeted_pair = (("router_0_0", "m0"), ("router_0_1", "m0"))
        generic_pair = (("router_0_0", "m1"), ("router_0_1", "m1"))
        protocol.generated_entanglement_pairs = {targeted_pair}
        protocol.generated_pair_metadata = {
            targeted_pair: {"target_request_id": 7},
        }
        protocol.strategy = "freshest"
        protocol.compiler_observer = None
        protocol.get_fidelity = lambda pair: 0.9

        self.assertEqual(
            protocol.match_generated_entanglement_pair(
                "router_0_0", "router_0_1", request_id=7
            ),
            targeted_pair,
        )
        self.assertIsNone(
            protocol.match_generated_entanglement_pair(
                "router_0_0", "router_0_1", request_id=8
            )
        )

        protocol.generated_entanglement_pairs.add(generic_pair)
        self.assertEqual(
            protocol.match_generated_entanglement_pair(
                "router_0_0", "router_0_1", request_id=8
            ),
            generic_pair,
        )


if __name__ == "__main__":
    unittest.main()
