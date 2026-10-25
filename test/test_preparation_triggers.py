"""The launch rules of CompilerPreGenerationController: when a planned preparation is requested."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from compiler_scheduler import CompilerPreGenerationController
from compiler_trace import CompilerRequest, ScheduledPreparation


class Timeline:
    def __init__(self):
        self.events, self.time = [], 0

    def now(self):
        return self.time

    def schedule(self, event):
        self.events.append(event)

    def remove_event(self, event):
        self.events.remove(event)


def build(trigger="layer-start", delay_ms=0.0, hops=None):
    # layer 1: qubit 7 moves 0->1->2 (requests 10, 11); qubit 8 moves 3->4 (request 12); all planned for layer 0
    requests = (CompilerRequest(10, 1, 0, 7, 0, 1), CompilerRequest(11, 1, 1, 7, 1, 2), CompilerRequest(12, 1, 0, 8, 3, 4))
    schedule = tuple(ScheduledPreparation(r.request_id, 0) for r in requests)
    asked = []
    routers = {f"router_0_{c}": SimpleNamespace(adaptive_continuous=SimpleNamespace(
        request_compiler_pair=lambda destination, meta, c=c: asked.append(meta["request_id"]))) for c in range(5)}
    timeline = Timeline()
    controller = CompilerPreGenerationController(
        timeline=timeline, routers=routers, requests=requests, schedule=schedule, strategy="dynamic", columns=5,
        planner_blocked=0, planner_peak_memory=0, fidelity=0.01, reservation_duration_ms=1000.0,
        trigger=trigger, trigger_delay_ms=delay_ms, chain_hops_prepared=hops)
    return controller, asked, timeline


class TriggerTests(unittest.TestCase):
    def test_default_launches_every_preparation_when_its_layer_activates(self):
        controller, asked, _ = build()
        controller.on_original_layer(0)
        self.assertEqual(sorted(asked), [10, 11, 12])

    def test_predecessor_start_holds_back_later_hops_until_the_hop_before_begins(self):
        controller, asked, _ = build("predecessor-start")
        controller.on_original_layer(0)
        self.assertEqual(sorted(asked), [10, 12])                     # first hops only
        controller.mark_request_start(10, 5)                          # hop 10 of qubit 7 begins
        self.assertEqual(sorted(asked), [10, 11, 12])

    def test_a_later_hop_that_already_started_is_not_prepared(self):
        controller, asked, _ = build("predecessor-start")
        controller.on_original_layer(0)
        controller.mark_request_start(11, 4)                          # the request itself started first
        controller.mark_request_start(10, 5)
        self.assertEqual(sorted(asked), [10, 12])

    def test_delay_schedules_the_launch_instead_of_making_it(self):
        controller, asked, timeline = build(delay_ms=2.0)
        controller.on_original_layer(0)
        self.assertEqual(asked, [])
        self.assertEqual(len(timeline.events), 3)
        self.assertTrue(all(e.time == 2 * 10**9 for e in timeline.events))

    def test_chain_hops_prepared_drops_the_later_hops_from_the_schedule(self):
        controller, asked, _ = build(hops=1)
        controller.on_original_layer(0)
        self.assertEqual(sorted(asked), [10, 12])
        self.assertEqual(set(controller.schedule), {10, 12})

    def test_unknown_trigger_is_rejected(self):
        with self.assertRaises(ValueError):
            build("whenever")


if __name__ == "__main__":
    unittest.main()
