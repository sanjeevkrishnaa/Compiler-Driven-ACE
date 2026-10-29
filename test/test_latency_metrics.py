"""The common latency definition, on hand-made managers and on the real simulator."""
import contextlib
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from ace.compiler.compiler_trace import CompilerRequest, router_name
from ace.observability.latency_metrics import arrival_latencies_ms, layer_activation_times
from ace.simulation.parallel_core import run_parallel_experiment
from tools.ace_correctness import harness
from tools.ace_correctness.harness import Hop

MS = 10**9


def manager(starts, origins, ends, pregeneration_ms=5.3):
    return SimpleNamespace(layer_start_times=starts, working_layer_origins=origins, request_end_times=ends,
                           pregeneration_time=int(pregeneration_ms * MS))


def simulate(layers, scheduler, memories=2):
    plan = [CompilerRequest(h.request_id, li, o, h.qubit, h.source_core, h.destination_core)
            for li, layer in enumerate(layers) for o, h in enumerate(layer)]
    tuples = [[(h.request_id, router_name(h.source_core, 4), router_name(h.destination_core, 4), 1, 0.01, 1)
               for h in layer] for layer in layers]
    with tempfile.TemporaryDirectory() as tmp:
        config = harness._config_without_speculation(Path(tmp))
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_parallel_experiment(str(config), False, False, tuples, 5.3, 50, "t", seed=0,
                                             total_memories_per_core=memories, simulation_stop_time_s=10.0,
                                             serialize_conflicts=(scheduler == "legacy"),
                                             scheduler=scheduler, request_plan=plan)
    return result, plan


class DefinitionTests(unittest.TestCase):
    def test_a_layer_split_into_batches_starts_at_its_first_batch(self):
        self.assertEqual(layer_activation_times({0: 10, 1: 30, 2: 50}, [0, 0, 1]), {0: 10, 1: 50})

    def test_retry_batches_do_not_define_a_layer_start(self):
        self.assertEqual(layer_activation_times({0: 10, 1: 30}, [0, None]), {0: 10})

    def test_a_request_is_measured_from_arrival_without_subtracting_the_buffer(self):
        requests = [CompilerRequest(0, 0, 0, 7, 5, 9), CompilerRequest(1, 0, 1, 7, 9, 10),
                    CompilerRequest(2, 0, 2, 8, 1, 2)]
        got = arrival_latencies_ms(manager({0: 0}, [0], {0: 6 * MS, 1: 14 * MS, 2: 9 * MS}), requests)
        self.assertAlmostEqual(got[0], 6)                 # from the layer start
        self.assertAlmostEqual(got[1], 14 - 6)            # from the moment hop 0 completed
        self.assertAlmostEqual(got[2], 9)                 # another qubit: from the layer start too

    def test_unfinished_requests_are_left_out(self):
        requests = [CompilerRequest(0, 0, 0, 7, 5, 9), CompilerRequest(1, 0, 1, 8, 1, 2)]
        got = arrival_latencies_ms(manager({0: 0}, [0], {0: 6 * MS}), requests)
        self.assertEqual(set(got), {0})


class OnTheSimulatorTests(unittest.TestCase):
    LAYERS = [[Hop(0, 5, 9, 0), Hop(1, 9, 10, 0), Hop(2, 13, 9, 1)], [Hop(3, 9, 10, 0)]]

    def test_per_qubit_latencies_equal_the_common_definition(self):
        """That manager already starts a request's clock at eligibility, so the two must agree."""
        result, plan = simulate(self.LAYERS, "per-qubit")
        own = result["stats"]["individual_latencies"]
        common = arrival_latencies_ms(result["request_manager"], plan)
        self.assertEqual(set(own), set(common))
        for request_id in own:
            self.assertAlmostEqual(own[request_id], common[request_id], places=6)

    def test_legacy_latency_leaves_out_waiting_for_earlier_batches_and_the_common_one_counts_it(self):
        result, plan = simulate(self.LAYERS, "legacy")
        own = result["stats"]["individual_latencies"]
        common = arrival_latencies_ms(result["request_manager"], plan)
        self.assertEqual(set(own), set(common))
        for request_id in own:
            self.assertGreaterEqual(common[request_id] + 1e-9, own[request_id])
        self.assertTrue(any(common[r] > own[r] + 0.5 for r in own), "some request waited for an earlier batch")


if __name__ == "__main__":
    unittest.main()


class AdmissionWaitColumnTests(unittest.TestCase):
    def test_admission_waits_are_reported_for_the_per_qubit_scheduler_and_absent_for_legacy(self):
        import ace.cli.run_trace_comparison as runner
        layers = [[Hop(0, 5, 6, 0), Hop(1, 5, 9, 1), Hop(2, 9, 10, 2)]]
        per_qubit, _ = simulate(layers, "per-qubit", memories=1)
        legacy, _ = simulate(layers, "legacy", memories=1)
        got = runner._admission_waits(per_qubit["stats"])
        self.assertGreater(got["max_admission_wait_ms"], 0)
        self.assertEqual(got["requests_that_waited_fraction"], 2 / 3)       # two of three requests had to wait
        self.assertIsNone(runner._admission_waits(legacy["stats"])["average_admission_wait_ms"])

    def test_a_one_picosecond_grace_is_not_a_wait(self):
        import ace.cli.run_trace_comparison as runner
        stats = {"timing_breakdown": {0: {"admission_wait_time_ms": 0.0}, 1: {"admission_wait_time_ms": 1e-9},
                                      2: {"admission_wait_time_ms": 0.5}, 3: {"admission_wait_time_ms": 2.0}}}
        got = runner._admission_waits(stats)
        self.assertEqual(got["requests_that_waited_fraction"], 0.5)          # only the 0.5 ms and 2 ms waits count
        self.assertEqual(got["max_admission_wait_ms"], 2.0)
