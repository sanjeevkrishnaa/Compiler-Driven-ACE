"""Randomized small traces through the per-qubit manager on the real simulator.

Each trace is a few layers of qubits walking along mesh links.  For every trace and several
memory budgets the run must complete every request, satisfy every invariant of
``invariants.py`` (including that a hop is submitted only after the previous hop of its qubit
completed), and never hold more bookings on a core than the core has memories.  With ample
memory there must be no contention at all.
"""
import collections
import random
import unittest

from execution_events import Booked, Unbooked
from tools.ace_correctness.harness import MESH_COLUMNS, Hop, are_neighbours, run_layers

CORES = MESH_COLUMNS * MESH_COLUMNS


def neighbours(core):
    return [other for other in range(CORES) if are_neighbours(core, other)]


def random_layers(rng, layer_count, max_qubits, max_hops):
    """Layers of hops; each qubit walks without stepping straight back, hops interleaved at random."""
    request_id = 0
    layers = []
    for _ in range(layer_count):
        walks = []
        for qubit in range(rng.randint(0, max_qubits)):
            core = rng.randrange(CORES)
            previous, hops = None, []
            for _ in range(rng.randint(1, max_hops)):
                options = [c for c in neighbours(core) if c != previous] or neighbours(core)
                step = rng.choice(options)
                hops.append((qubit, core, step))
                previous, core = core, step
            walks.append(hops)
        order = [qubit for qubit, hops in enumerate(walks) for _ in hops]
        rng.shuffle(order)
        cursor = [0] * len(walks)
        layer = []
        for qubit in order:
            _, source, destination = walks[qubit][cursor[qubit]]
            cursor[qubit] += 1
            layer.append(Hop(request_id, source, destination, qubit))
            request_id += 1
        layers.append(layer)
    return layers


def peak_bookings(events):
    live, peak = collections.Counter(), collections.Counter()
    for event in events:
        if isinstance(event, Booked):
            live[event.node] += 1
            peak[event.node] = max(peak[event.node], live[event.node])
        elif isinstance(event, Unbooked):
            live[event.node] -= 1
    return peak


class RandomTraceTests(unittest.TestCase):
    TRACES = 16

    def traces(self):
        for seed in range(self.TRACES):
            yield seed, random_layers(random.Random(seed), layer_count=4, max_qubits=6, max_hops=3)

    def test_every_request_completes_and_every_invariant_holds_at_each_memory_budget(self):
        for seed, layers in self.traces():
            for memories in (1, 2, 4):
                outcome = run_layers(layers, memories=memories, seed=seed, scheduler="per-qubit",
                                     submission_after_predecessor=True, stop_time_s=30.0)
                label = (seed, memories)
                self.assertEqual(outcome.completed, outcome.requested, label)
                self.assertEqual(outcome.violations, [], label)
                self.assertEqual(outcome.retry_layers, 0, label)
                self.assertLessEqual(max(peak_bookings(outcome.events).values(), default=0), memories, label)

    def test_ample_memory_means_no_contention(self):
        for seed, layers in self.traces():
            outcome = run_layers(layers, memories=16, seed=seed, scheduler="per-qubit",
                                 submission_after_predecessor=True, stop_time_s=30.0)
            self.assertEqual((outcome.completed, outcome.total_retries, outcome.violations),
                             (outcome.requested, 0, []), seed)

    def test_less_memory_never_finishes_a_trace_faster_in_total(self):
        """Not a law of the protocol, but a large inversion would point at a scheduling fault."""
        slower = 0
        for seed, layers in self.traces():
            makespans = {m: run_layers(layers, memories=m, seed=seed, scheduler="per-qubit",
                                       stop_time_s=30.0).makespan_ms for m in (1, 16)}
            slower += makespans[1] >= makespans[16] - 1e-9
        self.assertEqual(slower, self.TRACES)

    def test_the_generator_makes_chains_the_manager_accepts(self):
        rng = random.Random(99)
        layers = random_layers(rng, layer_count=6, max_qubits=6, max_hops=3)
        self.assertTrue(any(len(layer) > 1 for layer in layers))
        for layer in layers:
            last_end = {}
            for hop in layer:
                if hop.qubit in last_end:
                    self.assertEqual(last_end[hop.qubit], hop.source_core)
                last_end[hop.qubit] = hop.destination_core


if __name__ == "__main__":
    unittest.main()
