import tempfile
from pathlib import Path
import unittest

from tools.congestion_study.hotspot_analysis import (
    Hop, Trace, ace_batches, characterize, pack, preparation_plan, read_trace,
    shortest_route_facts,
)
from tools.congestion_study.run_study import configure, parser


class ArchitectureTests(unittest.TestCase):
    def test_defaults_preserve_total_budget_and_mapper_headroom(self):
        architecture=configure(parser().parse_args([]))
        self.assertEqual(architecture['physical_qubits'],128)
        self.assertEqual(architecture['cores'],16)
        self.assertEqual(architecture['communication_slots_per_core'],4)
        self.assertEqual(architecture['data_slots_per_core'],4)
        self.assertEqual(architecture['requested_circuit_qubits'],48)
        self.assertEqual(architecture['compiler_slots_per_core'],3)
        self.assertEqual(parser().parse_args([]).policy,'dynamic')

    def test_rectangular_mesh_and_capacity_knobs(self):
        args=parser().parse_args(['--mesh','2x3','--total-qubits','72','--memory-slots','3'])
        architecture=configure(args)
        self.assertEqual(architecture['cores'],6)
        self.assertEqual(architecture['data_slots_per_core'],9)
        self.assertEqual(architecture['requested_circuit_qubits'],48)

    def test_overfull_circuit_or_invalid_hardware_is_rejected(self):
        for flags in [['--logical-qubits','128'],['--mesh','3x3'],['--memory-slots','8'],
                      ['--on-demand-reserve','4'],['--buffer-ms','nan']]:
            with self.assertRaises(ValueError):configure(parser().parse_args(flags))


class AnalysisTests(unittest.TestCase):
    def test_layer_vs_batch_counts_and_capacity_threshold(self):
        hops=[Hop(0,0,0,0,1),Hop(1,0,1,0,2),Hop(2,0,2,0,1)]
        trace=Trace(4,8,3,{0:0,1:0,2:0},2,hops)
        result=characterize(trace,2,2,2,1)
        stat=result['summary']['capacity_sensitivity']['2']
        self.assertEqual(stat['overloaded_layers'],1)
        self.assertEqual(stat['overloaded_core_layers'],1)
        self.assertEqual(stat['excess_endpoint_demand'],1)
        self.assertEqual(stat['affected_hops'],3)
        self.assertEqual(result['summary']['active_layers'],1)
        self.assertEqual(result['summary']['empty_layers'],1)
        self.assertEqual(result['summary']['total_ace_batches'],3)

    def test_same_qubit_chain_cannot_run_in_one_wave(self):
        hops=[Hop(0,0,0,0,1),Hop(1,0,0,1,2),Hop(2,0,0,2,3)]
        self.assertEqual([len(w) for w in pack(hops,4)],[1,1,1])
        self.assertEqual(len(ace_batches(hops)),3)

    def test_shortest_path_lower_bound_has_no_internal_mandatory_diagonal_core(self):
        count,required=shortest_route_facts(0,15,4)
        self.assertEqual(count,20)
        self.assertEqual(required,frozenset({0,15}))
        count,required=shortest_route_facts(1,13,4)
        self.assertEqual(count,1)
        self.assertEqual(required,frozenset({1,5,9,13}))

    def test_empty_traffic_has_defined_statistics(self):
        result=characterize(Trace(4,8,1,{0:0},3,[]),2,2,4,3)
        self.assertEqual(result['summary']['hop_requests'],0)
        self.assertEqual(result['summary']['capacity_sensitivity']['4']['overloaded_active_layer_percent'],0)
        self.assertEqual(len(result['layers']),3)

    def test_dynamic_plan_obeys_resource_and_expiry_limits(self):
        trace=Trace(4,8,4,{q:0 for q in range(4)},4,
                    [Hop(q,3,q,0,1 if q%2 else 2) for q in range(4)])
        plan=preparation_plan(trace,'dynamic',2,8,10,6)
        self.assertEqual(len(plan),2)
        self.assertEqual({p['generation_layer'] for p in plan},{2})
        self.assertEqual(preparation_plan(trace,'on-demand',2,8,10,6),[])

    def test_trace_validator_catches_incorrect_qubit_location(self):
        text='''// Number of cores
4
// Number of qubit slots per core
8
// Number of qubits
1
// Initial placement
(0, 0)
// Inter-core communication requests
// Layer 0
(0, 0, 1)
// Layer 1
(0, 0, 2)
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'requests.txt';path.write_text(text)
            with self.assertRaisesRegex(ValueError,'evolving placement'):
                read_trace(path,2,2)


if __name__=='__main__':
    unittest.main()
