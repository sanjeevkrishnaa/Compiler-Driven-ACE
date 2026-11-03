import unittest
from types import SimpleNamespace
from ace.simulation.parallel_core import seed_entity_indices
from ace.observability.capacity import capacity_diagnostics
from ace.observability.execution_events import Booked,Unbooked,RequestSubmitted,RequestCompleted,ADAPTIVE,APPLICATION
from ace.compiler.compiler_trace import CompilerRequest


class CapacityDiagnosticTests(unittest.TestCase):
    def entities(self,count):
        array=SimpleNamespace(memory_name_to_index={f"m[{i}]":i for i in range(count)})
        return {"node":SimpleNamespace(),**{f"m[{i}]":SimpleNamespace(memory_array=array) for i in range(count)}}

    def test_reference_indices_survive_lexically_interleaved_extra_memories(self):
        old=seed_entity_indices(self.entities(8))
        new=seed_entity_indices(self.entities(256),8)
        self.assertTrue(all(new[n]==i for n,i in old.items()))

    def test_default_indices_keep_original_sorted_order(self):
        entities=self.entities(8)
        self.assertEqual(seed_entity_indices(entities),dict((n,i) for i,n in enumerate(sorted(entities))))

    def test_bound_counts_bookings_and_outstanding_requests_conservatively(self):
        events=[Booked(0,"router_0_0",0,1,0,ADAPTIVE),RequestSubmitted(1,0,0),
                Booked(2,"router_0_0",1,2,0,APPLICATION),
                Unbooked(3,"router_0_0",0,1,0,ADAPTIVE,"consumed"),RequestCompleted(4,0)]
        result=capacity_diagnostics(events,[CompilerRequest(0,0,0,0,0,1)],4,{0:["local_memory_quota"]})
        self.assertEqual(result['peak_booked_slots_per_node']['router_0_0'],2)
        self.assertEqual(result['peak_compiler_bookings_per_node']['router_0_0'],1)
        self.assertEqual(result['peak_booked_plus_outstanding_bound_per_node']['router_0_0'],3)
        self.assertEqual(result['compiler_rejection_reasons'],{'local_memory_quota':1})
