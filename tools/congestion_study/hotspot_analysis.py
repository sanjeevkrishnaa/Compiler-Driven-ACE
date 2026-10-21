"""Dependency-free trace validation and mesh congestion characterization."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil, comb, log
from pathlib import Path
import re


@dataclass(frozen=True)
class Hop:
    request_id: int
    layer: int
    qubit: int
    source: int
    target: int


@dataclass
class Trace:
    cores: int
    slots: int
    qubits: int
    initial: dict[int, int]
    layers: int
    hops: list[Hop]


def read_trace(path: Path, rows: int, columns: int) -> Trace:
    markers = {'// number of cores': 'cores', '// number of qubit slots per core': 'slots',
               '// number of qubits': 'qubits'}
    meta, initial, hops = {}, {}, []
    pending = section = None
    layer = -1
    for number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        text = raw.strip()
        if not text:
            continue
        lower = text.lower()
        if lower in markers:
            pending = markers[lower]
        elif lower.startswith('// initial placement'):
            section = 'initial'
        elif lower.startswith('// inter-core communication requests'):
            section = 'requests'
        elif match := re.fullmatch(r'//\s*layer\s+(\d+)', lower):
            new_layer = int(match[1])
            if new_layer != layer + 1:
                raise ValueError(f'{path}:{number}: expected consecutive layer {layer+1}')
            layer = new_layer
            section = 'requests'
        elif text.startswith('//'):
            continue
        elif pending:
            if pending in meta:
                raise ValueError(f'duplicate metadata: {pending}')
            meta[pending] = int(text)
            pending = None
        else:
            if not re.fullmatch(r'\(\s*\d+(?:\s*,\s*\d+)+\s*\)', text):
                raise ValueError(f'{path}:{number}: malformed tuple')
            values = tuple(int(value.strip()) for value in text[1:-1].split(','))
            if section == 'initial' and len(values) == 2:
                if values[0] in initial:
                    raise ValueError('duplicate initial qubit')
                initial[values[0]] = values[1]
            elif section == 'requests' and len(values) == 3 and layer >= 0:
                hops.append(Hop(len(hops), layer, *values))
            else:
                raise ValueError(f'{path}:{number}: tuple in wrong section')
    if set(meta) != {'cores', 'slots', 'qubits'} or min(meta.values()) < 1:
        raise ValueError('missing or non-positive trace metadata')
    if meta['cores'] != rows * columns or set(initial) != set(range(meta['qubits'])):
        raise ValueError('mesh/core count or initial placement mismatch')
    if any(core not in range(meta['cores']) for core in initial.values()):
        raise ValueError('invalid initial core')
    if max(Counter(initial.values()).values(), default=0) > meta['slots']:
        raise ValueError('initial physical capacity exceeded')
    location = dict(initial)
    for hop in hops:
        if location.get(hop.qubit) != hop.source:
            raise ValueError(f'request {hop.request_id}: evolving placement mismatch')
        if hop.source not in range(meta['cores']) or hop.target not in range(meta['cores']):
            raise ValueError('request core outside mesh')
        sr, sc = divmod(hop.source, columns)
        tr, tc = divmod(hop.target, columns)
        if abs(sr-tr) + abs(sc-tc) != 1:
            raise ValueError(f'request {hop.request_id}: nonadjacent mesh hop')
        location[hop.qubit] = hop.target
    return Trace(meta['cores'], meta['slots'], meta['qubits'], initial, layer+1, hops)


def pack(hops: list[Hop], capacity: int) -> list[list[Hop]]:
    """Feasible abstract waves, preserving same-qubit hop order."""
    if capacity < 1:
        raise ValueError('capacity must be positive')
    pending, waves = list(hops), []
    while pending:
        load, seen, selected, remaining = Counter(), set(), [], []
        for hop in pending:
            if hop.qubit not in seen and load[hop.source] < capacity and load[hop.target] < capacity:
                selected.append(hop)
                load[hop.source] += 1
                load[hop.target] += 1
            else:
                remaining.append(hop)
            seen.add(hop.qubit)
        waves.append(selected)
        pending = remaining
    return waves


def ace_batches(hops: list[Hop]) -> list[list[Hop]]:
    """ACE's current one-request/core batching, preserving order at every core."""
    last, batches = {}, []
    for hop in hops:
        index = 1 + max(last.get(hop.source, -1), last.get(hop.target, -1))
        while len(batches) <= index:
            batches.append([])
        batches[index].append(hop)
        last[hop.source] = last[hop.target] = index
    return batches


def shortest_route_facts(source: int, target: int, columns: int) -> tuple[int, frozenset[int]]:
    """Number of equal-hop mesh routes and cores on every such route.

    A straight row/column has one path; when both coordinates differ no
    internal core is mandatory. This avoids enumerating exponentially many
    paths when the mesh knobs are increased.
    """
    sr, sc = divmod(source, columns)
    tr, tc = divmod(target, columns)
    dr, dc = abs(sr-tr), abs(sc-tc)
    count = comb(dr+dc, dr)
    if dr and dc:
        return count, frozenset({source, target})
    step = (columns if tr > sr else -columns) if dr else (1 if tc > sc else -1)
    return count, frozenset(range(source, target+step, step))


def preparation_plan(trace: Trace, policy: str, memories: int, lookahead: int,
                     coherence: float, delta: int) -> list[dict]:
    """Offline admission only; no physical generation/readiness claim."""
    if policy == 'on-demand':
        return []
    memory, generation, plan = Counter(), Counter(), []
    for hop in trace.hops:
        candidates = ([hop.layer-delta] if policy == 'fixed' else
                      range(hop.layer-1, max(-1, hop.layer-lookahead-1), -1))
        for layer in candidates:
            if layer < 0 or hop.layer-layer >= coherence:
                continue
            held = range(layer, hop.layer)
            if any(generation[(core, layer)] >= memories for core in (hop.source, hop.target)):
                continue
            if any(memory[(core, t)] >= memories for core in (hop.source, hop.target) for t in held):
                continue
            for core in (hop.source, hop.target):
                generation[(core, layer)] += 1
                for t in held:
                    memory[(core, t)] += 1
            plan.append(dict(request_id=hop.request_id, generation_layer=layer, target_layer=hop.layer,
                             source=hop.source, target=hop.target, lead_layers=hop.layer-layer))
            break
    return plan


def characterize(trace: Trace, rows: int, columns: int, memories: int, compiler_memories: int,
                 buffer_ms: float = 5.3, service_ms: float | None = None) -> dict:
    by_layer = defaultdict(list)
    for hop in trace.hops:
        by_layer[hop.layer].append(hop)
    capacities = sorted({1, 2, 3, 4, memories, compiler_memories} - {0})
    totals, relay_totals, mandatory_totals = Counter(), Counter(), Counter()
    edges, edge_peaks, edge_active = Counter(), Counter(), Counter()
    core_peaks, hot_by_core = Counter(), {c: Counter() for c in capacities}
    layer_rows, capacity_rows = [], []
    aggregate = {c: dict(capacity=c, overloaded_layers=0, overloaded_core_layers=0,
                        excess_endpoint_demand=0, affected_hops=0,
                        fixed_endpoint_overload_layers=0, mandatory_shortest_path_overload_layers=0)
                 for c in capacities}
    chain_count = alternatives = nonshortest = 0
    for layer in range(trace.layers):
        hops = by_layer[layer]
        load = Counter(core for hop in hops for core in (hop.source, hop.target))
        totals.update(load)
        layer_edges = Counter(tuple(sorted((hop.source,hop.target))) for hop in hops)
        edges.update(layer_edges)
        edge_active.update(layer_edges.keys())
        for edge,count in layer_edges.items():
            edge_peaks[edge] = max(edge_peaks[edge],count)
        chains = []
        for hop in hops:
            if chains and chains[-1][0] == hop.qubit and chains[-1][1][-1] == hop.source:
                chains[-1][1].append(hop.target)
            else:
                chains.append((hop.qubit, [hop.source, hop.target]))
        endpoints, mandatory = Counter(), Counter()
        for _, path in chains:
            endpoints.update([path[0], path[-1]])
            count, required = shortest_route_facts(path[0], path[-1], columns)
            alternatives += count > 1
            chain_count += 1
            sr, sc = divmod(path[0], columns)
            tr, tc = divmod(path[-1], columns)
            nonshortest += len(path)-1 != abs(sr-tr)+abs(sc-tc)
            for core in required:
                mandatory[core] += 1 if core in (path[0], path[-1]) else 2
        for core, count in load.items():
            core_peaks[core] = max(core_peaks[core], count)
            relay_totals[core] += count-endpoints[core]
        mandatory_totals.update(mandatory)
        depth = max(Counter(hop.qubit for hop in hops).values(), default=0)
        current_batches = ace_batches(hops)
        row = dict(layer=layer, hop_requests=len(hops), peak_core_demand=max(load.values(), default=0),
                   ace_batches=len(current_batches), same_qubit_dependency_waves=depth,
                   fixed_endpoint_peak=max(endpoints.values(), default=0),
                   ace_buffer_component_ms=len(current_batches)*buffer_ms)
        if service_ms is not None:
            row['ace_constant_service_estimate_ms'] = len(current_batches)*(buffer_ms+service_ms)
            row['ace_mean_queue_estimate_ms'] = (sum(i*len(batch) for i,batch in enumerate(current_batches))
                                                 * (buffer_ms+service_ms)/len(hops) if hops else 0)
        for core in range(trace.cores):
            row[f'core_{core}_demand'] = load[core]
        for capacity in capacities:
            hot = {core for core, count in load.items() if count > capacity}
            waves = pack(hops, capacity)
            stat = aggregate[capacity]
            stat['overloaded_layers'] += bool(hot)
            stat['overloaded_core_layers'] += len(hot)
            stat['excess_endpoint_demand'] += sum(max(0, count-capacity) for count in load.values())
            stat['affected_hops'] += sum(h.source in hot or h.target in hot for h in hops)
            stat['fixed_endpoint_overload_layers'] += max(endpoints.values(), default=0)>capacity
            stat['mandatory_shortest_path_overload_layers'] += max(mandatory.values(), default=0)>capacity
            hot_by_core[capacity].update(hot)
            item = dict(layer=layer, capacity=capacity, overloaded=int(bool(hot)),
                        hot_cores=';'.join(map(str, sorted(hot))),
                        excess_endpoint_demand=sum(max(0,v-capacity) for v in load.values()),
                        wave_lower_bound=max(ceil(max(load.values(),default=0)/capacity),depth),
                        greedy_waves=len(waves), buffer_component_ms=len(waves)*buffer_ms)
            if service_ms is not None:
                item['constant_service_estimate_ms'] = len(waves)*(buffer_ms+service_ms)
            capacity_rows.append(item)
        layer_rows.append(row)
    active = sum(bool(by_layer[layer]) for layer in range(trace.layers))
    for stat in aggregate.values():
        stat['overloaded_active_layer_percent'] = 100*stat['overloaded_layers']/active if active else 0
        stat['affected_hop_percent'] = 100*stat['affected_hops']/len(trace.hops) if trace.hops else 0
    total_incidence = sum(totals.values())
    shares = [totals[core]/total_incidence for core in range(trace.cores)] if total_incidence else []
    entropy = (-sum(p*log(p) for p in shares if p)/log(trace.cores)
               if trace.cores>1 and shares else 0)
    core_rows = [dict(core=core,row=core//columns,column=core%columns,
                      incident_hops=totals[core],peak_layer_demand=core_peaks[core],
                      overloaded_layers_at_physical_capacity=hot_by_core[memories][core],
                      overloaded_layers_at_compiler_capacity=hot_by_core[compiler_memories][core],
                      internal_relay_incidences=relay_totals[core],
                      relay_fraction=relay_totals[core]/totals[core] if totals[core] else 0,
                      mandatory_shortest_path_incidences=mandatory_totals[core])
                 for core in range(trace.cores)]
    summary = dict(cores=trace.cores,mesh=f'{rows}x{columns}',logical_qubits=trace.qubits,
                   layers=trace.layers,active_layers=active,empty_layers=trace.layers-active,
                   hop_requests=len(trace.hops),hop_chains=chain_count,
                   chains_with_alternative_shortest_paths=alternatives,nonshortest_chains=nonshortest,
                   physical_memories_per_core=memories,compiler_memories_per_core=compiler_memories,
                   capacity_sensitivity={str(c):stat for c,stat in aggregate.items()},
                   peak_core_layer_demand=max(core_peaks.values(),default=0),
                   maximum_to_mean_core_load=max(totals.values(),default=0)/(total_incidence/trace.cores) if total_incidence else 0,
                   normalized_core_load_entropy=entropy,
                   top_3_core_incidence_share=sum(sorted(totals.values(),reverse=True)[:3])/total_incidence if total_incidence else 0,
                   total_ace_batches=sum(row['ace_batches'] for row in layer_rows),
                   ace_buffer_component_ms=sum(row['ace_buffer_component_ms'] for row in layer_rows),
                   total_same_qubit_dependency_waves=sum(row['same_qubit_dependency_waves'] for row in layer_rows),
                   total_greedy_physical_capacity_waves=sum(row['greedy_waves'] for row in capacity_rows if row['capacity']==memories),
                   delay_model='abstract scheduling/buffer components, not measured physical latency',
                   assumed_hop_service_ms=service_ms,buffer_per_batch_ms=buffer_ms)
    return dict(summary=summary,layers=layer_rows,capacities=capacity_rows,cores=core_rows,
                edges=[dict(source=a,target=b,hop_requests=count,active_layers=edge_active[(a,b)],
                            peak_layer_hops=edge_peaks[(a,b)]) for (a,b),count in sorted(edges.items())])
