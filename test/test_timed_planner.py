"""The wall-clock-aware planner: clock, readiness model, launch times, capacity, and the controller's offset."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ace.compiler.compiler_scheduler import CompilerPreGenerationController
from ace.compiler.compiler_trace import CompilerRequest, CompilerTrace, ScheduledPreparation
from ace.compiler.timed_planner import (LayerClock, PreparationModel, plan_timed_preparations,
                                        success_probability_from_config)


def trace(rows, layers):
    """rows: (layer, source, destination)."""
    requests = tuple(CompilerRequest(i, layer, i, i, s, d) for i, (layer, s, d) in enumerate(rows))
    return CompilerTrace(16, 12, len(rows), {}, requests, layers)


MODEL = PreparationModel(delay_ms=0.1, success_probability=0.5, quantile=0.9)      # 4 attempts cover 90 % at p = 0.5 (94 %)


class ModelTests(unittest.TestCase):
    def test_attempts_are_the_smallest_count_reaching_the_quantile(self):
        self.assertEqual(MODEL.attempts(), 4)                                   # 1 - 0.5**3 = 0.875 < 0.9 <= 0.9375
        self.assertEqual(PreparationModel(0.1, 1.0).attempts(), 1)

    def test_lead_is_window_plus_attempts_and_reverse_hops_cost_more(self):
        self.assertAlmostEqual(MODEL.lead_ms(0, 1), 0.2 + 4 * 0.1 * 4)           # 2 delta + 4 attempts x 4 delta
        self.assertAlmostEqual(MODEL.lead_ms(1, 0), 0.2 + 5 * 0.1 * 4)
        self.assertAlmostEqual(PreparationModel(0.1, 0.5, 0.9, margin_ms=0.3).lead_ms(0, 1), 1.8 + 0.3)

    def test_the_success_probability_of_the_configuration(self):
        config = {"templates": {"adaptive_protocol": {"MemoryArray": {"efficiency": 0.8},
                  "SingleHeraldedBSM": {"detectors": [{"efficiency": 0.95}, {"efficiency": 0.95}]}}}, "qchannels": []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "c.json"
            path.write_text(json.dumps(config))
            self.assertAlmostEqual(success_probability_from_config(path), 0.5 * 0.8 ** 2 * 0.95 ** 2)

    def test_invalid_models_are_rejected(self):
        for args in ((0, 0.5), (0.1, 0), (0.1, 0.5, 1.0), (0.1, 0.5, 0.9, -1)):
            with self.assertRaises(ValueError):
                PreparationModel(*args)


class ClockTests(unittest.TestCase):
    def test_layer_at_returns_the_open_layer(self):
        clock = LayerClock([0.0, 5.0, 10.0])
        self.assertEqual([clock.layer_at(t) for t in (0.0, 4.9, 5.0, 12.0)], [0, 0, 1, 2])

    def test_analytic_clock_uses_the_longest_chain_and_the_gap(self):
        t = trace([(1, 0, 1), (1, 1, 2)], layers=3)                              # two hops of different qubits in layer 1
        clock = LayerClock.analytic(t, hop_ms=0.6, empty_gap_ms=5.0)
        self.assertEqual(clock.starts_ms, [0.0, 5.0, 5.6])

    def test_profile_round_trip_and_decreasing_times_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "p.json"
            path.write_text(json.dumps([0, 1.5, 3]))
            self.assertEqual(LayerClock.from_profile(path).starts_ms, [0.0, 1.5, 3.0])
        with self.assertRaises(ValueError):
            LayerClock([0.0, 2.0, 1.0])


class PlannerTests(unittest.TestCase):
    def plan(self, rows, starts, memories=4, capacity=4, **kw):
        t = trace(rows, len(starts))
        return plan_timed_preparations(t, LayerClock(starts), MODEL, compiler_memories_per_core=memories,
                                       generation_capacity_per_core=capacity, **kw)

    def test_launch_is_one_lead_before_the_request_and_can_fall_inside_a_layer(self):
        schedule, blocked, peak = self.plan([(2, 0, 1)], [0.0, 3.0, 20.0])         # needed at 20.0, lead 1.8
        self.assertEqual(blocked, 0)
        item = schedule[0]
        self.assertEqual(item.generation_layer, 1)                                  # layer 1 is open from 3.0 to 20.0
        self.assertAlmostEqual(item.offset_ms, 20.0 - 1.8 - 3.0)                    # 15.2 ms into the layer
        self.assertEqual(peak, 1)

    def test_a_request_needing_a_launch_before_time_zero_is_blocked(self):
        schedule, blocked, _ = self.plan([(1, 0, 1)], [0.0, 1.0])                   # needed at 1.0, lead 1.8
        self.assertEqual((schedule, blocked), ((), 1))

    def test_zero_compiler_memories_blocks_everything(self):
        self.assertEqual(self.plan([(1, 0, 1)], [0.0, 30.0], memories=0)[:2], ((), 1))

    def test_a_full_core_pushes_the_launch_earlier_or_blocks_it(self):
        rows = [(1, 0, 1), (1, 0, 2)]                                               # both use core 0
        starts = [0.0, 30.0]
        one, blocked, _ = self.plan(rows, starts, memories=1, max_lookback_ms=0.0)
        self.assertEqual((len(one), blocked), (1, 1))                               # the second finds core 0 full
        two, blocked, peak = self.plan(rows, starts, memories=2)
        self.assertEqual((len(two), blocked, peak), (2, 0, 2))

    def test_generation_capacity_limits_launches_in_flight(self):
        rows = [(1, 0, 1), (1, 0, 2)]
        starts = [0.0, 30.0]
        schedule, blocked, _ = self.plan(rows, starts, memories=4, capacity=1, max_lookback_ms=0.0)
        self.assertEqual((len(schedule), blocked), (1, 1))
        schedule, blocked, _ = self.plan(rows, starts, memories=4, capacity=1)      # earlier launches avoid the overlap
        self.assertEqual((len(schedule), blocked), (2, 0))
        launches = sorted(item.offset_ms for item in schedule)                     # both launch in layer 0
        self.assertGreaterEqual(launches[1] - launches[0], 1.8 - 1e-9)             # the second waits for the first to be ready

    def test_the_clock_must_cover_every_layer(self):
        with self.assertRaises(ValueError):
            plan_timed_preparations(trace([(3, 0, 1)], 4), LayerClock([0.0, 1.0]), MODEL,
                                    compiler_memories_per_core=4, generation_capacity_per_core=4)


class Timeline:
    def __init__(self):
        self.events, self.time = [], 1_000

    def now(self):
        return self.time

    def schedule(self, event):
        self.events.append(event)

    def remove_event(self, event):
        self.events.remove(event)


class ControllerOffsetTests(unittest.TestCase):
    def build(self, offset_ms):
        requests = (CompilerRequest(5, 3, 0, 1, 0, 1),)
        asked = []
        routers = {f"router_0_{c}": SimpleNamespace(adaptive_continuous=SimpleNamespace(
            request_compiler_pair=lambda destination, meta: asked.append(meta["request_id"]))) for c in range(2)}
        timeline = Timeline()
        controller = CompilerPreGenerationController(
            timeline=timeline, routers=routers, requests=requests, schedule=(ScheduledPreparation(5, 1, offset_ms),),
            strategy="dynamic", columns=2, planner_blocked=0, planner_peak_memory=0, fidelity=0.01, reservation_duration_ms=50.0)
        return controller, asked, timeline

    def test_zero_offset_launches_when_the_layer_opens(self):
        controller, asked, timeline = self.build(0.0)
        controller.on_original_layer(1)
        self.assertEqual((asked, timeline.events), ([5], []))

    def test_an_offset_schedules_the_launch_that_much_later(self):
        controller, asked, timeline = self.build(2.5)
        controller.on_original_layer(1)
        self.assertEqual(asked, [])
        self.assertEqual(len(timeline.events), 1)
        self.assertEqual(timeline.events[0].time, 1_000 + 2_500_000_000)             # 2.5 ms in picoseconds

    def test_the_default_schedule_item_has_no_offset(self):
        self.assertEqual(ScheduledPreparation(1, 2).offset_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
