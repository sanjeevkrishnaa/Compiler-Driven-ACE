"""Unit tests for compiler-specific EPR lifecycle behavior."""

import unittest

from adaptive_continuous import AdaptiveContinuousProtocol
from parallel_core import serialize_core_conflicts
from reservation import ReservationAdaptive, eg_rule_condition_one_shot


class _MemoryInfo:
    state = "RAW"
    index = 0


class CompilerOneShotTests(unittest.TestCase):
    def test_core_conflicts_are_split_but_disjoint_requests_stay_parallel(self):
        requests = [[
            (0, "a", "b", 1, 0.01, 1),
            (1, "b", "c", 1, 0.01, 1),
            (2, "d", "e", 1, 0.01, 1),
        ]]
        batches, origins = serialize_core_conflicts(requests)

        self.assertEqual([[request[0] for request in batch] for batch in batches], [[0, 2], [1]])
        self.assertEqual(origins, [0, 0])

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
