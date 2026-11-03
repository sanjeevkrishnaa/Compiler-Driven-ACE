import unittest
from types import SimpleNamespace
from ace.simulation.request_scheduler import QubitOrderedRequestManager


class ChainCoverageTests(unittest.TestCase):
    def test_snapshot_groups_hops_and_precedes_admission_and_preparation(self):
        m=QubitOrderedRequestManager.__new__(QubitOrderedRequestManager)
        m.timeline=SimpleNamespace(now=lambda:123)
        m.layered_requests=[[(0,),(1,),(2,),(3,)]]
        m.request_qubits={0:7,1:7,2:8,3:9}
        m.record_chain_coverage=True;m.chain_coverage=[];m.layer_start_times={}
        m.layer_activation_order="execution-first";m.admission="event"
        m.predecessor={0:None,1:0,2:None,3:None}
        events=[]
        def ready(rid):
            self.assertEqual(events,[])
            return rid in {0,3}
        m.compiler_controller=SimpleNamespace(request_has_ready_pair=ready,on_original_layer=lambda i:events.append("prepare"))
        m._release=lambda *a,**kw:events.append("release")
        m._try_admit=lambda:events.append("admit")
        m._activate_layer(0)
        self.assertEqual([(r["qubit"],r["ready_hops"],r["coverage"]) for r in m.chain_coverage],[(7,1,"partial"),(8,0,"zero"),(9,1,"full")])
        self.assertEqual(m.chain_coverage[0]["request_ids"],[0,1])
        self.assertEqual(events[-2:],["admit","prepare"])

    def test_disabled_snapshot_does_not_query_pairs(self):
        m=QubitOrderedRequestManager.__new__(QubitOrderedRequestManager)
        m.timeline=SimpleNamespace(now=lambda:0);m.layered_requests=[[]]
        m.layer_start_times={};m.record_chain_coverage=False
        m.layer_activation_order="execution-first";m.compiler_controller=None
        m.empty_layer_gap_ms=5;m._finish_layer=lambda *a,**k:None
        m._activate_layer(0)
