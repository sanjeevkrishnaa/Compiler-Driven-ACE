import unittest
from types import SimpleNamespace
from ace.compiler.compiler_scheduler import CompilerPreGenerationController
from ace.compiler.compiler_trace import CompilerRequest
from ace.simulation.request_scheduler import QubitOrderedRequestManager


class PreparationPriorityTests(unittest.TestCase):
    def controller(self, **kwargs):
        self.events, self.calls = [], []
        clock = SimpleNamespace(now=lambda: 10, schedule=self.events.append, remove_event=lambda e: None)
        requests = (CompilerRequest(0, 4, 0, 0, 0, 1),
                    CompilerRequest(1, 4, 1, 1, 0, 1),
                    CompilerRequest(2, 4, 2, 1, 1, 2))
        adaptive = SimpleNamespace(request_compiler_pair=lambda *args: self.calls.append(args))
        return CompilerPreGenerationController(
            timeline=clock, routers={name: SimpleNamespace(adaptive_continuous=adaptive) for name in ('router_0_0', 'router_0_1')},
            requests=requests, schedule=(), strategy='dynamic', columns=2,
            planner_blocked=0, planner_peak_memory=None, fidelity=.01,
            reservation_duration_ms=50, **kwargs)

    def test_launches_shorter_earlier_trace_request_before_longer_chain(self):
        c = self.controller()
        calls = []
        c.by_generation_layer[3] = [2, 1, 0]
        c.launch_preparation = calls.append
        c.on_original_layer(3)
        self.assertEqual(calls, [0, 1, 2])

    def test_refill_preserves_trace_order_despite_pending_insertion_order(self):
        c = self.controller()
        c.pending_preparations = {rid: {} for rid in [2, 1, 0]}
        c.preparation_retry_events = {rid: object() for rid in [2, 1, 0]}
        calls = []
        c.retry_preparation = calls.append
        c._refill_preparations()
        self.assertEqual(calls, [0, 1, 2])

    def test_non_trace_preparation_priority_is_rejected(self):
        for priority in ('dependency', 'chain-length'):
            with self.subTest(priority=priority), self.assertRaisesRegex(ValueError, 'must be trace'):
                self.controller(preparation_priority=priority)

    def test_release_burst_coalesces_and_does_not_retry_inflight_handshake(self):
        c = self.controller(refill_on_release=True)
        c.pending_preparations[0] = {}
        c.on_resource_release(); c.on_resource_release()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].time, 12)
        c._refill_preparations()
        self.assertEqual(self.calls, [])
        self.assertIsNone(c._refill_event)

    def test_application_release_wakes_compiler_without_waiting_for_layer_end(self):
        calls = []
        manager = QubitOrderedRequestManager.__new__(QubitOrderedRequestManager)
        manager.waiting = {}
        manager._admitting = False
        manager.compiler_controller = SimpleNamespace(
            on_resource_release=lambda: calls.append("compiler-refill")
        )
        manager._on_release("router_0_0")
        self.assertEqual(calls, ["compiler-refill"])

    def test_runtime_launch_budget_blocks_second_attempt_until_next_active_layer(self):
        c = self.controller(generation_capacity_per_core=1)
        c.current_generation_layer = 2
        c.pending_preparations[2] = {}
        c.on_preparation_launched(0)
        c.retry_preparation(2)
        self.assertEqual(self.calls, [])
        self.assertEqual(c.rejections[2], ['generation_budget'])
        c.current_generation_layer = 3
        c.retry_preparation(2)
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
