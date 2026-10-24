"""Admission: polling livelocks on a swap, event-driven admission does not.

Core numbering is row major on the 4x4 mesh.  "One memory per core" is the setting where two
requests that need each other's only memory cannot both start, which is where the two
admission modes differ.
"""
import unittest

from execution_events import RequestCompleted, RequestSubmitted
from tools.ace_correctness.harness import Hop, run_layers

SWAP = [[Hop(0, 8, 12, qubit=0), Hop(1, 12, 8, qubit=1)]]          # two qubits exchange cores 8 and 12


def completions(outcome):
    return {e.request_id: e.time_ps for e in outcome.events if isinstance(e, RequestCompleted)}


def submissions(outcome):
    counts = {}
    for event in outcome.events:
        if isinstance(event, RequestSubmitted):
            counts[event.request_id] = counts.get(event.request_id, 0) + 1
    return counts


def run(layers, admission, **kwargs):
    return run_layers(layers, scheduler="per-qubit", submission_after_predecessor=True,
                      scheduler_options={"admission": admission, **kwargs.pop("options", {})}, **kwargs)


class SwapTests(unittest.TestCase):
    def test_polling_admission_livelocks_when_two_requests_need_each_others_only_memory(self):
        """Characterization of the reason event admission exists: both retry on the same 1 ms period for ever."""
        outcome = run(SWAP, "poll", memories=1, stop_time_s=3.0)
        self.assertEqual(outcome.completed, 0)
        counts = submissions(outcome)
        self.assertGreater(min(counts.values()), 1000)           # about 2,500 each in 3 s

    def test_event_admission_serializes_the_two_requests_oldest_first(self):
        outcome = run(SWAP, "event", memories=1, stop_time_s=3.0)
        self.assertEqual((outcome.completed, outcome.violations), (2, []))
        done = completions(outcome)
        self.assertLess(done[0], done[1])
        self.assertEqual(submissions(outcome), {0: 1, 1: 1})       # admitted once each, never rejected
        self.assertEqual(outcome.total_retries, 0)

    def test_with_two_memories_both_modes_run_the_swap_together(self):
        for admission in ("poll", "event"):
            outcome = run(SWAP, admission, memories=2)
            self.assertEqual((outcome.completed, outcome.total_retries, outcome.violations), (2, 0, []), admission)
            self.assertLess(max(outcome.latencies_ms.values()), 5.0)


class OrderTests(unittest.TestCase):
    """One memory per core.  A (5-6) runs; B (5-9) must wait for core 5; C (9-10) only needs free cores."""
    LAYER = [[Hop(0, 5, 6, qubit=0), Hop(1, 5, 9, qubit=1), Hop(2, 9, 10, qubit=2)]]

    def test_the_guard_keeps_core_9_for_the_older_request(self):
        outcome = run(self.LAYER, "event", memories=1)
        self.assertEqual((outcome.completed, outcome.violations), (3, []))
        done = completions(outcome)
        self.assertLess(done[0], done[1])
        self.assertLess(done[1], done[2])                          # B before C: C may not take what B needs

    def test_without_the_guard_the_younger_request_goes_ahead(self):
        outcome = run(self.LAYER, "event", memories=1, options={"starvation_guard": False})
        self.assertEqual((outcome.completed, outcome.violations), (3, []))
        done = completions(outcome)
        self.assertLess(done[2], done[1])                          # C used the idle core 9 first

    def test_the_younger_request_is_not_delayed_by_a_request_it_does_not_share_a_core_with(self):
        outcome = run([[Hop(0, 5, 6, qubit=0), Hop(1, 9, 10, qubit=1)]], "event", memories=1)
        self.assertEqual(submissions(outcome), {0: 1, 1: 1})
        first = {e.request_id: e.time_ps for e in outcome.events if isinstance(e, RequestSubmitted)}
        self.assertEqual((first[0], first[1]), (0, 0))


class WaitingTests(unittest.TestCase):
    def test_waiting_for_a_memory_counts_in_the_requests_latency(self):
        outcome = run(SWAP, "event", memories=1)
        slow, fast = outcome.latencies_ms[1], outcome.latencies_ms[0]
        self.assertGreater(slow, 1.5 * fast)                        # it waited for the first to finish

    def test_a_chain_through_a_one_memory_relay_is_not_rejected_by_the_release_lag(self):
        outcome = run([[Hop(0, 5, 9, qubit=0), Hop(1, 9, 10, qubit=0)]], "event", memories=1)
        self.assertEqual((outcome.completed, outcome.total_retries, outcome.violations), (2, 0, []))

    def test_an_unknown_admission_mode_is_refused(self):
        with self.assertRaises(ValueError):
            run([[Hop(0, 5, 9)]], "sometimes", memories=2)


if __name__ == "__main__":
    unittest.main()
