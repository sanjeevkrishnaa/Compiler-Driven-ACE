"""The initial demand admission pass must run before future preparation."""
import unittest
from types import SimpleNamespace
from ace.simulation.request_scheduler import QubitOrderedRequestManager


class LayerActivationOrderTests(unittest.TestCase):
    def activate(self, order, empty=False):
        events=[]
        m=QubitOrderedRequestManager.__new__(QubitOrderedRequestManager)
        m.timeline=SimpleNamespace(now=lambda:123)
        m.layered_requests=[[] if empty else [(0,), (1,)]]
        m.predecessor={0:None,1:None};m.layer_start_times={}
        m.layer_activation_order=order;m.admission="event";m.empty_layer_gap_ms=5
        m.compiler_controller=SimpleNamespace(on_original_layer=lambda i:events.append("prepare"))
        m._release=lambda rid,now,**kw:events.append(("release",rid,kw["schedule_admission"]))
        m._try_admit=lambda:events.append("admit")
        m._finish_layer=lambda *a,**kw:events.append(("finish",kw["gap_ms"]))
        m._activate_layer(0)
        return events

    def test_execution_first_admits_after_collecting_all_eligible_requests(self):
        self.assertEqual(self.activate("execution-first"),[("release",0,False),("release",1,False),"admit","prepare"])

    def test_original_order_is_available_for_control_runs(self):
        self.assertEqual(self.activate("preparation-first"),["prepare",("release",0,True),("release",1,True)])

    def test_empty_layers_still_launch_preparations_then_wait_five_ms(self):
        self.assertEqual(self.activate("execution-first",empty=True),["prepare",("finish",5)])
