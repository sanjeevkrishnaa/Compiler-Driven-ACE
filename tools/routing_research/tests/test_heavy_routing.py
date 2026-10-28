import sys
from pathlib import Path
import unittest
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from heavy_routing import choose, ALGORITHMS, ADJ, ro, migration_latencies

class RoutingContracts(unittest.TestCase):
    def test_migration_clock_includes_admission_wait_exactly_once(self):
        # Hop 0: eligible at 10, admitted at 12, completed at 14.
        # Hop 1: eligible at 14, admitted at 15, completed at 17.
        parts={0:dict(total_time_ms=4,admission_wait_time_ms=2),
               1:dict(total_time_ms=3,admission_wait_time_ms=1)}
        self.assertEqual(migration_latencies({(0,7):[0,1]},parts),[17-10])

    def test_history_breaks_a_shortest_path_tie_away_from_prior_hotspot(self):
        records=[dict(source_core=0,destination_core=5,path=[0,1,5])]
        self.assertEqual(choose(records,'greedy',Counter({1:100}))[0],[(0,1,5)])
        self.assertEqual(choose(records,'history',Counter({1:100}))[0],[(0,4,5)])

    def test_greedy_spreads_relay_load_without_changing_unavoidable_endpoints(self):
        records=[dict(source_core=0,destination_core=5,path=[0,4,5]) for _ in range(6)]
        paths,_=choose(records,'greedy',Counter())
        self.assertEqual(ro.excess(paths,4,'route'),ro.lower_bound(paths,4,'route'))

    def test_all_routes_preserve_endpoints_and_bound_detours(self):
        records=[dict(source_core=a,destination_core=b,path=[a,b]) for a,b in ((0,15),(3,12),(5,10),(0,3),(0,15),(3,12))]
        for algorithm in ALGORITHMS:
            paths,_=choose(records,algorithm,Counter())
            self.assertEqual(paths,choose(records,algorithm,Counter())[0])
            for r,p in zip(records,paths):
                self.assertEqual((p[0],p[-1]),(r['source_core'],r['destination_core']))
                self.assertEqual(len(p),len(set(p)))
                self.assertTrue(all(b in ADJ[a] for a,b in zip(p,p[1:])))
                self.assertLessEqual(len(p)-1,ro.shortest_length(ADJ,p[0],p[-1])+(2 if algorithm=='detour2' else 0))
    def test_global_optimization_cannot_worsen_xy_excess(self):
        records=[dict(source_core=0,destination_core=15,path=[0,4,8,12,13,14,15]) for _ in range(6)]
        xy,_=choose(records,'xy',Counter())
        for algorithm in ('minexcess','detour2'):
            paths,_=choose(records,algorithm,Counter())
            self.assertLessEqual(ro.excess(paths,4,'route'),ro.excess(xy,4,'route'))
            self.assertGreaterEqual(ro.excess(paths,4,'route'),ro.lower_bound(paths,4,'route'))

    def test_memory_objective_counts_both_incoming_and_outgoing_relay_pairs(self):
        records=[dict(source_core=0,destination_core=5,path=[0,4,5]) for _ in range(4)]
        xy,_=choose(records,'xy',Counter())
        paths,optimal=choose(records,'minhop',Counter())
        self.assertTrue(optimal)
        self.assertEqual(ro.excess(xy,4,'hop'),4)
        self.assertEqual(ro.excess(paths,4,'hop'),0)
if __name__=='__main__':unittest.main()
