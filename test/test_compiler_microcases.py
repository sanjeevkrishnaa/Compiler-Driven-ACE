"""Microcases on the real ACE simulator, each with the invariant monitor attached.

No mocks: every case runs ``run_parallel_experiment`` on the 4x4 mesh with speculative
generation switched off, so the only demand is the requests given.  Core numbering is row
major, so core 9 is router_2_1 and its neighbours are 5, 8, 10 and 13.
"""
import unittest

from execution_events import Booked, RequestCompleted, RequestRejected, Unbooked, canonical
from invariants import ORPHAN_PAIR, summarize
from compiler_trace import router_name
from tools.ace_correctness.harness import Hop, are_neighbours, run_layers

SAME_LINK = [[Hop(i, 5, 9, qubit=i) for i in range(4)]]
FOUR_LINKS_THROUGH_CORE_9 = [[Hop(0, 9, 10, 0), Hop(1, 9, 8, 1), Hop(2, 5, 9, 2), Hop(3, 13, 9, 3)]]
RESPONDER_CONFLICT = [[Hop(0, 9, 10, 0), Hop(1, 14, 10, 1)]]       # two single links into core 10


class ConcurrentDemandTests(unittest.TestCase):
    def test_distinct_reservations_on_one_link_overlap_without_a_retry(self):
        outcome = run_layers(SAME_LINK, memories=32, distinct_fidelity_targets=True)
        self.assertEqual((outcome.completed, outcome.total_retries), (4, 0))
        self.assertEqual(outcome.violations, [])
        self.assertLess(max(outcome.latencies_ms.values()), 5.0)

    def test_different_links_through_one_core_overlap_without_a_retry(self):
        outcome = run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=4)
        self.assertEqual((outcome.completed, outcome.total_retries), (4, 0))
        self.assertEqual(outcome.violations, [])
        self.assertLess(max(outcome.latencies_ms.values()), 5.0)

    def test_one_memory_per_core_makes_requests_wait_and_all_still_complete(self):
        outcome = run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=1)
        self.assertEqual(outcome.completed, 4)
        self.assertGreater(outcome.total_retries, 0)
        self.assertGreater(max(outcome.latencies_ms.values()), 5.0)       # waiting, not generation
        self.assertEqual(outcome.violations, [])

    def test_more_memory_never_makes_the_slowest_request_slower_here(self):
        slowest = [max(run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=m).latencies_ms.values())
                   for m in (1, 2, 4)]
        self.assertGreaterEqual(slowest[0], slowest[1])
        self.assertGreaterEqual(slowest[1], slowest[2])


class RejectionTests(unittest.TestCase):
    def test_a_rejection_at_the_responder_releases_the_initiators_booking_exactly_once(self):
        outcome = run_layers(RESPONDER_CONFLICT, memories=1)
        self.assertEqual(outcome.completed, 2)
        self.assertEqual(outcome.violations, [])
        initiator = router_name(14, 4)
        mine = [e for e in outcome.events
                if isinstance(e, (Booked, Unbooked)) and e.request_id == 1 and e.node == initiator]
        booked = [e for e in mine if isinstance(e, Booked)]
        released = [e for e in mine if isinstance(e, Unbooked)]
        self.assertGreater(len(booked), 1, "the request should have been rejected and retried")
        self.assertEqual(len(booked), len(released), "every booking is released exactly once")
        self.assertEqual([e.reason for e in released], ["removed"] * (len(released) - 1) + ["completed"])
        rejected = [e for e in outcome.events if isinstance(e, RequestRejected) and e.request_id == 1]
        self.assertEqual(len(rejected), len(booked) - 1)

    def test_the_rejected_request_completes_after_the_one_holding_the_memory(self):
        outcome = run_layers(RESPONDER_CONFLICT, memories=1)
        done = {e.request_id: e.time_ps for e in outcome.events if isinstance(e, RequestCompleted)}
        self.assertLess(done[0], done[1])


class AliasingTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_identical_looking_requests_on_one_link_complete_without_a_retry(self):
        """The behaviour a correct ACE must have. It fails today because SeQUeNCe's
        Reservation compares equal for equal endpoints, window, size and fidelity, so the
        reservations alias; the marker comes off when the reservation identity is fixed."""
        outcome = run_layers(SAME_LINK, memories=32)
        self.assertEqual((outcome.completed, outcome.total_retries), (4, 0))
        self.assertEqual(outcome.violations, [])

    def test_the_monitor_flags_the_legacy_aliasing_failure(self):
        """Characterisation of the current defect, deleted together with the fix: the
        second pair lands in a memory whose reservation has already been released."""
        outcome = run_layers(SAME_LINK, memories=32)
        self.assertGreater(outcome.total_retries, 0)
        self.assertIn(ORPHAN_PAIR, summarize(outcome.violations))


class HarnessTests(unittest.TestCase):
    def test_non_adjacent_requests_are_refused(self):
        with self.assertRaises(ValueError):
            run_layers([[Hop(0, 8, 10)]], memories=1)

    def test_neighbours_on_the_mesh(self):
        self.assertTrue(are_neighbours(9, 10) and are_neighbours(9, 5) and are_neighbours(9, 13))
        self.assertFalse(are_neighbours(9, 11) or are_neighbours(3, 4) or are_neighbours(9, 9))

    def test_the_same_seed_reproduces_the_event_log_exactly(self):
        first = run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=2, seed=3)
        second = run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=2, seed=3)
        self.assertEqual(canonical(first.events), canonical(second.events))
        self.assertEqual(first.latencies_ms, second.latencies_ms)

    def test_a_different_seed_changes_the_sampling(self):
        first = run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=4, seed=0)
        second = run_layers(FOUR_LINKS_THROUGH_CORE_9, memories=4, seed=1)
        self.assertNotEqual(first.latencies_ms, second.latencies_ms)


if __name__ == "__main__":
    unittest.main()
