"""Initiator completion must release remote bookings even without peer credit."""
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch
from ace.applications.request_app_parallel import RequestAppLatencyParallel


class CompletionMessagesTests(TestCase):
    def test_physical_peer_without_credit_is_released_after_real_message_delay(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from pathlib import Path
        from ace.applications.request_app import RequestAppLatency
        from ace.compiler.compiler_trace import CompilerTrace, CompilerRequest, to_ace_layers
        from ace.simulation.parallel_core import run_parallel_experiment
        from ace.observability.execution_events import ListRecorder, RequestCompleted, Unbooked
        from ace.observability.invariants import RequestInfo, check_events, BOOKING_SURVIVES_COMPLETION
        trace=CompilerTrace(16,4,1,{0:0},(CompilerRequest(0,0,0,0,0,1),),1)
        original=RequestAppLatencyParallel.get_memory
        def miss_peer_credit(app,info):
            res=app.memo_to_reservation.get(info.index)
            if res is not None and info.remote_node==res.initiator:
                return  # Reproduce the missing responder completion callback.
            return original(app,info)
        fixed=RequestAppLatencyParallel.send_expire_rules_message
        for notify, expect_failure in [(RequestAppLatency.send_expire_rules_message,True),(fixed,False)]:
            recorder=ListRecorder()
            spec=dict(requests=trace.requests,schedule=(),strategy='on-demand',columns=4,
                      planner_blocked=0,planner_peak_memory=0,compiler_memories_per_core=0,
                      fidelity=.01,reservation_duration_ms=50)
            with patch.object(RequestAppLatencyParallel,'get_memory',miss_peer_credit), \
                    patch.object(RequestAppLatencyParallel,'send_expire_rules_message',notify), redirect_stdout(StringIO()):
                result=run_parallel_experiment(str(Path(__file__).resolve().parents[1]/
                    'config/final_config/grid_4x4_ace_3.json'),False,False,to_ace_layers(trace,columns=4),
                    0,50,'peer-cleanup-regression',seed=62,compiler_spec=spec,total_memories_per_core=4,
                    stop_after_workload=True,simulation_stop_time_s=1,recorder=recorder,scheduler='per-qubit',
                    request_plan=trace.requests,scheduler_options=dict(admission='event'))
            self.assertEqual(result['stats']['completed_requests'],1)
            violations=check_events(recorder.events,{0:RequestInfo(0,0,0,0)},require_completion=True)
            if expect_failure:
                self.assertEqual([v.invariant for v in violations],[BOOKING_SURVIVES_COMPLETION])
            else:
                self.assertEqual(violations,[])
                completed=next(e.time_ps for e in recorder.events if isinstance(e,RequestCompleted))
                released=next(e.time_ps for e in recorder.events if isinstance(e,Unbooked) and e.node=='router_0_1')
                self.assertGreater(released,completed)
                self.assertLess(released-completed,1e9)

    def app(self):
        app=RequestAppLatencyParallel.__new__(RequestAppLatencyParallel)
        app.node=SimpleNamespace(name='source',adaptive_continuous=SimpleNamespace(
            send_expire_rules_message=Mock()))
        return app

    def test_direct_link_notifies_responder_without_synchronous_peer_access(self):
        app=self.app();reservation=SimpleNamespace(path=['source','peer'])
        app.send_expire_rules_message(reservation)
        app.node.adaptive_continuous.send_expire_rules_message.assert_called_once_with('peer',reservation)

    def test_multihop_preserves_intermediate_cleanup_and_notifies_peer_once(self):
        app=self.app();reservation=SimpleNamespace(path=['source','middle','peer'])
        app.send_expire_rules_message(reservation)
        calls=app.node.adaptive_continuous.send_expire_rules_message.call_args_list
        self.assertEqual([c.args for c in calls],[('middle',reservation),('peer',reservation)])


if __name__=='__main__':main()
