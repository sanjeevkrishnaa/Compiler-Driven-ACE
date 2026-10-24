import unittest

from execution_events import (
    ADAPTIVE, APPLICATION, Booked, ListRecorder, MisRemoved, NullRecorder, PairCredited,
    PairDelivered, RequestCompleted, RequestRejected, RequestSubmitted, Unbooked, canonical,
)
from invariants import (
    ALIASED_RESERVATIONS, BOOKING_SURVIVES_COMPLETION, COMPLETION_COUNT, CREDIT_EXCEEDS_REQUEST,
    CREDIT_WITHOUT_BOOKING,
    LAYER_BARRIER, MEMORY_DOUBLE_BOOKED, MISREMOVAL, ORPHAN_PAIR, RELEASE_NOT_LIVE,
    STALE_BOOKING_ON_RESUBMIT, SUBMISSION_BEFORE_PREDECESSOR, USE_ORDER, RequestInfo,
    check_events, summarize,
)


def book(t, node, mem, rid, request, kind=APPLICATION):
    return Booked(t, node, mem, rid, request, kind)


def unbook(t, node, mem, rid, request, kind=APPLICATION, reason="completed"):
    return Unbooked(t, node, mem, rid, request, kind, reason)


def names(violations):
    return [v.invariant for v in violations]


def one_request_log(request=0, rid=100):
    """A correct run of a single request: book, deliver, credit, complete, release."""
    return [
        RequestSubmitted(0, request, 0),
        book(1, "a", 0, rid, request), book(1, "b", 0, rid, request),
        PairDelivered(10, "a", 0), PairDelivered(10, "b", 0),
        PairCredited(10, "b", 0, rid, request, "responder"),
        PairCredited(10, "a", 0, rid, request, "initiator"),
        RequestCompleted(10, request),
        unbook(10, "a", 0, rid, request), unbook(10, "b", 0, rid, request),
    ]


class CleanRunTests(unittest.TestCase):
    def test_a_correct_run_has_no_violations(self):
        self.assertEqual(check_events(one_request_log(), require_completion=False), [])

    def test_null_recorder_discards_and_list_recorder_keeps_order(self):
        NullRecorder().record(RequestCompleted(0, 1))
        recorder = ListRecorder()
        events = one_request_log()
        for event in events:
            recorder.record(event)
        self.assertEqual(recorder.events, events)


class CanonicalTests(unittest.TestCase):
    def test_object_ids_become_first_seen_ordinals_so_runs_compare_equal(self):
        first = [book(1, "a", 0, 9001, 0), book(1, "a", 1, 9002, 1), unbook(2, "a", 0, 9001, 0)]
        second = [book(1, "a", 0, 77, 0), book(1, "a", 1, 12, 1), unbook(2, "a", 0, 77, 0)]
        self.assertNotEqual(first, second)
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual([e.reservation_id for e in canonical(first)], [0, 1, 0])

    def test_distinct_objects_stay_distinct(self):
        log = [book(1, "a", 0, 5, 0), book(1, "a", 1, 6, 0)]
        ids = [e.reservation_id for e in canonical(log)]
        self.assertEqual(len(set(ids)), 2)

    def test_misremoval_ids_share_the_same_numbering(self):
        log = [book(1, "a", 0, 5, 0), MisRemoved(2, "a", 0, requested_id=6, removed_id=5, request_id=1)]
        done = canonical(log)
        self.assertEqual(done[1].removed_id, done[0].reservation_id)
        self.assertNotEqual(done[1].requested_id, done[1].removed_id)

    def test_events_without_ids_and_the_input_log_are_untouched(self):
        log = [RequestSubmitted(0, 1, 0), RequestCompleted(5, 1)]
        self.assertEqual(canonical(log), log)
        original = [book(1, "a", 0, 9001, 0)]
        canonical(original)
        self.assertEqual(original[0].reservation_id, 9001)


class AliasingTests(unittest.TestCase):
    def test_two_live_reservations_with_the_same_key_hash_are_flagged(self):
        log = [Booked(1, "a", 0, 1, 0, APPLICATION, key_hash=77), Booked(2, "a", 1, 2, 1, APPLICATION, key_hash=77)]
        found = check_events(log)
        self.assertEqual(names(found), [ALIASED_RESERVATIONS])
        self.assertIn("request 1", found[0].detail)

    def test_different_hashes_do_not_alias(self):
        log = [Booked(1, "a", 0, 1, 0, APPLICATION, key_hash=77), Booked(2, "a", 1, 2, 1, APPLICATION, key_hash=78)]
        self.assertEqual(check_events(log), [])

    def test_one_reservation_booking_several_memories_is_not_aliasing_itself(self):
        log = [Booked(1, "a", 0, 1, 0, APPLICATION, key_hash=77), Booked(1, "b", 0, 1, 0, APPLICATION, key_hash=77)]
        self.assertEqual(check_events(log), [])

    def test_equal_hashes_across_kinds_are_not_aliasing(self):
        log = [Booked(1, "a", 0, 1, 0, APPLICATION, key_hash=77), Booked(2, "a", 1, 2, -1, ADAPTIVE, key_hash=77)]
        self.assertEqual(check_events(log), [])

    def test_sequential_reservations_with_the_same_key_are_not_aliasing(self):
        log = [Booked(1, "a", 0, 1, 0, APPLICATION, key_hash=77), unbook(2, "a", 0, 1, 0),
               Booked(3, "a", 0, 2, 0, APPLICATION, key_hash=77)]
        self.assertEqual(check_events(log), [])

    def test_a_missing_hash_disables_the_check_for_that_booking(self):
        log = [book(1, "a", 0, 1, 0), book(2, "a", 1, 2, 1)]
        self.assertEqual(check_events(log), [])


class MemoryOwnershipTests(unittest.TestCase):
    def test_booking_a_held_memory_for_another_reservation_is_flagged(self):
        log = [book(1, "a", 0, 1, 0), book(2, "a", 0, 2, 1)]
        self.assertEqual(names(check_events(log)), [MEMORY_DOUBLE_BOOKED])

    def test_rebooking_the_same_reservation_is_not_double_booking(self):
        log = [book(1, "a", 0, 1, 0), book(2, "a", 0, 1, 0)]
        self.assertEqual(check_events(log), [])

    def test_releasing_twice_is_flagged(self):
        log = [book(1, "a", 0, 1, 0), unbook(2, "a", 0, 1, 0), unbook(3, "a", 0, 1, 0)]
        self.assertEqual(names(check_events(log)), [RELEASE_NOT_LIVE])

    def test_releasing_a_memory_that_another_reservation_holds_is_flagged(self):
        log = [book(1, "a", 0, 1, 0), unbook(2, "a", 0, 2, 1)]
        self.assertEqual(names(check_events(log)), [RELEASE_NOT_LIVE])

    def test_misremoval_is_flagged_and_frees_what_was_removed(self):
        log = [book(1, "a", 0, 1, 0), MisRemoved(2, "a", 0, requested_id=2, removed_id=1, request_id=1),
               book(3, "a", 0, 3, 2)]
        self.assertEqual(names(check_events(log)), [MISREMOVAL])

    def test_phantom_booking_when_a_request_is_resubmitted(self):
        log = [RequestSubmitted(0, 7, 0), book(1, "a", 0, 1, 7), RequestSubmitted(60, 7, 1)]
        self.assertEqual(names(check_events(log)), [STALE_BOOKING_ON_RESUBMIT])

    def test_resubmitting_after_the_old_booking_was_released_is_clean(self):
        log = [RequestSubmitted(0, 7, 0), book(1, "a", 0, 1, 7), unbook(50, "a", 0, 1, 7, reason="timeout"),
               RequestSubmitted(60, 7, 1)]
        self.assertEqual(check_events(log), [])

    def test_a_booking_that_exists_before_the_first_submission_is_not_stale(self):
        """Early generation may hold a memory for a hop before that hop is submitted."""
        log = [book(1, "a", 0, 1, 7), RequestSubmitted(2, 7, 0)]
        self.assertEqual(check_events(log), [])

    def test_adaptive_bookings_and_other_requests_do_not_count_as_stale(self):
        log = [book(1, "a", 0, 1, 7, ADAPTIVE), book(1, "a", 1, 2, 8), RequestSubmitted(60, 7, 1)]
        self.assertEqual(check_events(log), [])

    def test_booking_that_outlives_the_completed_request_is_flagged(self):
        log = one_request_log()[:-2]          # never released
        found = check_events(log)
        self.assertEqual(names(found), [BOOKING_SURVIVES_COMPLETION])
        self.assertIn("a[0]", found[0].detail)

    def test_a_failed_attempts_booking_does_not_count_against_the_completing_reservation(self):
        log = [RequestSubmitted(0, 0, 0), book(1, "a", 0, 50, 0), unbook(2, "a", 0, 50, 0, reason="rejected")] + [
            e for e in one_request_log(0, 100) if not isinstance(e, RequestSubmitted)]
        self.assertEqual(check_events(log), [])


class PairOwnershipTests(unittest.TestCase):
    def test_pair_delivered_into_an_unheld_memory_is_an_orphan(self):
        self.assertEqual(names(check_events([PairDelivered(5, "a", 3)])), [ORPHAN_PAIR])

    def test_a_pair_in_a_memory_held_by_an_adaptive_reservation_is_not_an_orphan(self):
        log = [book(1, "a", 3, 9, 0, ADAPTIVE), PairDelivered(5, "a", 3)]
        self.assertEqual(check_events(log), [])

    def test_credit_to_a_reservation_that_does_not_hold_the_memory(self):
        log = [book(1, "a", 0, 1, 0), PairCredited(5, "a", 0, 2, 1, "initiator")]
        self.assertEqual(CREDIT_WITHOUT_BOOKING, names(check_events(log))[0])

    def test_credit_after_release_is_flagged(self):
        log = [book(1, "a", 0, 1, 0), unbook(2, "a", 0, 1, 0), PairCredited(5, "a", 0, 1, 0, "initiator")]
        self.assertIn(CREDIT_WITHOUT_BOOKING, names(check_events(log)))

    def test_two_credits_to_one_reservation_side_exceed_a_single_pair_request(self):
        log = [book(1, "a", 0, 1, 0), PairCredited(5, "a", 0, 1, 0, "initiator"),
               PairCredited(6, "a", 0, 1, 0, "initiator")]
        self.assertEqual(names(check_events(log)), [CREDIT_EXCEEDS_REQUEST])

    def test_two_credits_are_fine_when_two_pairs_were_requested(self):
        info = {0: RequestInfo(0, layer=0, qubit=0, order=0, pairs_required=2)}
        log = [book(1, "a", 0, 1, 0), PairCredited(5, "a", 0, 1, 0, "initiator"),
               PairCredited(6, "a", 0, 1, 0, "initiator")]
        self.assertEqual(check_events(log, info), [])

    def test_the_two_sides_are_counted_separately(self):
        log = [book(1, "a", 0, 1, 0), book(1, "b", 0, 1, 0),
               PairCredited(5, "b", 0, 1, 0, "responder"), PairCredited(5, "a", 0, 1, 0, "initiator")]
        self.assertEqual(check_events(log), [])

    def test_completing_twice_is_flagged(self):
        log = [RequestCompleted(1, 0), RequestCompleted(2, 0)]
        self.assertEqual(names(check_events(log)), [COMPLETION_COUNT])

    def test_a_missing_completion_is_only_flagged_when_completion_is_required(self):
        info = {0: RequestInfo(0, 0, 0, 0), 1: RequestInfo(1, 0, 1, 1)}
        log = [RequestCompleted(1, 0)]
        self.assertEqual(check_events(log, info), [])
        found = check_events(log, info, require_completion=True)
        self.assertEqual(names(found), [COMPLETION_COUNT])
        self.assertIn("request 1", found[0].detail)


class OrderingTests(unittest.TestCase):
    CHAIN = {
        0: RequestInfo(0, layer=0, qubit=5, order=0),
        1: RequestInfo(1, layer=0, qubit=5, order=1),
        2: RequestInfo(2, layer=0, qubit=6, order=2),
    }

    def test_hops_of_one_qubit_completing_in_trace_order_is_clean(self):
        log = [RequestSubmitted(0, 0, 0), RequestSubmitted(0, 1, 0), RequestSubmitted(0, 2, 0),
               RequestCompleted(10, 0), RequestCompleted(12, 1), RequestCompleted(5, 2)]
        self.assertEqual(check_events(log, self.CHAIN), [])

    def test_a_later_hop_completing_before_an_earlier_one_is_flagged(self):
        log = [RequestSubmitted(0, 0, 0), RequestSubmitted(0, 1, 0),
               RequestCompleted(10, 0), RequestCompleted(4, 1)]
        self.assertEqual(names(check_events(log, self.CHAIN)), [USE_ORDER])

    def test_different_qubits_are_free_to_complete_in_any_order(self):
        log = [RequestSubmitted(0, 0, 0), RequestSubmitted(0, 2, 0), RequestCompleted(10, 0), RequestCompleted(2, 2)]
        self.assertEqual(check_events(log, self.CHAIN), [])

    def test_submission_before_the_predecessor_completes_is_only_flagged_on_request(self):
        log = [RequestSubmitted(0, 0, 0), RequestSubmitted(3, 1, 0), RequestCompleted(10, 0), RequestCompleted(12, 1)]
        self.assertEqual(check_events(log, self.CHAIN), [])
        found = check_events(log, self.CHAIN, submission_after_predecessor=True)
        self.assertEqual(names(found), [SUBMISSION_BEFORE_PREDECESSOR])

    def test_just_in_time_submission_passes_the_strict_check(self):
        log = [RequestSubmitted(0, 0, 0), RequestCompleted(10, 0), RequestSubmitted(10, 1, 0), RequestCompleted(14, 1)]
        self.assertEqual(check_events(log, self.CHAIN, submission_after_predecessor=True), [])

    def test_a_layer_starting_before_the_previous_one_finished_is_flagged(self):
        info = {0: RequestInfo(0, 0, 1, 0), 1: RequestInfo(1, 1, 2, 0)}
        log = [RequestSubmitted(0, 0, 0), RequestSubmitted(5, 1, 0), RequestCompleted(10, 0), RequestCompleted(12, 1)]
        self.assertEqual(names(check_events(log, info)), [LAYER_BARRIER])

    def test_a_layer_starting_when_the_previous_finished_is_clean(self):
        info = {0: RequestInfo(0, 0, 1, 0), 1: RequestInfo(1, 1, 2, 0)}
        log = [RequestSubmitted(0, 0, 0), RequestCompleted(10, 0), RequestSubmitted(10, 1, 0), RequestCompleted(12, 1)]
        self.assertEqual(check_events(log, info), [])

    def test_retries_do_not_move_the_first_submission_time(self):
        info = {0: RequestInfo(0, 0, 1, 0), 1: RequestInfo(1, 1, 2, 0)}
        log = [RequestSubmitted(0, 0, 0), RequestRejected(1, 0), RequestSubmitted(2, 0, 1), RequestCompleted(10, 0),
               RequestSubmitted(10, 1, 0), RequestCompleted(12, 1)]
        self.assertEqual(check_events(log, info), [])

    def test_ordering_checks_are_skipped_without_metadata(self):
        log = [RequestSubmitted(0, 0, 0), RequestCompleted(10, 0), RequestCompleted(4, 1)]
        self.assertEqual(check_events(log), [])


class ReportingTests(unittest.TestCase):
    def test_violations_come_back_in_a_deterministic_order_and_can_be_summarised(self):
        log = [PairDelivered(9, "a", 0), PairDelivered(3, "b", 0), book(1, "c", 0, 1, 0), book(2, "c", 0, 2, 1)]
        found = check_events(log)
        self.assertEqual([v.time_ps for v in found], [2, 3, 9])
        self.assertEqual(dict(summarize(found)), {MEMORY_DOUBLE_BOOKED: 1, ORPHAN_PAIR: 2})
        self.assertEqual(found, check_events(log))


if __name__ == "__main__":
    unittest.main()
