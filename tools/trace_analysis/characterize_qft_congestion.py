"""Characterize raw QFT layer demand and observed ACE serialization delay.

Uses existing physical trial records; abstract capacity-wave replays hold each
request's observed service time fixed and are not new physical simulations.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import hashlib
import json
from math import ceil
from pathlib import Path
from statistics import fmean

if __package__:
    from .analyze_trace_hotspots import parse_trace
else:
    from analyze_trace_hotspots import parse_trace


@lru_cache(maxsize=None)
def shortest_mesh_paths(source, target):
    """Enumerate all shortest paths in the row-major 4x4 mesh."""
    if source == target:
        return ((source,),)
    sr, sc = divmod(source, 4)
    tr, tc = divmod(target, 4)
    neighbors = []
    if sr != tr:
        neighbors.append(source + (4 if tr > sr else -4))
    if sc != tc:
        neighbors.append(source + (1 if tc > sc else -1))
    return tuple((source, *tail) for neighbor in neighbors
                 for tail in shortest_mesh_paths(neighbor, target))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def pack_waves(requests, capacity):
    """Greedy endpoint-capacity packing with same-qubit precedence preserved."""
    pending = list(requests)
    result = []
    while pending:
        load = Counter()
        blocked_qubits = set()
        selected, remaining = [], []
        for request_id, qubit, source, target in pending:
            if (qubit not in blocked_qubits and load[source] < capacity
                    and load[target] < capacity):
                selected.append(request_id)
                load[source] += 1
                load[target] += 1
            else:
                remaining.append((request_id, qubit, source, target))
            # At most the first pending hop of a qubit can run in this wave.
            blocked_qubits.add(qubit)
        assert selected
        result.append(selected)
        pending = remaining
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--ace', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    trace = parse_trace(args.trace)
    requests = [(rid, layer, qubit, source, target)
                for rid, (layer, qubit, source, target) in enumerate(trace['hops'])]
    by_layer = defaultdict(list)
    for rid, layer, qubit, source, target in requests:
        by_layer[layer].append((rid, qubit, source, target))
    manager_source = args.ace / 'ace/simulation/parallel_core.py'
    if not manager_source.exists():
        manager_source = args.ace / 'parallel_core.py'  # frozen flat-layout checkouts
    source_tree = ast.parse(manager_source.read_text())
    function = next(node for node in source_tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'serialize_core_conflicts')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'ACE batching', 'exec'), namespace)
    ace_layers = [[(rid, str(source), str(target)) for rid, _, source, target in by_layer[layer]]
                  for layer in range(trace['layers'])]
    batches, origins = namespace['serialize_core_conflicts'](ace_layers)
    batch_ids = [[request[0] for request in batch] for batch in batches]
    indices = defaultdict(list)
    for index, layer in enumerate(origins):
        indices[layer].append(index)
    layer_rows, core_rows = [], []
    degrees = {}
    endpoints_by_layer = {}
    packings = {}
    chains_by_layer = {}
    mandatory_by_layer = {}
    alternate_path_chains = 0
    nonshortest_chains = 0
    for layer in range(trace['layers']):
        hops = by_layer[layer]
        degree = Counter(core for _, _, source, target in hops for core in [source, target])
        degrees[layer] = degree
        chains = []
        for _, qubit, source, target in hops:
            if chains and chains[-1][0] == qubit and chains[-1][1][-1] == source:
                chains[-1][1].append(target)
            else:
                chains.append((qubit, [source, target]))
        chains_by_layer[layer] = chains
        mandatory = Counter()
        for _, path in chains:
            alternatives = shortest_mesh_paths(path[0], path[-1])
            alternate_path_chains += len(alternatives) > 1
            nonshortest_chains += len(path) != len(alternatives[0])
            required = set.intersection(*(set(alternative) for alternative in alternatives))
            for core in required:
                mandatory[core] += 1 if core in [path[0], path[-1]] else 2
        mandatory_by_layer[layer] = mandatory
        endpoints = Counter(core for _, path in chains for core in [path[0], path[-1]])
        endpoints_by_layer[layer] = endpoints
        peak = max(degree.values(), default=0)
        dependency_depth = max(Counter(qubit for _, qubit, _, _ in hops).values(), default=0)
        packings[layer] = {capacity: pack_waves(hops, capacity) for capacity in [1, 3, 4, 999]}
        row = dict(layer=layer, hop_requests=len(hops), peak_core_demand=peak,
                   ace_batches=len(indices[layer]) if hops else 0,
                   dependency_waves=dependency_depth,
                   fixed_endpoint_peak=max(endpoints.values(), default=0))
        for capacity in [3, 4]:
            row[f'overloaded_at_{capacity}'] = int(peak > capacity)
            row[f'hot_cores_at_{capacity}'] = ';'.join(str(core) for core in range(16) if degree[core] > capacity)
            row[f'excess_endpoint_demand_at_{capacity}'] = sum(max(0, value-capacity) for value in degree.values())
            row[f'capacity_wave_lower_bound_at_{capacity}'] = max(ceil(peak/capacity), dependency_depth)
            row[f'greedy_waves_at_{capacity}'] = len(packings[layer][capacity])
        for core in range(16):
            row[f'core_{core}_demand'] = degree[core]
        layer_rows.append(row)
    for core in range(16):
        incidence = sum(degrees[layer][core] for layer in degrees)
        endpoint = sum(endpoints_by_layer[layer][core] for layer in degrees)
        core_rows.append(dict(core=core, row=core//4, column=core%4,
                              incident_hops=incidence, peak_layer_demand=max(degrees[layer][core] for layer in degrees),
                              overloaded_layers_at_3=sum(degrees[layer][core]>3 for layer in degrees),
                              overloaded_layers_at_4=sum(degrees[layer][core]>4 for layer in degrees),
                              fixed_endpoint_incidences=endpoint,
                              internal_relay_incidences=incidence-endpoint,
                              unavoidable_shortest_path_incidences=sum(
                                  mandatory_by_layer[layer][core] for layer in degrees)))
    stats = {}
    active = [layer for layer in range(trace['layers']) if by_layer[layer]]
    for capacity in [3, 4]:
        hot = [layer for layer in active if max(degrees[layer].values())>capacity]
        stats[str(capacity)] = dict(
            overloaded_layers=len(hot), overloaded_layer_ids=hot,
            overloaded_core_layers=sum(degrees[layer][core]>capacity for layer in active for core in range(16)),
            excess_endpoint_demand=sum(max(0,value-capacity) for layer in active for value in degrees[layer].values()),
            affected_hops=sum(degrees[layer][source]>capacity or degrees[layer][target]>capacity
                              for _, layer, _, source, target in requests),
            fixed_endpoints_already_over_capacity_layers=sum(max(endpoints_by_layer[layer].values(),default=0)>capacity for layer in hot),
            relay_only_overload_layers=sum(max(endpoints_by_layer[layer].values(),default=0)<=capacity for layer in hot),
            mandatory_shortest_path_overload_layers=[layer for layer in hot if max(mandatory_by_layer[layer].values(),default=0)>capacity])
    study = json.loads(args.study.read_text())
    buffer_ms = study['parameters']['pregeneration_buffer_ms']
    trial_rows, observed_layers = [], []
    for trial in study['runs']:
        if trial['summary']['strategy'] not in {'dynamic', 'on-demand'}:
            continue
        metrics = trial['stats']
        assert metrics['total_retries'] == 0, 'Delay reconstruction currently requires no retries'
        # Exported layer latencies are measured elapsed batch times. ACE starts
        # the next batch immediately, except for its explicit 5 ms idle-layer
        # delay. Reconstruct starts and verify against measured makespan.
        assert len(metrics['layer_latencies']) == len(batches)
        starts, ends = {}, {}
        cursor = 0.0
        for index, batch in enumerate(batch_ids):
            starts[index] = cursor
            cursor += metrics['layer_latencies'][str(index)]
            ends[index] = cursor
            if not batch and index < len(batches)-1:
                cursor += 5.0
        assert abs(cursor-metrics['end_to_end_latency_ms']) < 1e-6
        durations = {int(k): buffer_ms + value for k,value in metrics['individual_latencies'].items()}
        trial_layers = []
        for layer in active:
            working = indices[layer]
            entry = starts[working[0]]
            actual = ends[working[-1]]-entry
            queue = [starts[index]-entry for index in working for _ in batch_ids[index]]
            ace_sum = sum(max(durations[rid] for rid in batch_ids[index]) for index in working)
            assert abs(ace_sum-actual)<1e-7
            row = dict(strategy=trial['summary']['strategy'], seed=trial['summary']['seed'], layer=layer,
                       overloaded_at_4=int(max(degrees[layer].values())>4),
                       observed_layer_ms=actual, batches=len(working),
                       buffer_ms=len(working)*buffer_ms,
                       exposed_service_ms=actual-len(working)*buffer_ms,
                       within_layer_queue_sum_ms=sum(queue), within_layer_queue_mean_ms=fmean(queue),
                       within_layer_queue_max_ms=max(queue))
            for capacity in [1, 3, 4, 999]:
                row[f'fixed_service_replay_capacity_{capacity}_ms'] = sum(
                    max(durations[rid] for rid in wave) for wave in packings[layer][capacity])
            trial_layers.append(row)
        observed_layers.extend(trial_layers)
        for category, layers in [('all_active',active),('over_4',[l for l in active if max(degrees[l].values())>4]),
                                 ('within_4',[l for l in active if max(degrees[l].values())<=4])]:
            group = [row for row in trial_layers if row['layer'] in layers]
            count = sum(len(by_layer[layer]) for layer in layers)
            result = dict(strategy=trial['summary']['strategy'],seed=trial['summary']['seed'],category=category,
                          layers=len(layers),hop_requests=count,
                          observed_active_layer_ms=sum(row['observed_layer_ms'] for row in group),
                          buffer_ms=sum(row['buffer_ms'] for row in group),
                          exposed_service_ms=sum(row['exposed_service_ms'] for row in group),
                          within_layer_queue_sum_ms=sum(row['within_layer_queue_sum_ms'] for row in group),
                          within_layer_queue_mean_ms=sum(row['within_layer_queue_sum_ms'] for row in group)/count)
            for capacity in [1,3,4,999]:
                result[f'fixed_service_replay_capacity_{capacity}_ms']=sum(row[f'fixed_service_replay_capacity_{capacity}_ms'] for row in group)
            trial_rows.append(result)
    summary = dict(trace=str(args.trace),sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),
                   layer_count=trace['layers'],active_layers=len(active),hop_requests=len(requests),
                   physical_memories_per_core=4,compiler_memory_cap=3,
                   capacity_stats=stats, cores=core_rows,
                   total_ace_communication_batches=sum(row['ace_batches'] for row in layer_rows),
                   total_dependency_waves=sum(row['dependency_waves'] for row in layer_rows),
                   consecutive_hop_chains=sum(len(chains) for chains in chains_by_layer.values()),
                   chains_with_multiple_shortest_paths=alternate_path_chains,
                   nonshortest_chains=nonshortest_chains,
                   capacity_4_greedy_waves=sum(row['greedy_waves_at_4'] for row in layer_rows),
                   capacity_3_greedy_waves=sum(row['greedy_waves_at_3'] for row in layer_rows),
                   worst_layers=sorted([row for row in layer_rows if row['hop_requests']],key=lambda row:-row['peak_core_demand'])[:10],
                   trial_delay_summary=trial_rows)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    write_csv(args.output/'layers.csv',layer_rows)
    write_csv(args.output/'cores.csv',core_rows)
    write_csv(args.output/'observed_layer_delay.csv',observed_layers)
    write_csv(args.output/'trial_delay_summary.csv',trial_rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in {'worst_layers','trial_delay_summary','capacity_stats'}},indent=2))
    print('CAPACITY:',json.dumps({k:{a:b for a,b in v.items() if a!='overloaded_layer_ids'} for k,v in stats.items()}))
    print('TRIALS:',json.dumps(trial_rows))


if __name__ == '__main__':
    main()
