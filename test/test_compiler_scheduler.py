"""The per-qubit request manager, on the real ACE simulator with the invariant monitor attached.

Core numbering is row major on the 4x4 mesh: core 9 is router_2_1 and its neighbours are 5, 8, 10, 13.
Speculative generation is off, so the requests given are the only demand.
"""
import unittest

from ace.compiler.compiler_trace import CompilerRequest
from ace.observability.execution_events import RequestCompleted, RequestSubmitted, canonical
from ace.simulation.request_scheduler import QubitOrderedRequestManager, TraceError
from tools.ace_correctness.harness import Hop, run_layers

MS = 1e9            # picoseconds per millisecond


def first_submissions(outcome):
    first = {}
    for event in outcome.events:
        if isinstance(event, RequestSubmitted) and event.request_id not in first:
            first[event.request_id] = event.time_ps
    return first


def completions(outcome):
    return {e.request_id: e.time_ps for e in outcome.events if isinstance(e, RequestCompleted)}


def run(layers, **kwargs):
    kwargs.setdefault("memories", 4)
    return run_layers(layers, scheduler="per-qubit", submission_after_predecessor=True, **kwargs)


class ChainTests(unittest.TestCase):
    CHAIN = [[Hop(0, 5, 9, qubit=0), Hop(1, 9, 10, qubit=0)]]            # one qubit moves 5 -> 9 -> 10

    def test_the_next_hop_is_released_when_the_previous_one_completes(self):
        outcome = run(self.CHAIN)
        self.assertEqual((outcome.completed, outcome.total_retries, outcome.violations), (2, 0, []))
        submitted, done = first_submissions(outcome), completions(outcome)
        self.assertEqual(submitted[0], 0)
        self.assertEqual(submitted[1], done[0])
        self.assertLess(done[0], done[1])

    def test_a_chain_through_a_one_memory_relay_completes_without_rejection(self):
        outcome = run(self.CHAIN, memories=1)
        self.assertEqual((outcome.completed, outcome.total_retries, outcome.violations), (2, 0, []))

    def test_different_qubits_are_released_together_and_overlap(self):
        outcome = run([[Hop(0, 5, 9, qubit=0), Hop(1, 13, 9, qubit=1)]])
        self.assertEqual((outcome.completed, outcome.total_retries, outcome.violations), (2, 0, []))
        submitted = first_submissions(outcome)
        self.assertEqual((submitted[0], submitted[1]), (0, 0))
        self.assertLess(max(outcome.latencies_ms.values()), 10.0)

    def test_a_longer_chain_keeps_trace_order(self):
        outcome = run([[Hop(0, 4, 5, qubit=3), Hop(1, 5, 9, qubit=3), Hop(2, 9, 10, qubit=3)]])
        self.assertEqual((outcome.completed, outcome.violations), (3, []))
        done = completions(outcome)
        self.assertLess(done[0], done[1])
        self.assertLess(done[1], done[2])


class LayerTests(unittest.TestCase):
    def test_a_layer_starts_when_every_request_of_the_previous_one_has_completed(self):
        outcome = run([[Hop(0, 5, 9, qubit=0), Hop(1, 13, 9, qubit=1)], [Hop(2, 9, 10, qubit=0)]])
        self.assertEqual((outcome.completed, outcome.violations), (3, []))
        done = completions(outcome)
        self.assertEqual(first_submissions(outcome)[2], max(done[0], done[1]))

    def test_an_empty_layer_costs_the_five_millisecond_gap_of_the_legacy_manager(self):
        outcome = run([[Hop(0, 5, 9)], [], [Hop(1, 5, 9)]])
        self.assertEqual((outcome.completed, outcome.violations), (2, []))
        self.assertEqual(first_submissions(outcome)[1] - completions(outcome)[0], 5 * MS)

    def test_the_makespan_covers_every_layer(self):
        outcome = run([[Hop(0, 5, 9)], [Hop(1, 9, 10)]])
        self.assertAlmostEqual(outcome.makespan_ms, completions(outcome)[1] / MS, places=6)


class TimeoutTests(unittest.TestCase):
    """A request window shorter than the usual generation time forces timeouts and resubmission."""
    LAYER = [[Hop(0, 5, 9, qubit=0), Hop(1, 13, 9, qubit=1), Hop(2, 9, 10, qubit=2)]]

    def test_timed_out_requests_are_resubmitted_alone_and_leave_no_stale_booking(self):
        for seed in range(6):
            outcome = run(self.LAYER, request_duration_ms=0.6, stop_time_s=5.0, seed=seed)
            self.assertEqual(outcome.completed, 3, seed)
            self.assertEqual(outcome.violations, [], seed)
            self.assertEqual(outcome.retry_layers, 0, seed)

    def test_a_timeout_actually_happens_in_those_runs(self):
        outcome = run(self.LAYER, request_duration_ms=0.6, stop_time_s=5.0, seed=0)
        self.assertGreater(outcome.total_retries, 0)

    def test_the_same_seed_reproduces_the_event_log_exactly(self):
        first = run(self.LAYER, request_duration_ms=0.6, stop_time_s=5.0, seed=1)
        second = run(self.LAYER, request_duration_ms=0.6, stop_time_s=5.0, seed=1)
        self.assertEqual(canonical(first.events), canonical(second.events))


class ValidationTests(unittest.TestCase):
    def plan(self, *hops):
        return [CompilerRequest(*fields) for fields in hops]

    def layers_for(self, requests):
        grouped = {}
        for r in requests:
            grouped.setdefault(r.layer, []).append((r.request_id, "a", "b", 1, 0.01, 1))
        return [grouped.get(layer, []) for layer in range(max(grouped) + 1)]

    def test_a_chain_whose_hops_do_not_connect_is_refused(self):
        requests = self.plan((0, 0, 0, 7, 5, 9), (1, 0, 1, 7, 8, 12))      # qubit 7 arrives at 9, then leaves from 8
        with self.assertRaises(TraceError):
            QubitOrderedRequestManager._plan_chains(requests, self.layers_for(requests))

    def test_requests_missing_from_the_layers_are_refused(self):
        requests = self.plan((0, 0, 0, 7, 5, 9), (1, 0, 1, 8, 9, 10))
        with self.assertRaises(TraceError):
            QubitOrderedRequestManager._plan_chains(requests, self.layers_for(requests[:1]))

    def test_a_request_in_the_wrong_layer_is_refused(self):
        requests = self.plan((0, 0, 0, 7, 5, 9), (1, 1, 0, 8, 9, 10))
        layers = self.layers_for(requests)
        layers[0], layers[1] = layers[1], layers[0]
        with self.assertRaises(TraceError):
            QubitOrderedRequestManager._plan_chains(requests, layers)

    def test_the_chains_are_found_per_layer_and_qubit(self):
        requests = self.plan((0, 0, 0, 7, 5, 9), (1, 0, 1, 7, 9, 10), (2, 0, 2, 8, 13, 9), (3, 1, 0, 7, 10, 11))
        layer_of, predecessor, successor = QubitOrderedRequestManager._plan_chains(requests, self.layers_for(requests))
        self.assertEqual(layer_of, {0: 0, 1: 0, 2: 0, 3: 1})
        self.assertEqual(predecessor, {0: None, 1: 0, 2: None, 3: None})
        self.assertEqual(successor, {0: 1, 1: None, 2: None, 3: None})

    def test_an_unknown_scheduler_is_refused(self):
        with self.assertRaises(ValueError):
            run_layers([[Hop(0, 5, 9)]], memories=2, scheduler="nonsense")

    def test_the_per_qubit_scheduler_needs_the_trace(self):
        from ace.simulation.parallel_core import run_parallel_experiment
        with self.assertRaises(ValueError):
            run_parallel_experiment("unused.json", False, False, [], 5.3, 50, "x", scheduler="per-qubit")


if __name__ == "__main__":
    unittest.main()
