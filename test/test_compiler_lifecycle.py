"""Reservation ownership regressions requiring the compatible SeQUeNCe fork."""
from types import SimpleNamespace
import unittest

from reservation import ReservationAdaptive, ResourceReservationProtocolAdaptive
from sequence.network_management.reservation import Reservation


class LeaseTests(unittest.TestCase):
    def reservation(self, target=1):
        return ReservationAdaptive('a', 'b', 10, 100, 1, .9,
                                   compiler_target_request_id=target)

    def protocol(self, reservation, compiler=True):
        events, removed, updates, expirations = [], [], [], []
        memory = SimpleNamespace(name='m0')
        manager = SimpleNamespace(
            rule_manager=SimpleNamespace(rules=[]),
            memory_manager=SimpleNamespace(get_info_by_memory=lambda memory: SimpleNamespace(index=0)),
            update=lambda *args: updates.append(args))
        app = SimpleNamespace(memo_to_reservation={0: reservation})
        adaptive = SimpleNamespace(adaptive_memory_used=1 if compiler else 0,
                                   note_memory_expiration=lambda *args, **kwargs: expirations.append(args))
        owner = SimpleNamespace(
            timeline=SimpleNamespace(schedule=events.append, remove_event=removed.append),
            resource_manager=manager, adaptive_continuous=adaptive, app=app)
        protocol = ResourceReservationProtocolAdaptive.__new__(ResourceReservationProtocolAdaptive)
        protocol.owner = owner
        protocol.timecards = [SimpleNamespace(memory_index=0, reservations=[reservation])]
        protocol.memo_arr = [memory]
        protocol.accepted_reservations = []
        protocol._reservation_leases = {}
        protocol._load_owned_rules([], reservation, compiler=compiler)
        return protocol, events, removed, updates

    def test_same_edge_simultaneous_compiler_targets_are_distinct(self):
        first, second = self.reservation(1), self.reservation(2)
        self.assertNotEqual(first, second)
        self.assertEqual(len({first, second}), 2)
        self.assertEqual(first, self.reservation(1))
        self.assertEqual(hash(first), hash(self.reservation(1)))

    def test_noncompiler_reservation_keeps_base_hash_contract(self):
        adaptive = self.reservation(None)
        ordinary = Reservation('a', 'b', 10, 100, 1, .9)
        self.assertEqual(adaptive, ordinary)
        self.assertEqual(hash(adaptive), hash(ordinary))

    def test_compiler_release_is_local_idempotent_and_cancels_events(self):
        reservation = self.reservation()
        protocol, events, removed, updates = self.protocol(reservation)
        peer, _, _, _ = self.protocol(reservation)
        self.assertTrue(protocol.release_reservation(reservation, 'consumed'))
        self.assertEqual(protocol.timecards[0].reservations, [])
        self.assertEqual(protocol.owner.adaptive_continuous.adaptive_memory_used, 0)
        self.assertEqual(protocol.owner.app.memo_to_reservation, {})
        self.assertEqual(removed, events)
        self.assertEqual(len(updates), 1)
        self.assertFalse(protocol.release_reservation(reservation))
        self.assertEqual(len(updates), 1)
        self.assertEqual(peer.timecards[0].reservations, [reservation])
        self.assertEqual(peer.owner.adaptive_continuous.adaptive_memory_used, 1)

    def test_stale_expiry_does_not_reset_reassigned_memory(self):
        old = self.reservation(1)
        protocol, _, _, updates = self.protocol(old)
        protocol.release_reservation(old, 'consumed')
        new = self.reservation(2)
        protocol.timecards[0].reservations.append(new)
        protocol._load_owned_rules([], new, compiler=True)
        protocol.owner.adaptive_continuous.adaptive_memory_used = 1
        count = len(updates)
        self.assertFalse(protocol.release_reservation(old, 'reservation_expired'))
        self.assertEqual(len(updates), count)
        self.assertEqual(protocol.timecards[0].reservations, [new])
        self.assertEqual(protocol.owner.adaptive_continuous.adaptive_memory_used, 1)

    def test_application_completion_releases_card_without_touching_compiler_quota(self):
        reservation = Reservation('a', 'b', 10, 100, 1, .9)
        protocol, events, removed, _ = self.protocol(reservation, compiler=False)
        protocol.owner.adaptive_continuous.adaptive_memory_used = 2
        protocol.release_reservation(reservation)
        self.assertEqual(protocol.timecards[0].reservations, [])
        self.assertEqual(protocol.owner.adaptive_continuous.adaptive_memory_used, 2)
        self.assertEqual(events, removed)


class AdmissionTests(unittest.TestCase):
    def controller(self):
        from compiler_scheduler import CompilerPreGenerationController
        from compiler_trace import CompilerRequest, ScheduledPreparation
        events, removed, calls = [], [], []
        clock = SimpleNamespace(now=lambda: 0, schedule=events.append, remove_event=removed.append)
        request = CompilerRequest(0, 3, 0, 0, 0, 1)
        adaptive = SimpleNamespace(request_compiler_pair=lambda *args: calls.append(args))
        controller = CompilerPreGenerationController(
            timeline=clock, routers={'router_0_0': SimpleNamespace(adaptive_continuous=adaptive)},
            requests=(request,), schedule=(ScheduledPreparation(0, 0),),
            strategy='dynamic', columns=2, planner_blocked=0, planner_peak_memory=1,
            fidelity=.01, reservation_duration_ms=1000)
        return controller, events, removed, calls

    def test_rejected_compiler_job_retries_and_stops_at_first_submission(self):
        controller, events, removed, calls = self.controller()
        controller.on_original_layer(0)
        self.assertEqual(len(calls), 1)
        controller.on_preparation_rejected(0, 'local_memory_quota')
        self.assertEqual(len(events), 1)
        controller.mark_request_start(0, 10)
        self.assertEqual(events, removed)
        controller.retry_preparation(0)
        self.assertEqual(len(calls), 1)

    def test_accepted_compiler_job_is_not_launched_again(self):
        controller, _, _, calls = self.controller()
        controller.on_original_layer(0)
        controller.on_preparation_accepted(0)
        controller.retry_preparation(0)
        self.assertEqual(len(calls), 1)


class PhysicalIntegrationTests(unittest.TestCase):
    def test_ready_pairs_reduce_latency_against_corrected_odg_and_seed_changes_sampling(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from pathlib import Path
        from compiler_trace import parse_compiler_trace, plan_preparations, to_ace_layers
        from parallel_core import run_parallel_experiment
        root = Path(__file__).resolve().parents[1]
        trace = parse_compiler_trace(root/'data/tracegen/random16_d80_seed303.txt')
        def run(strategy, seed):
            plan, blocked, peak = plan_preparations(trace, strategy=strategy,
                compiler_memories_per_core=3, generation_capacity_per_core=3,
                coherence_time_layers=10, delta_layers=6, dynamic_lookahead_layers=8)
            spec = dict(requests=trace.requests, schedule=plan, strategy=strategy, columns=4,
                planner_blocked=blocked, planner_peak_memory=peak,
                compiler_memories_per_core=0 if strategy=='on-demand' else 3,
                fidelity=.01, reservation_duration_ms=1000)
            with redirect_stdout(StringIO()):
                return run_parallel_experiment(str(root/'config/final_config/grid_4x4_ace_3.json'),
                    False, False, to_ace_layers(trace, columns=4), 5.3, 50,
                    'compiler-lifecycle-regression', seed=seed, compiler_spec=spec,
                    total_memories_per_core=4, simulation_stop_time_s=5, serialize_conflicts=True)
        odg, compiler, other_seed = run('on-demand', 0), run('dynamic', 0), run('on-demand', 1)
        for result in [odg, compiler, other_seed]:
            stats = result['stats']
            self.assertEqual(stats['completed_requests'], 62)
            self.assertEqual(stats['total_retries'], 0)
            for rid, row in stats['timing_breakdown'].items():
                self.assertAlmostEqual(row['total_time_ms'], stats['individual_latencies'][rid])
                self.assertGreaterEqual(row['entanglement_generation_time_ms'], 0)
        self.assertLess(compiler['stats']['avg_request_latency_ms'], odg['stats']['avg_request_latency_ms'])
        self.assertLess(compiler['stats']['end_to_end_latency_ms'], odg['stats']['end_to_end_latency_ms'])
        self.assertNotEqual(odg['stats']['node_seeds'], other_seed['stats']['node_seeds'])
        self.assertNotEqual(odg['stats']['individual_latencies'], other_seed['stats']['individual_latencies'])
        for pair in compiler['compiler_metrics']['epr_utilization_trace']:
            self.assertEqual(pair['status'], 'used')
            self.assertEqual(pair['target_request_id'], pair['actual_request_id'])


if __name__ == '__main__':
    unittest.main()
