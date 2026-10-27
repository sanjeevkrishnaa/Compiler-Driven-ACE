"""Runtime queue candidates must retain all hop positions and obey physical ownership."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest

from compiler_trace import CompilerRequest, CompilerTrace, parse_compiler_trace, plan_preparations, to_ace_layers
from execution_events import ListRecorder
from invariants import RequestInfo, check_events
from parallel_core import run_parallel_experiment
from compiler_scheduler import CompilerPreGenerationController

ROOT = Path(__file__).resolve().parents[1]


class RuntimeQueueTests(unittest.TestCase):
    def test_borrowing_requires_an_earlier_request_on_the_same_edge_and_an_unstarted_target(self):
        requests = (CompilerRequest(0, 1, 0, 0, 0, 1), CompilerRequest(1, 2, 0, 1, 1, 0),
                    CompilerRequest(2, 1, 1, 2, 0, 2))
        controller = CompilerPreGenerationController(
            timeline=None, routers={}, requests=requests, schedule=(), strategy="dynamic",
            columns=2, planner_blocked=0, planner_peak_memory=0, fidelity=.01,
            reservation_duration_ms=1000, borrow_compiler_pairs=True)
        self.assertTrue(controller.can_borrow_pair(1, 0))
        self.assertFalse(controller.can_borrow_pair(0, 1))
        self.assertFalse(controller.can_borrow_pair(1, 2))
        controller.deadlines[1] = 10
        self.assertFalse(controller.can_borrow_pair(1, 0))

    def test_competing_full_chains_are_candidates_without_an_offline_capacity_promise(self):
        requests = tuple(CompilerRequest(i, 1, i, i // 2, a, b)
                         for i, (a, b) in enumerate(((0, 1), (1, 3), (2, 3), (3, 1))))
        trace = CompilerTrace(4, 8, 2, {0: 0, 1: 2}, requests, 2)
        candidates, blocked, peak = plan_preparations(
            trace, strategy="dynamic", compiler_memories_per_core=1,
            generation_capacity_per_core=1, coherence_time_layers=10, planning_mode="runtime")
        self.assertEqual([item.request_id for item in candidates], [0, 1, 2, 3])
        self.assertEqual(blocked, 0)
        self.assertIsNone(peak)

    def test_refilled_full_chain_runs_preserve_all_physical_invariants(self):
        trace = parse_compiler_trace(ROOT / "data/tracegen/random16_d80_seed303.txt")
        for demand_first, borrow in ((False, False), (True, False), (False, True)):
            with self.subTest(demand_first=demand_first, borrow=borrow):
                schedule, blocked, peak = plan_preparations(
                    trace, strategy="dynamic", compiler_memories_per_core=2,
                    generation_capacity_per_core=2, coherence_time_layers=10,
                    planning_mode="runtime")
                recorder = ListRecorder()
                spec = dict(requests=trace.requests, schedule=schedule, strategy="dynamic", columns=4,
                            planner_blocked=blocked, planner_peak_memory=peak, compiler_memories_per_core=2,
                            fidelity=.01, reservation_duration_ms=1000, refill_on_release=True,
                            demand_first=demand_first, borrow_compiler_pairs=borrow)
                with redirect_stdout(StringIO()):
                    result = run_parallel_experiment(
                        str(ROOT / "config/final_config/grid_4x4_ace_3.json"), False, False,
                        to_ace_layers(trace, columns=4), 0, 50, "runtime-queue-test",
                        compiler_spec=spec, total_memories_per_core=4, scheduler="per-qubit",
                        request_plan=trace.requests, scheduler_options={"admission": "event"},
                        simulation_stop_time_s=5, stop_after_workload=True, recorder=recorder)
                self.assertEqual(result["stats"]["completed_requests"], len(trace.requests))
                info = {r.request_id: RequestInfo(r.request_id, r.layer, r.qubit, r.order)
                        for r in trace.requests}
                self.assertEqual(check_events(recorder.events, info, require_completion=True,
                                              submission_after_predecessor=True), [])
                for record in result["compiler_metrics"]["epr_utilization_trace"]:
                    if record["status"] == "used" and not borrow:
                        self.assertEqual(record["actual_request_id"], record["target_request_id"])

    def test_consuming_a_borrowed_pair_replenishes_the_displaced_future_target(self):
        from compiler_trace import ScheduledPreparation
        calls = []
        requests = (CompilerRequest(0, 1, 0, 0, 0, 1), CompilerRequest(1, 2, 0, 1, 0, 1))
        adaptive = SimpleNamespace(request_compiler_pair=lambda *args: calls.append(args))
        clock = SimpleNamespace(now=lambda: 2, remove_event=lambda event: None)
        controller = CompilerPreGenerationController(
            timeline=clock, routers={"router_0_0": SimpleNamespace(adaptive_continuous=adaptive)},
            requests=requests, schedule=(ScheduledPreparation(1, 0),), strategy="dynamic",
            columns=2, planner_blocked=0, planner_peak_memory=1, fidelity=.01,
            reservation_duration_ms=1000, borrow_compiler_pairs=True)
        pair = (("router_0_0", "m0"), ("router_0_1", "m0"))
        metadata = dict(target_request_id=1, strategy="dynamic", generation_layer=0, target_layer=2)
        controller.on_pair_generated(pair, 0, .95, metadata)
        controller.accepted.add(1)
        controller.deadlines[0] = 1
        controller.on_pair_utilized(pair, 0, 2, .95, metadata)
        self.assertEqual(len(calls), 1)
        self.assertIn(1, controller.pending_preparations)
        self.assertNotIn(1, controller.accepted)
        self.assertEqual(controller.records[0]["actual_request_id"], 0)
        self.assertEqual(controller.records[0]["status"], "used")


if __name__ == "__main__":
    unittest.main()
