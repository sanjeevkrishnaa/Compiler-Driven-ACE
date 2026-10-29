"""Ready-pair admission must beat competing ODG without serializing independent work."""
from types import SimpleNamespace
import unittest

from request_scheduler import QubitOrderedRequestManager
from adaptive_continuous import AdaptiveContinuousProtocol


class AdmissionTests(unittest.TestCase):
    def manager(self, requests, slots, ready, priority="ready-first"):
        manager = QubitOrderedRequestManager.__new__(QubitOrderedRequestManager)
        manager.timeline = SimpleNamespace(now=lambda: 10)
        manager.waiting = {rid: 0 for rid in requests}
        manager.tuple_by_id = requests
        manager.position = {rid: (0, rid) for rid in requests}
        manager.compiler_controller = SimpleNamespace(request_has_ready_pair=lambda rid: rid in ready)
        manager.admission_priority = priority
        manager.admission_decisions = []
        manager.starvation_guard = True
        manager.request_duration = 50
        manager.in_flight = set()
        manager._reservation_start_time = lambda now: now
        manager._free_memories = lambda name, start, end: slots[name]
        manager._schedule_admission = lambda delay: None
        admitted = []
        def admit(rid, now):
            admitted.append(rid)
            manager.waiting.pop(rid)
            manager.in_flight.add(rid)
        manager._admit = admit
        return manager, admitted

    def test_fifo_reproduces_odg_bypassing_a_ready_pair_at_a_shared_core(self):
        requests = {0: (0, "a", "b", 1), 1: (1, "a", "c", 1), 2: (2, "d", "e", 1)}
        manager, admitted = self.manager(requests, dict.fromkeys("abcde", 1), {1}, "fifo")
        manager._try_admit()
        self.assertEqual(admitted, [0, 2])
        self.assertEqual(manager.admission_decisions[0]["bypassed_ready_ids"], [1])

    def test_ready_first_prevents_the_bypass_and_keeps_disjoint_odg_concurrent(self):
        requests = {0: (0, "a", "b", 1), 1: (1, "a", "c", 1), 2: (2, "d", "e", 1)}
        manager, admitted = self.manager(requests, dict.fromkeys("abcde", 1), {1})
        manager._try_admit()
        self.assertEqual(admitted, [1, 2])
        self.assertTrue(all(not d["bypassed_ready_ids"] for d in manager.admission_decisions))

    def test_remaining_slots_admit_multiple_odg_requests_on_the_same_core(self):
        requests = {0: (0, "a", "b", 1), 1: (1, "a", "c", 1), 2: (2, "a", "d", 1)}
        manager, admitted = self.manager(requests, dict(a=3, b=1, c=1, d=1), {0})
        manager._try_admit()
        self.assertEqual(admitted, [0, 1, 2])
        self.assertEqual([d["time_ps"] for d in manager.admission_decisions], [10, 10, 10])

    def test_a_later_pair_becoming_ready_reorders_only_the_waiting_requests(self):
        requests = {0: (0, "a", "b", 1), 1: (1, "a", "c", 1)}
        ready = set()
        slots = dict(a=0, b=1, c=1)
        manager, admitted = self.manager(requests, slots, ready)
        manager._try_admit()
        self.assertEqual(admitted, [])
        ready.add(1)
        slots["a"] = 1
        manager._try_admit()
        self.assertEqual(admitted, [1])

    def test_blocked_ready_request_keeps_its_free_endpoint_without_blocking_disjoint_odg(self):
        requests = {0: (0, "a", "b", 1), 1: (1, "a", "c", 1), 2: (2, "d", "e", 1)}
        manager, admitted = self.manager(requests, dict(a=1, b=0, c=1, d=1, e=1), {0})
        manager.starvation_guard = False
        manager._try_admit()
        self.assertEqual(admitted, [2])

    def test_pair_readiness_wakes_admission_without_waiting_for_a_memory_release(self):
        manager, _ = self.manager({0: (0, "a", "b", 1)}, dict(a=1, b=1), {0})
        scheduled = []
        manager._schedule_admission = scheduled.append
        manager._on_pair_ready()
        self.assertEqual(scheduled, [1])


class ReadinessTests(unittest.TestCase):
    def test_readiness_is_bilateral_targeted_non_consuming_and_fidelity_checked(self):
        pair = (("a", "ma"), ("b", "mb"))
        reverse = (pair[1], pair[0])
        peer = SimpleNamespace(generated_entanglement_pairs={reverse},
                               generated_pair_metadata={reverse: {"target_request_id": 1}})
        protocol = AdaptiveContinuousProtocol.__new__(AdaptiveContinuousProtocol)
        protocol.owner = SimpleNamespace(name="a", timeline=SimpleNamespace(
            get_entity_by_name=lambda name: SimpleNamespace(adaptive_continuous=peer)))
        protocol.generated_entanglement_pairs = {pair}
        protocol.generated_pair_metadata = {pair: {"target_request_id": 1}}
        protocol.get_fidelity = lambda pair: .95
        self.assertTrue(protocol.has_ready_compiler_pair("b", 1, .9))
        self.assertEqual(protocol.generated_entanglement_pairs, {pair})
        self.assertEqual(peer.generated_entanglement_pairs, {reverse})
        self.assertFalse(protocol.has_ready_compiler_pair("b", 2, .9))
        self.assertFalse(protocol.has_ready_compiler_pair("b", 1, .99))
        peer.generated_entanglement_pairs.clear()
        self.assertFalse(protocol.has_ready_compiler_pair("b", 1, .9))


if __name__ == "__main__":
    unittest.main()
