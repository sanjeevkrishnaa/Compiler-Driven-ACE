"""Reservation identity: two requests are two bookings, however alike they look."""
from types import SimpleNamespace
import unittest

from execution_events import ListRecorder, MisRemoved, Unbooked
from reservation import (
    ApplicationReservation, ObservedTimeCard, ReservationAdaptive, ResourceReservationProtocolAdaptive,
    describe_reservation,
)
from sequence.network_management.reservation import (
    QCap, Reservation, ResourceReservationMessage, RSVPMsgType,
)


def application(identity, **overrides):
    fields = dict(initiator="a", responder="b", start_time=10, end_time=100, memory_size=1, fidelity=0.01)
    fields.update(overrides)
    return ApplicationReservation(fields["initiator"], fields["responder"], fields["start_time"],
                                  fields["end_time"], fields["memory_size"], fields["fidelity"],
                                  entanglement_number=1, identity=identity)


class EqualityTests(unittest.TestCase):
    def test_requests_that_differ_only_in_identity_are_distinct_reservations(self):
        first, second = application(1), application(2)
        self.assertNotEqual(first, second)
        self.assertEqual(len({first, second}), 2)

    def test_the_same_request_is_equal_to_a_copy_of_itself(self):
        """Equality is by value, so a copy (as across processes) is still the same booking."""
        self.assertEqual(application(7), application(7))
        self.assertEqual(hash(application(7)), hash(application(7)))
        self.assertEqual(len({application(7), application(7)}), 1)

    def test_any_other_field_still_distinguishes_reservations(self):
        base = application(1)
        for other in (application(1, initiator="c"), application(1, responder="c"), application(1, start_time=11),
                      application(1, end_time=101), application(1, memory_size=2), application(1, fidelity=0.02)):
            self.assertNotEqual(base, other)

    def test_a_resubmission_with_a_new_window_is_not_the_attempt_it_replaces(self):
        self.assertNotEqual(application(5, start_time=10, end_time=60), application(5, start_time=1010, end_time=1060))

    def test_an_application_reservation_never_equals_an_adaptive_or_a_stock_one(self):
        mine = application(0)
        adaptive = ReservationAdaptive("a", "b", 10, 100, 1, 0.01)
        stock = Reservation("a", "b", 10, 100, 1, 0.01)
        for other in (adaptive, stock):
            self.assertNotEqual(mine, other)
            self.assertNotEqual(other, mine)            # symmetric, in both directions
        self.assertNotEqual(ReservationAdaptive("a", "b", 10, 100, 1, 0.01, compiler_target_request_id=0), mine)

    def test_the_autonomous_protocols_keep_their_existing_contract(self):
        """CGP/ACGP reservations still equal an ordinary Reservation; the audit found no aliasing among them."""
        adaptive = ReservationAdaptive("a", "b", 10, 100, 1, 0.9)
        stock = Reservation("a", "b", 10, 100, 1, 0.9)
        self.assertEqual(adaptive, stock)
        self.assertEqual(hash(adaptive), hash(stock))

    def test_events_label_application_and_adaptive_reservations(self):
        self.assertEqual(describe_reservation(application(4)), (4, "application"))
        self.assertEqual(describe_reservation(ReservationAdaptive("a", "b", 1, 2, 1, 0.9,
                                                                  compiler_target_request_id=9)), (9, "adaptive"))
        self.assertEqual(describe_reservation(ReservationAdaptive("a", "b", 1, 2, 1, 0.9)), (-1, "adaptive"))


class TimecardTests(unittest.TestCase):
    def card(self):
        recorder = ListRecorder()
        owner = SimpleNamespace(name="r", recorder=recorder, timeline=SimpleNamespace(now=lambda: 0))
        return ObservedTimeCard(0, owner), recorder

    def test_removing_one_request_never_releases_another_that_looks_alike(self):
        card, recorder = self.card()
        first, second = application(1), application(2)
        self.assertTrue(card.add(first))
        self.assertFalse(card.remove(second))              # it holds nothing for request 2
        self.assertEqual(card.reservations, [first])
        self.assertEqual(recorder.events[-1].__class__.__name__, "Booked")
        self.assertTrue(card.remove(first))
        released = [e for e in recorder.events if isinstance(e, Unbooked)]
        self.assertEqual(len(released), 1)
        self.assertFalse([e for e in recorder.events if isinstance(e, MisRemoved)])

    def test_the_booking_event_carries_the_reservations_hash(self):
        card, recorder = self.card()
        reservation = application(3)
        card.add(reservation)
        self.assertEqual(recorder.events[0].key_hash, hash(reservation))


class PushTests(unittest.TestCase):
    """``push`` must behave exactly as the stock protocol's, with one difference: the class."""

    def protocol(self, accept):
        protocol = ResourceReservationProtocolAdaptive.__new__(ResourceReservationProtocolAdaptive)
        protocol.owner = SimpleNamespace(name="a")
        protocol.name = "a.RSVP"
        protocol.schedule = lambda reservation: accept
        protocol.pushed, protocol.popped = [], []
        protocol._push = lambda **kwargs: protocol.pushed.append(kwargs)
        protocol._pop = lambda **kwargs: protocol.popped.append(kwargs)
        return protocol

    def test_an_accepted_request_is_forwarded_toward_the_responder_as_an_application_reservation(self):
        protocol = self.protocol(accept=True)
        protocol.push("b", 10, 100, 1, 0.01, entanglement_number=1, identity=7)
        self.assertEqual(protocol.popped, [])
        (call,) = protocol.pushed
        message = call["msg"]
        self.assertEqual(call["dst"], "b")
        self.assertEqual(message.msg_type, RSVPMsgType.REQUEST)
        self.assertIsInstance(message.reservation, ApplicationReservation)
        self.assertEqual((message.reservation.initiator, message.reservation.responder, message.reservation.identity,
                          message.reservation.start_time, message.reservation.end_time,
                          message.reservation.memory_size, message.reservation.fidelity,
                          message.reservation.entanglement_number), ("a", "b", 7, 10, 100, 1, 0.01, 1))
        self.assertEqual([q.node for q in message.qcaps], ["a"])

    def test_a_rejected_request_is_popped_back_up_with_an_empty_path(self):
        protocol = self.protocol(accept=False)
        protocol.push("b", 10, 100, 1, 0.01, identity=3)
        self.assertEqual(protocol.pushed, [])
        (call,) = protocol.popped
        self.assertEqual(call["msg"].msg_type, RSVPMsgType.REJECT)
        self.assertEqual(call["msg"].path, [])
        self.assertIsInstance(call["msg"].reservation, ApplicationReservation)

    def test_the_stock_protocol_would_have_built_a_plain_reservation(self):
        """The reason for the override: the stock class aliases, and it hard-codes ``Reservation``."""
        stock = Reservation("a", "b", 10, 100, 1, 0.01, 1, 1)
        other = Reservation("a", "b", 10, 100, 1, 0.01, 1, 2)
        self.assertEqual(stock, other)
        self.assertEqual(hash(stock), hash(other))


if __name__ == "__main__":
    unittest.main()
