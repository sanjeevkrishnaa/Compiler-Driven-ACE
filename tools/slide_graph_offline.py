"""Trace-derived congestion and planner evidence for the corrected slide deck."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ace.compiler.compiler_trace import parse_compiler_trace, plan_preparations
from tools.benchmark_matrix import WORKLOADS, save
OUT = ROOT/'output/slide-graphs-2026-11-04'
TRACES = ROOT/'output/benchmark-matrix-224-2026-11-04/routed/traces'


def main():
    summaries, cores, plans = [], [], []
    for workload in WORKLOADS:
        for route in ('xy', 'history'):
            trace = parse_compiler_trace(TRACES/workload/'seed_42'/route/'requests.txt')
            active = sorted({r.layer for r in trace.requests})
            rank = {layer:i for i,layer in enumerate(active)}
            counts = Counter((r.layer, c) for r in trace.requests for c in r.edge)
            overloaded = {key for key, value in counts.items() if value > 8}
            summaries.append(dict(workload=workload, route=route, hops=len(trace.requests),
                active_layers=len(active), overloaded_core_layers=len(overloaded),
                overloaded_layers=len({layer for layer,core in overloaded}),
                hops_touching_overload=sum(any((r.layer,c) in overloaded for c in r.edge) for r in trace.requests),
                peak_endpoint_hops=max(counts.values(), default=0), threshold=8,
                history_routing_reference_capacity=4))
            for core in range(16):
                cores.append(dict(workload=workload, route=route, core=core,
                    overloaded_layers=sum((layer,core) in overloaded for layer in active),
                    active_layers=len(active), peak=max((counts[(layer,core)] for layer in active),default=0)))
            by_id = {r.request_id:r for r in trace.requests}
            for total,quota in ((4,3),(8,6),(8,8),(256,256)):
                for lead in (1,2):
                    scheduled,blocked,peak = plan_preparations(trace, strategy='dynamic',
                        compiler_memories_per_core=quota, generation_capacity_per_core=total,
                        coherence_time_layers=10, dynamic_lookahead_layers=8, lead_layers=lead,
                        layer_basis='active', preparation_priority='chain-length')
                    distribution=Counter(rank[by_id[p.request_id].layer]-rank[p.generation_layer] for p in scheduled)
                    plans.append(dict(workload=workload,route=route,total_memories=total,compiler_quota=quota,
                        minimum_lead=lead,maximum_lead=8,scheduled=len(scheduled),blocked=blocked,
                        peak_planned_occupancy=peak,active_layer_lead_distribution=dict(distribution),
                        scope='offline planner replay, not physical runtime outcome'))
    save(OUT/'congestion-summary.json', summaries)
    save(OUT/'congestion-cores.json', cores)
    save(OUT/'planner-replay.json', plans)
    print(len(summaries),'trace summaries;',len(cores),'core records;',len(plans),'planner replays')


if __name__ == '__main__': main()
