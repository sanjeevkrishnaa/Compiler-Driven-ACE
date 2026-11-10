"""Completed demand must not leave its request-specific generation running."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from ace.compiler.compiler_scheduler import CompilerPreGenerationController
from ace.compiler.compiler_trace import CompilerRequest
from ace.protocols.adaptive_continuous import AdaptiveContinuousProtocol, AdaptiveContinuousMessage, ACMsgType
from ace.resources.reservation import ReservationAdaptive
from test import test_compiler_lifecycle as lifecycle


class CompletionCleanupTests(unittest.TestCase):
    def test_rejected_handoff_releases_its_state_even_before_application_start(self):
        helper=lifecycle.LeaseTests()
        reservation=helper.reservation()
        protocol,_,_,updates=helper.protocol(reservation,compiler=False)
        protocol.owner.timeline.now=lambda: 5
        protocol._reservation_leases[id(reservation)]['handoff']=True
        protocol.release_reservation(reservation,'rejected')
        self.assertEqual(len(updates),1)

    def test_handoff_created_before_rule_loading_still_gets_one_application_timeout(self):
        helper=lifecycle.LeaseTests()
        reservation=helper.reservation()
        protocol,events,_,_=helper.protocol(reservation,compiler=False)
        memories=protocol._reservation_leases[id(reservation)]['memories']
        protocol._reservation_leases[id(reservation)]=dict(reservation=reservation,
            memories=memories,events=[],compiler=False,released=False,handoff=True)
        protocol.accepted_reservations.clear();events.clear()
        protocol._load_owned_rules([],reservation)
        protocol._load_owned_rules([],reservation)
        self.assertEqual(len(events),1)
        self.assertEqual(protocol.accepted_reservations,[reservation])

    def controller(self):
        protocol = SimpleNamespace(_reservation_leases={}, release_reservation=Mock(return_value=True))
        adaptive = SimpleNamespace(send_expire_rules_message=Mock())
        router = SimpleNamespace(network_manager=SimpleNamespace(protocol_stack=[protocol]), adaptive_continuous=adaptive)
        timeline = SimpleNamespace(now=lambda: 10, remove_event=Mock())
        c = CompilerPreGenerationController(timeline=timeline, routers={'router_0_0': router},
            requests=(CompilerRequest(0, 1, 0, 0, 0, 1),), schedule=(), strategy='dynamic',
            columns=2, planner_blocked=0, planner_peak_memory=1, fidelity=.01, reservation_duration_ms=50)
        return c, protocol, adaptive

    def test_completion_cancels_only_its_owned_compiler_lease_and_notifies_peer_once(self):
        c, protocol, adaptive = self.controller()
        reservation = ReservationAdaptive('router_0_0','router_0_1',0,100,1,.01,compiler_target_request_id=0)
        other = ReservationAdaptive('router_0_0','router_0_1',0,100,1,.01,compiler_target_request_id=1)
        protocol._reservation_leases = {
            1: dict(reservation=reservation, compiler=True, released=False),
            2: dict(reservation=other, compiler=True, released=False),
            3: dict(reservation=reservation, compiler=False, released=False),
        }
        c.pending_preparations[0]={}
        c.preparation_retry_events[0]=object()
        c.mark_request_completed(0,10)
        c.mark_request_completed(0,10)
        protocol.release_reservation.assert_called_once_with(reservation,'request_completed')
        adaptive.send_expire_rules_message.assert_called_once_with('router_0_1',reservation,reason='request_completed')
        self.assertNotIn(0,c.pending_preparations)
        self.assertNotIn(0,c.preparation_retry_events)

    def test_discarded_ready_pair_is_cancelled_and_still_counts_as_waste(self):
        c, _, _ = self.controller()
        pair=(('router_0_0','m0'),('router_0_1','m1'))
        c.on_pair_generated(pair,1,.95,dict(target_request_id=0,generation_layer=0,target_layer=1,strategy='dynamic'))
        c.on_pair_expired(pair,10,'request_completed')
        m=c.finalize([0])
        self.assertEqual(m['cancelled_compiler_pairs'],1)
        self.assertEqual(m['expired_compiler_pairs'],0)
        self.assertEqual(m['compiler_waste_percentage'],100)

    def test_timeout_still_counts_as_expiry(self):
        c, _, _ = self.controller()
        pair=(('router_0_0','m0'),('router_0_1','m1'))
        c.on_pair_generated(pair,1,.95,dict(target_request_id=0,generation_layer=0,target_layer=1,strategy='dynamic'))
        c.on_pair_expired(pair,100,'reservation_expired')
        m=c.finalize([0])
        self.assertEqual(m['expired_compiler_pairs'],1)
        self.assertEqual(m['cancelled_compiler_pairs'],0)

    def test_pending_booking_has_one_timeout_and_cannot_be_resurrected_after_cancel(self):
        helper=lifecycle.LeaseTests()
        reservation=helper.reservation()
        protocol,events,_,_=helper.protocol(reservation)
        protocol.owner.timeline.now=lambda: 10
        protocol._load_owned_rules([],reservation,compiler=True)
        self.assertEqual(len(events),1)
        protocol.release_reservation(reservation,'request_completed')
        protocol._load_owned_rules([],reservation,compiler=True)
        self.assertEqual(len(events),1)
        self.assertTrue(protocol._reservation_leases[id(reservation)]['released'])

    def test_late_approval_or_rejection_cannot_reload_rules_or_release_quota_twice(self):
        for answer in (True,False):
            with self.subTest(answer=answer):
                reservation=ReservationAdaptive('a','b',10,100,1,.01,compiler_target_request_id=0)
                p=AdaptiveContinuousProtocol.__new__(AdaptiveContinuousProtocol)
                p.owner=SimpleNamespace(name='a')
                p.adaptive_memory_used=0
                p.resource_reservation=SimpleNamespace(_reservation_leases={id(reservation):{'released':True}})
                message=AdaptiveContinuousMessage(ACMsgType.RESPOND,reservation,answer=answer,path=['a','b'])
                p.received_message('b',message)
                self.assertEqual(p.adaptive_memory_used,0)

    def test_cancelled_future_booking_preserves_the_current_memory_state(self):
        helper=lifecycle.LeaseTests()
        reservation=helper.reservation()
        protocol,_,_,updates=helper.protocol(reservation)
        protocol.owner.timeline.now=lambda: 5
        protocol.release_reservation(reservation,'request_completed')
        self.assertEqual(updates,[])
        self.assertEqual(protocol.owner.adaptive_continuous.adaptive_memory_used,0)


if __name__=='__main__':
    unittest.main()
