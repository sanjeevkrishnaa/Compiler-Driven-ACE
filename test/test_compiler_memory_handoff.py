"""A cached pair can change ownership without allocating another communication slot."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ace.compiler.compiler_trace import CompilerRequest, CompilerTrace, plan_preparations, to_ace_layers
from ace.observability.execution_events import ADAPTIVE, APPLICATION, Booked, ListRecorder, Unbooked
from ace.observability.invariants import RequestInfo, check_events
from ace.simulation.parallel_core import run_parallel_experiment
from ace.resources.reservation import ApplicationReservation, ReservationAdaptive, ResourceReservationProtocolAdaptive
from ace.simulation.request_scheduler import QubitOrderedRequestManager

ROOT = Path(__file__).resolve().parents[1]


class HandoffTests(unittest.TestCase):
    def run_full_pool(self, memories, reuse):
        requests = (CompilerRequest(0, 1, 0, 0, 5, 9),)
        if memories == 2:
            requests += (CompilerRequest(1, 1, 1, 1, 9, 10),)
        trace = CompilerTrace(16, 8, len(requests), {0: 5, 1: 9}, requests, 2)
        schedule, blocked, peak = plan_preparations(
            trace, strategy="dynamic", compiler_memories_per_core=memories,
            generation_capacity_per_core=memories, coherence_time_layers=10)
        spec = dict(requests=requests, schedule=schedule, strategy="dynamic", columns=4,
                    planner_blocked=blocked, planner_peak_memory=peak,
                    compiler_memories_per_core=memories, fidelity=.01,
                    reservation_duration_ms=1000)
        if reuse is not None:
            spec['reuse_compiler_memory'] = reuse
        recorder = ListRecorder()
        with redirect_stdout(StringIO()):
            result = run_parallel_experiment(
                str(ROOT/'config/final_config/grid_4x4_ace_3.json'), False, False,
                to_ace_layers(trace, columns=4), 0, 50, "handoff-full-pool", compiler_spec=spec,
                total_memories_per_core=memories, simulation_stop_time_s=3,
                scheduler="per-qubit", request_plan=requests, stop_after_workload=True,
                recorder=recorder)
        info = {r.request_id: RequestInfo(r.request_id, r.layer, r.qubit, r.order) for r in requests}
        self.assertEqual(check_events(recorder.events, info, require_completion=True,
                                      submission_after_predecessor=True), [])
        return result, recorder.events

    def test_one_full_memory_can_be_consumed_without_waiting_for_reservation_expiry(self):
        result, events = self.run_full_pool(1, True)
        self.assertEqual(result['stats']['completed_requests'], 1)
        self.assertLess(result['stats']['end_to_end_latency_ms'], 10)
        self.assertEqual(result['compiler_metrics']['pregenerated_hits'], 1)
        bookings = [e for e in events if isinstance(e, Booked) and e.node == 'router_1_1']
        self.assertEqual([e.kind for e in bookings], [ADAPTIVE, APPLICATION])
        self.assertEqual([e.memory_index for e in bookings], [0, 0])
        parts = result['stats']['timing_breakdown'][0]
        self.assertGreaterEqual(parts['reservation_start_delay_time_ms'], .2)
        self.assertGreaterEqual(parts['entanglement_generation_time_ms'], .19)
        reference, _ = self.run_full_pool(3, False)
        self.assertEqual(parts['entanglement_generation_time_ms'],
                         reference['stats']['timing_breakdown'][0]['entanglement_generation_time_ms'])

    def test_default_delivery_uses_the_only_existing_pair_memory(self):
        result, events = self.run_full_pool(1, None)
        self.assertEqual(result['stats']['completed_requests'], 1)
        self.assertEqual(result['compiler_metrics']['pregenerated_hits'], 1)
        self.assertLess(result['stats']['end_to_end_latency_ms'], 10)
        bookings = [e for e in events if isinstance(e, Booked) and e.node == 'router_1_1']
        self.assertEqual([e.memory_index for e in bookings], [0, 0])

    def test_physical_handoff_preserves_pair_state_key_age_and_expiry_at_both_endpoints(self):
        import numpy as np
        schedule = ResourceReservationProtocolAdaptive.schedule
        observed = []

        def inspect_transfer(protocol, reservation):
            candidate = protocol._handoff_candidate(reservation)
            if candidate is None:
                return schedule(protocol, reservation)
            _, lease, _, _ = candidate
            memory = lease['memories'][0]
            memory.bds_decohere()
            qm = protocol.owner.timeline.quantum_manager
            before = np.array(qm.get(memory.qstate_key).state, copy=True)
            key, created, expiry = memory.qstate_key, memory.generation_time, memory.expiration_event
            accepted = schedule(protocol, reservation)
            self.assertTrue(accepted)
            self.assertIs(protocol._reservation_leases[id(reservation)]['memories'][0], memory)
            self.assertEqual(memory.qstate_key, key)
            self.assertEqual(memory.generation_time, created)
            self.assertIs(memory.expiration_event, expiry)
            np.testing.assert_allclose(qm.get(key).state, before, rtol=0, atol=0)
            observed.append(protocol.owner.name)
            return accepted

        with patch.object(ResourceReservationProtocolAdaptive, 'schedule', inspect_transfer):
            result, _ = self.run_full_pool(1, None)
        self.assertEqual(result['stats']['completed_requests'], 1)
        self.assertEqual(set(observed), {'router_1_1', 'router_2_1'})

    def test_two_ready_requests_share_a_full_core_concurrently(self):
        result, _ = self.run_full_pool(2, True)
        manager = result['request_manager']
        self.assertEqual(manager.request_admission_times[0], manager.request_admission_times[1])
        self.assertEqual(result['compiler_metrics']['pregenerated_hits'], 2)
        self.assertLess(result['stats']['end_to_end_latency_ms'], 10)

    def test_legacy_extra_slot_mode_reproduces_the_expiry_stall(self):
        result, _ = self.run_full_pool(1, False)
        self.assertGreater(result['stats']['end_to_end_latency_ms'], 1000)
        self.assertEqual(result['compiler_metrics']['expired_compiler_pairs'], 1)

    def test_booking_transfer_preserves_the_memory_and_cancels_old_cleanup(self):
        protocol = ResourceReservationProtocolAdaptive.__new__(ResourceReservationProtocolAdaptive)
        old_reservation = ReservationAdaptive('a', 'b', 1, 1000, 1, .01, compiler_target_request_id=7)
        application = ApplicationReservation('a', 'b', 10, 100, 1, .01, 1, 7)
        memory = SimpleNamespace(name='m0', qstate_key=123, generation_time=1, expiration_event=object())
        expiry = memory.expiration_event
        old = dict(reservation=old_reservation, memories=[memory], events=['old-timeout'], compiler=True, released=False)
        cards = []
        card = SimpleNamespace(remove=lambda r: cards.append(('remove', r)) or True,
                               add=lambda r: cards.append(('add', r)) or True)
        removed = []
        adaptive = SimpleNamespace(adaptive_memory_used=1)
        protocol.owner = SimpleNamespace(timeline=SimpleNamespace(remove_event=removed.append),
                                         resource_manager=SimpleNamespace(expire=lambda rule: None),
                                         adaptive_continuous=adaptive)
        protocol._reservation_leases = {id(old_reservation): old}
        protocol._handoff_candidate = lambda r: ((('a', 'm0'), ('b', 'm1')), old, card, [])
        self.assertTrue(protocol.schedule(application))
        self.assertTrue(old['released'])
        self.assertEqual(removed, ['old-timeout'])
        self.assertEqual(memory.qstate_key, 123)
        self.assertEqual(memory.generation_time, 1)
        self.assertIs(memory.expiration_event, expiry)
        self.assertIs(protocol._reservation_leases[id(application)]['memories'][0], memory)
        self.assertEqual(adaptive.adaptive_memory_used, 0)
        self.assertEqual([kind for kind, _ in cards], ['remove', 'add'])

    def test_a_peer_must_reject_a_claimed_pair_that_has_expired_instead_of_booking_an_unrelated_slot(self):
        protocol = ResourceReservationProtocolAdaptive.__new__(ResourceReservationProtocolAdaptive)
        application = ApplicationReservation('a', 'b', 10, 100, 1, .01, 1, 7)
        application.compiler_handoff_pair = (('a', 'm0'), ('b', 'm1'))
        protocol._handoff_candidate = lambda reservation: None
        self.assertFalse(protocol.schedule(application))

    def test_future_pairs_cannot_deadlock_an_unprepared_current_layer(self):
        from ace.compiler.compiler_trace import ScheduledPreparation
        requests = (CompilerRequest(0, 1, 0, 0, 5, 9),
                    CompilerRequest(1, 2, 0, 1, 9, 10),
                    CompilerRequest(2, 2, 1, 2, 9, 13))
        trace = CompilerTrace(16, 8, 3, {0: 5, 1: 9, 2: 9}, requests, 3)
        # Both slots at core 9 hold pairs for layer 2, but layer 1 must run first.
        spec = dict(requests=requests, schedule=(ScheduledPreparation(1, 0), ScheduledPreparation(2, 0)),
                    strategy='dynamic', columns=4, planner_blocked=1, planner_peak_memory=2,
                    compiler_memories_per_core=2, fidelity=.01, reservation_duration_ms=1000,
                    reuse_compiler_memory=True)
        recorder = ListRecorder()
        with redirect_stdout(StringIO()):
            result = run_parallel_experiment(
                str(ROOT/'config/final_config/grid_4x4_ace_3.json'), False, False,
                to_ace_layers(trace, columns=4), 0, 50, 'future-cache-progress',
                compiler_spec=spec, total_memories_per_core=2, simulation_stop_time_s=3,
                scheduler='per-qubit', request_plan=requests, stop_after_workload=True,
                recorder=recorder)
        self.assertEqual(result['stats']['completed_requests'], 3)
        self.assertLess(result['stats']['end_to_end_latency_ms'], 20)
        self.assertEqual(result['compiler_metrics']['compiler_progress_yields'], 1)
        expired = [r for r in result['compiler_metrics']['epr_utilization_trace'] if r['status']=='expired']
        self.assertEqual([r['expiry_reason'] for r in expired], ['demand_progress'])
        info = {r.request_id: RequestInfo(r.request_id, r.layer, r.qubit, r.order) for r in requests}
        self.assertEqual(check_events(recorder.events, info, require_completion=True,
                                      submission_after_predecessor=True), [])

    def test_pair_expiry_during_rsvp_rejects_handoff_and_falls_back_without_a_stale_booking(self):
        from sequence.kernel.event import Event
        from sequence.kernel.process import Process
        from sequence.constants import MILLISECOND
        activate = QubitOrderedRequestManager._activate_layer
        injected = []
        def activate_and_expire(manager, index):
            activate(manager, index)
            if index == 1:
                node = manager.name_to_apps['router_2_1'].node
                adaptive = node.adaptive_continuous
                pair = next(iter(adaptive.generated_entanglement_pairs))
                memory = manager.timeline.get_entity_by_name(pair[0][1])
                # Fault injection: expire the peer after local claim but before
                # its RSVP request arrives (one-way control delay is .1 ms).
                manager.timeline.schedule(Event(manager.timeline.now() + int(.05*MILLISECOND),
                                                Process(memory, 'expire', [])))
                injected.append(memory.name)
        with patch.object(QubitOrderedRequestManager, '_activate_layer', activate_and_expire):
            result, _ = self.run_full_pool(1, True)
        self.assertEqual(len(injected), 1)
        self.assertEqual(result['stats']['completed_requests'], 1)
        self.assertLess(result['stats']['end_to_end_latency_ms'], 20)
        self.assertEqual(result['compiler_metrics']['pregenerated_hits'], 0)
        self.assertGreaterEqual(result['compiler_metrics']['expired_compiler_pairs'], 1)


if __name__ == '__main__':
    unittest.main()
