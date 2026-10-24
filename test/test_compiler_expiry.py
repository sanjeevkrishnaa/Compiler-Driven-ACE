"""Windows and expiry: a memory may be booked for a later window while an earlier reservation holds it.

Cached pairs expire when their reservation window ends unused.  A request that arrives just after
that finds the pair gone and books the memory for its own window; for a moment both are on the card,
in sequence.  That is not a double booking, and the invariant checker must tell the two apart.
"""
import collections
import tempfile
import unittest
import zipfile
from pathlib import Path

from execution_events import Booked, Unbooked, reservation_serial
from invariants import MEMORY_DOUBLE_BOOKED, RELEASE_NOT_LIVE, check_events
from tools.ace_correctness.audit_trace import audit_trace

ARCHIVE = Path(__file__).resolve().parents[1] / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
MS = 10**9


def book(time, reservation, start, end, request=0, kind="adaptive", node="n", memory=0):
    return Booked(time, node, memory, reservation, request, kind, None, start, end)


def release(time, reservation, request=0, kind="adaptive", reason="reservation_expired", node="n", memory=0):
    return Unbooked(time, node, memory, reservation, request, kind, reason)


class CheckerWindowTests(unittest.TestCase):
    def kinds(self, events):
        return {v.invariant for v in check_events(events)}

    def test_a_booking_for_a_later_window_on_a_memory_still_held_is_not_a_double_booking(self):
        events = [book(0, 1, 0, 87 * MS), book(82 * MS, 2, 88 * MS, 138 * MS, kind="application"),
                  release(87 * MS, 1), release(88 * MS, 2, kind="application", reason="completed")]
        self.assertEqual(self.kinds(events), set())

    def test_the_two_may_be_released_in_either_order(self):
        events = [book(0, 1, 0, 87 * MS), book(82 * MS, 2, 88 * MS, 138 * MS, kind="application"),
                  release(83 * MS, 2, kind="application", reason="removed"), release(87 * MS, 1)]
        self.assertEqual(self.kinds(events), set())

    def test_overlapping_windows_on_one_memory_are_a_double_booking(self):
        events = [book(0, 1, 0, 100 * MS), book(10 * MS, 2, 50 * MS, 150 * MS, kind="application")]
        self.assertIn(MEMORY_DOUBLE_BOOKED, self.kinds(events))

    def test_windows_that_only_touch_at_an_instant_overlap(self):
        events = [book(0, 1, 0, 50 * MS), book(10 * MS, 2, 50 * MS, 90 * MS, kind="application")]
        self.assertIn(MEMORY_DOUBLE_BOOKED, self.kinds(events))

    def test_a_booking_with_no_window_is_treated_as_overlapping(self):
        events = [Booked(0, "n", 0, 1, 0, "adaptive"), Booked(1, "n", 0, 2, 1, "application")]
        self.assertIn(MEMORY_DOUBLE_BOOKED, self.kinds(events))

    def test_releasing_a_booking_that_was_never_made_is_still_reported(self):
        self.assertIn(RELEASE_NOT_LIVE, self.kinds([release(0, 9)]))

    def test_other_memories_are_independent(self):
        events = [book(0, 1, 0, 100 * MS, memory=0), book(1, 2, 0, 100 * MS, memory=1)]
        self.assertEqual(self.kinds(events), set())


class SerialTests(unittest.TestCase):
    def test_a_serial_is_stable_per_object_and_never_reused(self):
        class Thing:
            pass
        first = Thing()
        number = reservation_serial(first)
        self.assertEqual(reservation_serial(first), number)
        seen = {number}
        for _ in range(200):
            transient = Thing()
            seen.add(reservation_serial(transient))      # freed immediately; its address may be recycled
            del transient
        self.assertEqual(len(seen), 201)


@unittest.skipUnless(ARCHIVE.exists(), "committed MQT archive not present")
class ExpiryOnTheSimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="ace-expiry-")
        with zipfile.ZipFile(ARCHIVE) as archive:
            cls.trace = Path(archive.extract("mqt_ten_workload_study/ghz/seed_42/requests.txt", cls.directory.name))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_pairs_that_expire_unused_leave_every_request_completed_and_every_invariant_intact(self):
        for scheduler in ("legacy", "per-qubit"):
            for window_ms in (20, 5):
                audit = audit_trace(self.trace, "dynamic", seed=0, scheduler=scheduler, compiler_reservation_ms=window_ms)
                reasons = collections.Counter(e.reason for e in audit.events
                                              if isinstance(e, Unbooked) and e.kind == "adaptive")
                label = (scheduler, window_ms)
                self.assertGreater(reasons["reservation_expired"], 0, label)
                self.assertEqual(audit.completed, audit.requested, label)
                self.assertEqual(audit.violations, [], label)

    def test_a_long_window_expires_nothing(self):
        audit = audit_trace(self.trace, "dynamic", seed=0, scheduler="per-qubit", compiler_reservation_ms=1000)
        self.assertFalse([e for e in audit.events if isinstance(e, Unbooked) and e.reason == "reservation_expired"])


if __name__ == "__main__":
    unittest.main()
