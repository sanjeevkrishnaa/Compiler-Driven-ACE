import unittest
from dataclasses import replace
from ace.compiler.compiler_trace import CompilerRequest, CompilerTrace, plan_preparations


class ActiveLayerPlannerTests(unittest.TestCase):
    def trace(self, layers):
        return CompilerTrace(16,8,len(layers),{},tuple(CompilerRequest(i,L,i,i,0,1) for i,L in enumerate(layers)),max(layers,default=-1)+1)

    def plan(self, layers, **kw):
        return plan_preparations(self.trace(layers),strategy="dynamic",compiler_memories_per_core=50,
            generation_capacity_per_core=kw.pop("capacity",50),coherence_time_layers=kw.pop("coherence",10),
            dynamic_lookahead_layers=8,lead_layers=2,layer_basis="active",**kw)

    def test_second_previous_active_layer_not_previous_logical_layer(self):
        schedule,blocked,_=self.plan([2,5,9,15,20])
        self.assertEqual({p.request_id:p.generation_layer for p in schedule},{2:2,3:5,4:9})
        self.assertEqual(blocked,2)

    def test_capacity_moves_candidate_to_earlier_active_layer(self):
        trace=self.trace([2,5,9,15,20,20])
        trace=replace(trace,requests=tuple(replace(r,source_core=2,destination_core=3) if r.request_id<4 else r for r in trace.requests))
        schedule,_,_=plan_preparations(trace,strategy="dynamic",compiler_memories_per_core=50,
            generation_capacity_per_core=1,coherence_time_layers=10,lead_layers=2,layer_basis="active")
        chosen={p.request_id:p.generation_layer for p in schedule}
        self.assertEqual((chosen[4],chosen[5]),(9,5))

    def test_runtime_candidates_use_active_age_not_raw_layer_distance(self):
        schedule,blocked,peak=self.plan([0,100,200],planning_mode="runtime",coherence=3)
        self.assertEqual([(p.request_id,p.generation_layer) for p in schedule],[(2,0)])
        self.assertEqual(blocked,2);self.assertIsNone(peak)

    def test_empty_trace_has_no_preparation(self):
        self.assertEqual(self.plan([]),((),0,0))

    def test_eighth_active_layer_is_last_candidate(self):
        schedule,_,_=self.plan(list(range(0,100,10)))
        active=list(range(0,100,10));rank={L:i for i,L in enumerate(active)}
        for p in schedule:self.assertTrue(2<=rank[active[p.request_id]]-rank[p.generation_layer]<=8)
