import unittest
from types import SimpleNamespace
from ace.compiler.compiler_scheduler import CompilerPreGenerationController
from ace.compiler.compiler_trace import CompilerRequest


class PreparationPriorityTests(unittest.TestCase):
    def controller(self, **kwargs):
        self.events, self.calls = [], []
        clock = SimpleNamespace(now=lambda: 10, schedule=self.events.append, remove_event=lambda e: None)
        requests = (CompilerRequest(0, 4, 0, 0, 0, 1),
                    CompilerRequest(1, 4, 1, 0, 1, 2),
                    CompilerRequest(2, 4, 2, 1, 0, 1))
        adaptive = SimpleNamespace(request_compiler_pair=lambda *args: self.calls.append(args))
        return CompilerPreGenerationController(
            timeline=clock, routers={'router_0_0': SimpleNamespace(adaptive_continuous=adaptive)},
            requests=requests, schedule=(), strategy='dynamic', columns=2,
            planner_blocked=0, planner_peak_memory=None, fidelity=.01,
            reservation_duration_ms=50, **kwargs)

    def test_unstarted_predecessor_defers_later_hop_behind_independent_first_hop(self):
        c = self.controller(preparation_priority='dependency')
        self.assertEqual(sorted([1, 2, 0], key=c._preparation_key), [0, 2, 1])
        c.deadlines[0] = 5
        self.assertEqual(sorted([1, 2], key=c._preparation_key), [1, 2])

    def test_release_burst_coalesces_and_does_not_retry_inflight_handshake(self):
        c = self.controller(refill_on_release=True)
        c.pending_preparations[0] = {}
        c.on_resource_release(); c.on_resource_release()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].time, 12)
        c._refill_preparations()
        self.assertEqual(self.calls, [])
        self.assertIsNone(c._refill_event)

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
