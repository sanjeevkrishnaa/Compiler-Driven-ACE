"""Dependency-free regressions for ACE request ordering and timing.

Load the actual manager definitions without importing the physical simulator;
the tests exercise production method bodies with a minimal event/app harness.
"""
import ast
from ace.paths import source_path
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_definitions(filename, names, namespace):
    tree = ast.parse(source_path(filename).read_text(encoding='utf-8'))
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), filename, 'exec'), namespace)
    return namespace


NS = load_definitions('parallel_core.py',
                      {'serialize_core_conflicts', 'ParallelLayerRequestManager'}, {
                          'MILLISECOND': 1,
                          'RESERVATION_START_GRACE_PS': 1,
                          'Process': lambda *args: args,
                          'Event': lambda *args: args,
                      })
serialize = NS['serialize_core_conflicts']
Manager = NS['ParallelLayerRequestManager']


class ExecutionTests(unittest.TestCase):
    def test_dependent_three_hop_chain_stays_ordered(self):
        requests = [(0, 'a', 'b'), (1, 'b', 'c'), (2, 'c', 'd'), (3, 'x', 'y')]
        batches, origins = serialize([requests])
        self.assertEqual([[r[0] for r in batch] for batch in batches], [[0, 3], [1], [2]])
        self.assertEqual(origins, [0, 0, 0])

    def test_every_core_preserves_trace_order(self):
        import random
        rng = random.Random(42)
        for _ in range(100):
            requests = [(i, *rng.sample(range(16), 2)) for i in range(100)]
            batches, _ = serialize([requests])
            for batch in batches:
                endpoints = [core for r in batch for core in r[1:3]]
                self.assertEqual(len(endpoints), len(set(endpoints)))
            for core in range(16):
                expected = [r[0] for r in requests if core in r[1:3]]
                actual = [r[0] for batch in batches for r in batch if core in r[1:3]]
                self.assertEqual(actual, expected)

    def manager(self):
        clock = SimpleNamespace(time=0, now=lambda: clock.time, schedule=lambda event: None)
        app = SimpleNamespace(start=lambda *args: None,
                              set_reservation_approval_callback=lambda *args: None, set_reservation_rejection_callback=lambda *args: None,
                              set_completion_callback=lambda *args: None)
        return Manager(clock, {'a': app}, [[(0, 'a', 'b', 1, .01, 1)]], 5, 50)

    def test_control_plane_guard_is_the_round_trip_channel_delay(self):
        clock = SimpleNamespace(time=0, now=lambda: clock.time, schedule=lambda event: None)
        channel = SimpleNamespace(delay=100)
        app = SimpleNamespace(
            node=SimpleNamespace(cchannels={'b': channel}),
            start=lambda *args: None,
            set_reservation_approval_callback=lambda *args: None,
            set_reservation_rejection_callback=lambda *args: None,
            set_completion_callback=lambda *args: None,
        )
        manager = Manager(clock, {'a': app}, [[(0, 'a', 'b', 1, .01, 1)]], 0, 50)
        self.assertEqual(manager.control_plane_guard, 201)  # 2 x 100 ps + one-picosecond grace
        self.assertEqual(manager._reservation_start_time(500), 701)

    def test_retry_keeps_first_submission_and_counts_failed_attempt(self):
        manager = self.manager()
        with redirect_stdout(StringIO()):
            manager._send_layer()
            manager.timeline.time = 55
            manager.current_layer_index = 0
            manager._send_layer()
        self.assertEqual(manager.request_submission_times[0], 0)
        self.assertEqual(manager.request_attempt_submission_times[0], 55)
        manager.request_approval_times[0] = 57
        manager.request_end_times[0] = 62
        self.assertEqual(manager.get_individual_latencies()[0], 62)
        row = manager.get_individual_latencies_breakdown()[0]
        self.assertEqual(row['retry_wait_time_ms'], 55)
        self.assertEqual(row['reservation_setup_time_ms'], 0)
        self.assertEqual(row['entanglement_generation_time_ms'], 2)
        self.assertEqual(row['initial_buffer_time_ms'], 5)
        self.assertEqual(row['total_time_ms'], 62)

    def test_setup_beyond_buffer_is_counted_once(self):
        manager = self.manager()
        with redirect_stdout(StringIO()):
            manager._send_layer()
        manager.request_approval_times[0] = 7
        manager.request_end_times[0] = 10
        row = manager.get_individual_latencies_breakdown()[0]
        self.assertEqual(row['reservation_setup_time_ms'], 2)
        self.assertEqual(row['entanglement_generation_time_ms'], 3)
        self.assertEqual(row['total_time_ms'], manager.get_individual_latencies()[0])

    def test_makespan_and_timeout_layers_use_elapsed_clock(self):
        manager = self.manager()
        manager.series_start_time, manager.series_end_time = 0, 120
        manager.layer_start_times, manager.layer_end_times = {0: 0, 1: 55}, {0: 55, 1: 120}
        self.assertEqual(manager.get_end_to_end_latency(), 120)
        self.assertEqual(manager.get_layer_latencies(), {0: 55, 1: 65})

    def test_synchronous_rejection_retries_before_service_timeout(self):
        manager = self.manager()
        events, callbacks = [], {}
        manager.timeline.schedule = events.append
        app = manager.name_to_apps['a']
        app.set_reservation_rejection_callback = lambda callback, rid: callbacks.update({rid: callback})
        app.start = lambda *args: callbacks[0](0, manager.timeline.time)
        with redirect_stdout(StringIO()):
            manager._send_layer()
        self.assertTrue(any(event[0] == 1 for event in events))
        self.assertEqual(manager.request_retry_count[0], 0)
        manager.timeline.time = 1
        app.start = lambda *args: None
        with redirect_stdout(StringIO()):
            manager._retry_rejected_request(0, 0)
        self.assertEqual(manager.request_retry_count[0], 1)
        self.assertEqual(manager.request_submission_times[0], 0)
        self.assertEqual(manager.request_attempt_submission_times[0], 1)
        with redirect_stdout(StringIO()):
            manager._retry_rejected_request(0, 0)
        self.assertEqual(manager.request_retry_count[0], 1)

    def test_readiness_is_strictly_before_first_submission(self):
        from collections import defaultdict
        from statistics import fmean
        ns = load_definitions('compiler_scheduler.py', {'_pair_key', 'CompilerPreGenerationController'},
                              {'defaultdict': defaultdict, 'fmean': fmean,
                               'CompilerRequest': object, 'ScheduledPreparation': object,
                               'MILLISECOND': 1})
        cls = ns['CompilerPreGenerationController']
        for generated, expected in [(9, True), (10, False), (12, False)]:
            controller = cls.__new__(cls)
            pair = (('a', 'm'), ('b', 'm'))
            controller.deadlines = {}
            controller.pending_preparations = {}
            controller.preparation_retry_events = {}
            controller.mark_request_start(0, 10)
            controller.mark_request_start(0, 30)
            controller.records = [{'status': 'ready', 'generated_at_ps': generated}]
            controller.active_record_by_pair = {ns['_pair_key'](pair): 0}
            controller.utilization_by_request = {}
            controller.on_pair_utilized(pair, 0, 16, .9, None)
            self.assertEqual(controller.records[0]['prepared_before_request'], expected)


if __name__ == '__main__':
    unittest.main()
