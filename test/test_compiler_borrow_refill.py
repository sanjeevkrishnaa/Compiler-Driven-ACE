"""Physical borrowing must transfer the selected memory and replenish its target."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from types import SimpleNamespace
from ace.compiler.compiler_scheduler import CompilerPreGenerationController, _pair_key

from ace.compiler.compiler_trace import CompilerRequest, CompilerTrace, ScheduledPreparation, to_ace_layers
from ace.observability.execution_events import ListRecorder
from ace.observability.invariants import RequestInfo, check_events
from ace.simulation.parallel_core import run_parallel_experiment

ROOT = Path(__file__).resolve().parents[1]


class BorrowRefillTests(unittest.TestCase):
    def test_another_application_cannot_reuse_an_rsvp_claimed_or_consumed_pair(self):
        c=CompilerPreGenerationController.__new__(CompilerPreGenerationController)
        pair=(('a','ma'),('b','mb'))
        c.records=[{'status':'ready'}]
        c.active_record_by_pair={_pair_key(pair):0}
        c.routers={name:SimpleNamespace(network_manager=SimpleNamespace(protocol_stack=[
            SimpleNamespace(memo_arr=[SimpleNamespace(name='ma' if name=='a' else 'mb')],
                timecards=[SimpleNamespace(memory_index=0,reservations=[SimpleNamespace(identity=3)] if name=='a' else [])])])) for name in ('a','b')}
        self.assertFalse(c.pair_available_for_request(pair,4))
        self.assertTrue(c.pair_available_for_request(pair,3))
        c.records[0]['status']='used'
        self.assertFalse(c.pair_available_for_request(pair,3))

    def run_case(self, borrow, reverse=False):
        a,b = (1,0) if reverse else (0,1)
        requests=(CompilerRequest(0,2,0,0,0,1), CompilerRequest(1,5,0,1,a,b))
        trace=CompilerTrace(16,8,2,{0:0,1:a},requests,6)
        spec=dict(requests=requests,schedule=(ScheduledPreparation(1,0),),strategy='dynamic',
                  columns=4,planner_blocked=0,planner_peak_memory=1,compiler_memories_per_core=1,
                  fidelity=.01,reservation_duration_ms=50,reuse_compiler_memory=True,
                  borrow_compiler_pairs=borrow,refill_on_release=True)
        recorder=ListRecorder()
        with redirect_stdout(StringIO()):
            result=run_parallel_experiment(str(ROOT/'config/final_config/grid_4x4_ace_3.json'),
                False,False,to_ace_layers(trace,columns=4),0,50,'borrow-refill-test',
                compiler_spec=spec,total_memories_per_core=2,scheduler='per-qubit',
                request_plan=requests,scheduler_options={'empty_layer_gap_ms':5},
                recorder=recorder,simulation_stop_time_s=1,stop_after_workload=True)
        info={r.request_id:RequestInfo(r.request_id,r.layer,r.qubit,r.order) for r in requests}
        self.assertEqual(check_events(recorder.events,info,require_completion=True,submission_after_predecessor=True),[])
        self.assertEqual(result['stats']['completed_requests'],2)
        return result['compiler_metrics']

    def test_borrowed_pair_is_handed_off_and_replacement_serves_original_target(self):
        for reverse in (False,True):
            with self.subTest(reverse=reverse):
                m=self.run_case(True,reverse)
                self.assertEqual(m['borrowed_compiler_pairs'],1)
                self.assertEqual(m['replacement_preparations_requested'],1)
                self.assertEqual(m['replacement_attempts_immediate'],1)
                used=[r for r in m['epr_utilization_trace'] if r['status']=='used']
                self.assertEqual([(r['target_request_id'],r['actual_request_id']) for r in used],[(1,0),(1,1)])
                self.assertEqual(m['expired_compiler_pairs'],0)

    def test_disabled_borrowing_keeps_future_pair_for_its_target(self):
        m=self.run_case(False)
        self.assertEqual(m['borrowed_compiler_pairs'],0)
        self.assertEqual(m['replacement_preparations_requested'],0)
        self.assertEqual(m['utilized_compiler_pairs'],1)
        self.assertEqual(m['epr_utilization_trace'][0]['actual_request_id'],1)


if __name__=='__main__':
    unittest.main()
