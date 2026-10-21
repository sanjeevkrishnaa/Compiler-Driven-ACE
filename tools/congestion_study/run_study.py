#!/usr/bin/env python3
"""MQT Bench/QASM -> supplied qmap mapper -> trace -> congestion reports.

Run directly with Python 3.11+; see README.md beside this file. This module
does not import the SeQUeNCe simulator unless optional ACE execution is requested.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import importlib
import importlib.metadata
import inspect
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from types import SimpleNamespace

if __package__:
    from .hotspot_analysis import characterize, preparation_plan, read_trace
else:
    from hotspot_analysis import characterize, preparation_plan, read_trace

DEFAULT_WORKLOADS = ['qft', 'ghz', 'qaoa', 'vqe_real_amp',
                     'cdkm_ripple_carry_adder', 'draper_qft_adder']
BENCH_URL = 'https://github.com/munich-quantum-toolkit/bench/tree/main/src/mqt/bench/benchmarks'


def dump_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str)+'\n', encoding='utf-8')


def dump_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else [])
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def versions():
    result = {'python': platform.python_version()}
    for package in ['mqt-bench', 'qiskit', 'numpy', 'scipy', 'networkx', 'qm2026']:
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = 'not installed'
    return result


def git_commit(path):
    try:
        return subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--mapper-dir', type=Path, help='Checkout containing the supplied qmap/ package (TraceGen)')
    p.add_argument('--bench-dir', type=Path, help='Optional MQT Bench checkout; uses its src/ instead of installed package')
    p.add_argument('--workloads', nargs='+', help='MQT benchmark module names; defaults to six workloads when no QASM is supplied')
    p.add_argument('--qasm', type=Path, nargs='+', default=[], help='Additional OpenQASM 2/3 input files')
    p.add_argument('--workload-options', type=Path, help='JSON object: benchmark name -> create_circuit keyword arguments')
    p.add_argument('--mesh', default='4x4')
    p.add_argument('--total-qubits', type=int, default=128, help='Total physical slots INCLUDING communication memories')
    p.add_argument('--memory-slots', type=int, default=4, help='Communication memories PER CORE, deducted from physical capacity')
    p.add_argument('--on-demand-reserve', type=int, default=1, help='Slots within the memory bank reserved for fallback/adoption')
    p.add_argument('--spare-data-slots-per-core', type=int, default=1, help='Initial data vacancies needed by the supplied migration mapper')
    p.add_argument('--logical-qubits', type=int, help='Requested circuit width; defaults to data capacity minus initial spare slots')
    p.add_argument('--policy', choices=['dynamic', 'fixed', 'on-demand'], default='dynamic')
    p.add_argument('--dynamic-lookahead-layers', type=int, default=8)
    p.add_argument('--coherence-time-layers', type=float, default=10)
    p.add_argument('--delta-layers', type=int, default=6)
    p.add_argument('--placer', default='HQA', help='Supplied mapper algorithm; separate from EPR preparation policy')
    p.add_argument('--initial-placement', default='oee')
    p.add_argument('--reliability-min', type=float, default=0.1)
    p.add_argument('--reliability-max', type=float, default=1.0)
    p.add_argument('--seeds', nargs='+', default=['42'], help='Mapping/hardware seeds, space or comma separated')
    p.add_argument('--circuit-seed', type=int, default=42, help='Seed passed to factories that support it and for parameter binding')
    p.add_argument('--optimization-level', type=int, choices=range(4), default=0)
    p.add_argument('--buffer-ms', type=float, default=5.3, help='Per-wave buffer for abstract scheduling components')
    p.add_argument('--hop-service-ms', type=float, help='Optional constant service assumption; estimates ONLY, not physical latency')
    p.add_argument('--simulate', action='store_true', help='Also run repaired physical ACE for the selected policy')
    p.add_argument('--ace-dir', type=Path)
    p.add_argument('--sequence-dir', type=Path, help='Compatible qnoc-stress-testing/SeQUeNCe runtime for physical ACE')
    p.add_argument('--ace-config', type=Path)
    p.add_argument('--stop-time-s', type=float, default=300)
    p.add_argument('--output', type=Path, default=Path('output/mqt_congestion_study'))
    return p


def configure(args):
    match = re.fullmatch(r'(\d+)x(\d+)', args.mesh.lower())
    if not match or min(map(int, match.groups())) < 1:
        raise ValueError('--mesh must be positive ROWSxCOLUMNS')
    rows, columns = map(int, match.groups())
    cores = rows*columns
    if cores < 2 or args.total_qubits <= 0 or args.total_qubits % cores:
        raise ValueError('--total-qubits must divide evenly among at least two cores')
    slots = args.total_qubits//cores
    if not 1 <= args.memory_slots < slots:
        raise ValueError('memory slots must leave at least one data slot per core')
    if not 0 <= args.on_demand_reserve < args.memory_slots:
        raise ValueError('--on-demand-reserve must leave at least one compiler slot')
    data_slots = slots-args.memory_slots
    if data_slots < 2:
        raise ValueError('the two-qubit mapper needs at least two data slots per core')
    spare = args.spare_data_slots_per_core
    if not 0 <= spare < data_slots:
        raise ValueError('--spare-data-slots-per-core must leave at least one initially occupied data slot')
    workload_capacity = cores*(data_slots-spare)
    logical = args.logical_qubits if args.logical_qubits is not None else workload_capacity
    if not 1 <= logical <= workload_capacity:
        raise ValueError(f'circuit width must fit {workload_capacity} initial data slots; increase --total-qubits or reduce --spare-data-slots-per-core')
    if not 0 < args.reliability_min <= args.reliability_max <= 1:
        raise ValueError('reliability range must satisfy 0 < min <= max <= 1')
    if (min(args.dynamic_lookahead_layers, args.delta_layers, args.coherence_time_layers) <= 0
            or not math.isfinite(args.coherence_time_layers)):
        raise ValueError('lookahead, delta and coherence must be positive')
    if (not math.isfinite(args.buffer_ms) or args.buffer_ms < 0 or
            (args.hop_service_ms is not None and
             (not math.isfinite(args.hop_service_ms) or args.hop_service_ms < 0))):
        raise ValueError('time assumptions must be nonnegative')
    if not math.isfinite(args.stop_time_s) or args.stop_time_s <= 0:
        raise ValueError('--stop-time-s must be finite and positive')
    seeds = [int(seed) for group in args.seeds for seed in group.split(',')]
    if not seeds or min(seeds) < 0 or args.circuit_seed < 0 or len(set(seeds)) != len(seeds):
        raise ValueError('seeds must be nonnegative and distinct')
    return dict(mesh=args.mesh, rows=rows, columns=columns, cores=cores,
                physical_qubits=args.total_qubits, physical_slots_per_core=slots,
                communication_slots_per_core=args.memory_slots,
                compiler_slots_per_core=args.memory_slots-args.on_demand_reserve,
                fallback_slots_per_core=args.on_demand_reserve,
                data_slots_per_core=data_slots, data_capacity=cores*data_slots,
                initial_spare_data_slots_per_core=spare, initial_workload_capacity=workload_capacity,
                requested_circuit_qubits=logical, seeds=seeds)


def load_circuit(name, qasm_path, width, args, options):
    import numpy as np
    from qiskit import QuantumCircuit, qasm2, qasm3, transpile
    source = {}
    if qasm_path is not None:
        text = qasm_path.read_text(encoding='utf-8')
        circuit = qasm3.loads(text) if re.search(r'OPENQASM\s+3', text) else qasm2.loads(text)
        source = dict(kind='qasm', path=str(qasm_path.resolve()), sha256=digest(qasm_path))
    else:
        if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
            raise ValueError('workload names must be MQT benchmark module names')
        module = importlib.import_module(f'mqt.bench.benchmarks.{name}')
        factory = module.create_circuit
        kwargs = dict(options.get(name, {}))
        if 'seed' in inspect.signature(factory).parameters:
            kwargs.setdefault('seed', args.circuit_seed)
        circuit = factory(width, **kwargs)
        source = dict(kind='mqt-bench', benchmark=name, factory_options=kwargs,
                      factory_source=str(Path(module.__file__).resolve()),
                      factory_sha256=digest(Path(module.__file__)),
                      reference=f'{BENCH_URL.replace("/tree/", "/blob/")}/{name}.py')
    if not isinstance(circuit, QuantumCircuit):
        raise ValueError('factory must return a Qiskit QuantumCircuit')
    raw_qubits = circuit.num_qubits
    if circuit.parameters:
        rng = np.random.default_rng(args.circuit_seed)
        circuit = circuit.assign_parameters({p:float(rng.uniform(0,2*np.pi))
                                             for p in sorted(circuit.parameters,key=str)})
    circuit = circuit.remove_final_measurements(inplace=False)
    for item in circuit.data:
        op = item.operation
        if (op.name in {'measure','reset'} or hasattr(op, 'blocks')
                or getattr(op, 'condition', None) is not None):
            raise ValueError('mid-circuit measurement, reset and classical control are not supported by this static mapper')
    circuit = transpile(circuit, basis_gates=['rz','sx','x','cx'],
                        optimization_level=args.optimization_level, seed_transpiler=args.circuit_seed)
    from qmap.circuit.ir import Circuit, Gate
    gates = []
    for item in circuit.data:
        op = item.operation
        qubits = tuple(circuit.find_bit(qubit).index for qubit in item.qubits)
        if len(qubits)>2 and op.name!='barrier':
            raise ValueError(f'operation {op.name} was not decomposed to one/two-qubit gates')
        gates.append(Gate(op.name, qubits, tuple(float(value) for value in op.params)))
    ir = Circuit(name=name, n_qubits=circuit.num_qubits, gates=tuple(gates))
    return circuit, ir, {**source, 'actual_qubits':raw_qubits,
                         'normalized_depth':circuit.depth(), 'normalized_gates':len(circuit.data),
                         'basis_gates':['rz','sx','x','cx'], 'optimization_level':args.optimization_level,
                         'circuit_seed':args.circuit_seed,
                         'final_measurements_removed':True}


def map_and_export(ir, architecture, seed, args, folder):
    import numpy as np
    from qmap.architecture.reliability import ReliabilityBand
    from qmap.experiments.runner import prepare_trial, run_trial
    from qmap.io.requests import write_request_file
    from qmap.placement.base import PlacerConfig
    from qmap.rng import SeedSequence
    from qmap.validation import validate_partition
    band = ReliabilityBand(args.reliability_min, args.reliability_max)
    # The supplied mapper treats reserved_ancilla as an INITIAL placement
    # reservation, while later assignments may use its full capacity. Pass
    # only the DATA bank as mapper capacity, so it cannot occupy comm memories.
    setup = prepare_trial(grid=args.mesh, benchmark=ir.name, seed=SeedSequence.from_seed(seed),
        reliability_band=band, qubits_per_core=architecture['data_slots_per_core'],
        reserved_ancilla=architecture['initial_spare_data_slots_per_core'], circuit=ir, topology='mesh')
    result = run_trial(setup, args.placer, PlacerConfig(initial_placement=args.initial_placement,strict=True),
                       benchmark=ir.name, reliability_band=band.label, keep_partition=True)
    partition = result.partition
    validation = validate_partition(partition, setup.sliced, setup.architecture)
    if not validation.is_complete:
        raise ValueError(f'{validation.uncolocated_operations} two-qubit operations remain unplaced')
    # The mapper output records actual DATA placements; the trace header must
    # advertise the full architecture capacity including the separate bank.
    export_arch = SimpleNamespace(n_cores=architecture['cores'],
                                 qubits_per_core=architecture['physical_slots_per_core'])
    trace_file, hop_count = write_request_file(partition, export_arch, setup.oracle, folder/'requests.txt')
    trace = read_trace(trace_file, architecture['rows'], architecture['columns'])
    assert len(trace.hops)==hop_count
    location = dict(trace.initial)
    by_layer = {}
    for hop in trace.hops:
        by_layer.setdefault(hop.layer,[]).append(hop)
    for layer in range(trace.layers):
        for hop in by_layer.get(layer,[]):
            location[hop.qubit]=hop.target
        if [location[q] for q in range(trace.qubits)] != partition.placement(layer).tolist():
            raise ValueError(f'trace and mapping disagree after layer {layer}')
    np.savez_compressed(folder/'mapping.npz', initial=partition.initial_assignment,
                        placements=partition.assignments, mesh=np.array([architecture['rows'],architecture['columns']]))
    with (folder/'mapping.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream);writer.writerow(['layer','qubit','core'])
        for layer, placement in [(-1,partition.initial_assignment), *enumerate(partition.assignments)]:
            writer.writerows((layer,qubit,int(core)) for qubit,core in enumerate(placement))
    dump_json(folder/'mapping_summary.json',dict(algorithm=result.placer,
        initial_placement=args.initial_placement, route_model=partition.route_model,
        mapping=result.as_record(), maximum_data_occupancy=validation.max_occupancy,
        data_capacity_enforced=architecture['data_slots_per_core'],
        seed_path=setup.seed.path, links=[dict(source=a,target=b,reliability=value)
                                         for (a,b),value in setup.architecture.link_reliabilities.items()]))
    return trace


def heatmap_svg(data, cores):
    rows=data['layers']; block=max(1,ceil_div(len(rows),400)); width=800
    bins=[rows[i:i+block] for i in range(0,len(rows),block)]
    height=24*cores+55; cell=width/max(1,len(bins))
    pieces=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 {height}" role="img" aria-label="Core-layer demand heatmap">',
            '<rect width="100%" height="100%" fill="#f8fafc"/>']
    peak=max(1,data['summary']['peak_core_layer_demand'])
    for core in range(cores):
        pieces.append(f'<text x="4" y="{core*24+19}" font-size="12">Core {core}</text>')
        for index,group in enumerate(bins):
            value=max(row[f'core_{core}_demand'] for row in group)
            light=96-62*value/peak
            color=f'hsl(12 78% {light:.1f}%)' if value>data['summary']['physical_memories_per_core'] else f'hsl(210 45% {light:.1f}%)'
            pieces.append(f'<rect x="{70+index*cell:.2f}" y="{core*24+3}" width="{cell+.1:.2f}" height="20" fill="{color}"><title>Core {core}; layers {group[0]["layer"]}–{group[-1]["layer"]}; peak {value}</title></rect>')
    pieces.append(f'<text x="70" y="{height-15}" font-size="12">Compiler layers 0–{max(0,len(rows)-1)}; max demand per {block}-layer bin; red exceeds physical bank</text></svg>')
    return ''.join(pieces)


def ceil_div(a,b):
    return (a+b-1)//b


STYLE='''body{font:16px/1.55 system-ui,sans-serif;max-width:1180px;margin:40px auto;padding:0 24px;color:#172c44;background:#f8fafc}h1,h2{line-height:1.2}h1{font-size:32px}table{border-collapse:collapse;width:100%;margin:20px 0;background:white}th,td{padding:10px 12px;border-bottom:1px solid #dbe3ec;text-align:left;font-variant-numeric:tabular-nums}th{background:#eaf0f7}a{color:#126ca4}code{background:#eaf0f7;padding:2px 5px}section{margin:28px 0}img{width:100%}.note{background:#e8f2fc;padding:16px;border-left:4px solid #277da8}.error{color:#a52a2a}'''


def table(headers, rows):
    return '<table><thead><tr>'+''.join(f'<th>{html.escape(str(h))}</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
        '<tr>'+''.join(f'<td>{html.escape(str(c))}</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'


def trial_report(folder, name, seed, architecture, data, plan, policy, physical):
    summary=data['summary'];mem=architecture['communication_slots_per_core'];comp=architecture['compiler_slots_per_core']
    sensitivity=[(c,s['overloaded_layers'],f"{s['overloaded_active_layer_percent']:.2f}%",s['excess_endpoint_demand'],s['affected_hops'])
                 for c,s in summary['capacity_sensitivity'].items()]
    top=sorted(data['cores'],key=lambda r:-r['incident_hops'])[:8]
    worst=sorted(data['layers'],key=lambda r:(-r['peak_core_demand'],-r['hop_requests']))[:10]
    hot=summary['capacity_sensitivity'][str(mem)]
    routing=(f"{hot['overloaded_layers']} overloaded layers; {hot['fixed_endpoint_overload_layers']} have endpoint demand alone over capacity, "
             f"and {hot['mandatory_shortest_path_overload_layers']} exceed capacity even using mandatory shortest-path incidences. "
             'These are lower-bound tests, not a proof that all other layers can be cleared.')
    body=f'''<h1>{html.escape(name)} · seed {seed}</h1><p><a href="../../report.html">Study overview</a></p>
<div class="note">{architecture['cores']} cores; {architecture['physical_qubits']} total physical slots; {architecture['data_slots_per_core']} data + {mem} communication slots per core; {architecture['initial_spare_data_slots_per_core']} initial spare data slots/core.
Policy: {policy}; compiler bank: {comp}; circuit width: {summary['logical_qubits']}.</div>
<h2>Workload and layer demand</h2><p>{summary['layers']:,} compiler layers, {summary['active_layers']:,} active layers and {summary['hop_requests']:,} adjacent-hop requests.
Peak demand: {summary['peak_core_layer_demand']}. Counts are whole-layer demand, not observed simultaneous occupancy.</p>
<img src="hotspots.svg" alt="Demand per core and compiler layer"/>
{table(['Capacity/core','Overloaded layers','% active layers','Excess endpoint demand','Affected hops'],sensitivity)}
<h2>Core hotspots</h2>{table(['Core','Incident hops','Peak layer demand',f'Layers > {mem}','Relay share'],[(r['core'],r['incident_hops'],r['peak_layer_demand'],r['overloaded_layers_at_physical_capacity'],f"{100*r['relay_fraction']:.1f}%") for r in top])}
<h2>Largest bursts</h2>{table(['Layer','Hop requests','Peak core demand','ACE batches','Dependency waves'],[(r['layer'],r['hop_requests'],r['peak_core_demand'],r['ace_batches'],r['same_qubit_dependency_waves']) for r in worst])}
<h2>Routing evidence</h2><p>{summary['chains_with_alternative_shortest_paths']:,} of {summary['hop_chains']:,} consecutive hop chains have alternative equal-hop shortest paths. {routing}</p>
<h2>Dynamic/fixed preparation plan</h2><p>Policy {policy}: {len(plan):,}/{summary['hop_requests']:,} requests admitted offline using {comp} compiler slots. This is planned admission, not physical readiness or a latency speedup.</p>
<h2>Scheduling and delay components</h2><p>Current ACE batching: {summary['total_ace_batches']:,} batches. Abstract capacity-{mem} packing: {summary['total_greedy_physical_capacity_waves']:,} waves; same-qubit dependency floor: {summary['total_same_qubit_dependency_waves']:,} waves.</p>
<p>At {summary['buffer_per_batch_ms']} ms/batch, the ACE buffer component is {summary['ace_buffer_component_ms']/1000:.3f} s. This is a configured component, not measured congestion delay. Constant-service estimates appear in CSV only when --hop-service-ms is set. Abstract multi-request waves require runtime concurrency support and do not model changing EPR readiness, fidelity or handoff memory.</p>'''
    if physical:
        body+='<h2>Measured physical ACE</h2>'+table(['Policy','Completion','Mean request ms','Makespan ms'],[(r['strategy'],r['completion_rate'],r['average_request_latency_ms'],r['end_to_end_latency_ms']) for r in physical])
    body+='<h2>Raw artifacts</h2><p>'+ ' · '.join(f'<a href="{file}">{file}</a>' for file in ['requests.txt','mapping.csv','mapping.npz','mapping_summary.json','summary.json','layers.csv','capacity_layers.csv','cores.csv','edges.csv','preparation_schedule.csv','manifest.json'])+'</p>'
    (folder/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Hotspot analysis</title><style>'+STYLE+'</style>'+body,encoding='utf-8')


def simulate(args, folder, seed):
    import os
    config=args.ace_config or args.ace_dir/'config/final_config/grid_4x4_ace_3.json'
    if args.mesh!='4x4' and args.ace_config is None:
        raise ValueError('--simulate on another mesh requires --ace-config matching that mesh')
    command=[sys.executable,'-B',str(args.ace_dir/'run_compiler_pregeneration.py'),
        '--trace',str(folder/'requests.txt'),'--config',str(config.resolve()),'--mesh',args.mesh,
        '--strategies',args.policy,'--seeds',str(seed),'--total-memories',str(args.memory_slots),
        '--compiler-memories',str(args.memory_slots-args.on_demand_reserve),
        '--generation-capacity',str(args.memory_slots-args.on_demand_reserve),
        '--delta-layers',str(args.delta_layers),'--dynamic-lookahead-layers',str(args.dynamic_lookahead_layers),
        '--coherence-time-layers',str(args.coherence_time_layers),'--pregeneration-buffer-ms',str(args.buffer_ms),
        '--stop-time-s',str(args.stop_time_s),'--output',str(folder/'physical')]
    env=dict(os.environ);env['PYTHONPATH']=str(args.sequence_dir.resolve())+os.pathsep+env.get('PYTHONPATH','')
    with (folder/'physical.log').open('w',encoding='utf-8') as stream:
        subprocess.run(command,cwd=args.ace_dir,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
    with (folder/'physical/summary.csv').open(encoding='utf-8') as stream:
        rows=list(csv.DictReader(stream))
    if not rows or any(float(row['completion_rate']) < 1 for row in rows):
        raise RuntimeError('physical ACE did not complete all requests; inspect physical/ and increase --stop-time-s')
    return rows


def overview(output, architecture, rows, errors):
    headers=['Workload','Seed','Qubits','Active layers','Hop requests','Overloaded layers','% active','Peak demand','Planned prep %']
    body='<h1>Multicore congestion study</h1>'+f'<p>{architecture["mesh"]} mesh · {architecture["physical_qubits"]} total physical slots · {architecture["communication_slots_per_core"]} communication slots/core · {architecture["data_capacity"]} data slots · {architecture["initial_workload_capacity"]} initial workload slots after migration headroom</p>'
    body+=table(headers,[(r['workload'],r['seed'],r['logical_qubits'],r['active_layers'],r['hop_requests'],r['overloaded_layers'],f"{r['overloaded_active_layer_percent']:.2f}%",r['peak_core_layer_demand'],f"{r['planned_preparation_percent']:.2f}%") for r in rows])
    body+='<p>Demand is counted at both endpoints of every hop. Overload uses the physical communication bank; compiler-bank sensitivity appears in each report. Delay components are analytical unless physical ACE was explicitly requested.</p>'
    body+='<h2>Per-workload reports</h2><ul>'+''.join(f'<li><a href="{r["report"]}">{html.escape(r["workload"])} · seed {r["seed"]}</a></li>' for r in rows)+'</ul>'
    if errors:
        body+='<h2 class="error">Failed inputs</h2>'+table(['Workload','Error'],[(r['workload'],r['error']) for r in errors])
    body+='<p>Raw overview: <a href="summary.csv">summary.csv</a> · <a href="study.json">study.json</a></p>'
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Congestion study</title><style>'+STYLE+'</style>'+body,encoding='utf-8')
    md=['# Multicore congestion study','',f"Architecture: {architecture['mesh']}, {architecture['physical_qubits']} physical slots, {architecture['communication_slots_per_core']} communication slots/core.",'',
        '| Workload | Seed | Active layers | Hops | Overloaded layers | % active | Peak demand |',
        '|---|---:|---:|---:|---:|---:|---:|']
    md += [f"| {r['workload']} | {r['seed']} | {r['active_layers']} | {r['hop_requests']} | {r['overloaded_layers']} | {r['overloaded_active_layer_percent']:.2f}% | {r['peak_core_layer_demand']} |" for r in rows]
    md+=['','Overload uses the physical communication bank. Layer demand is not simultaneous occupancy. Scheduling estimates are not measured physical latency.','',
         *[f"- [{r['workload']} seed {r['seed']}]({r['report']})" for r in rows]]
    if errors:md+=['','## Failed inputs','',*[f"- {r['workload']}: {r['error']}" for r in errors]]
    (output/'report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')


def main(argv=None):
    p=parser();args=p.parse_args(argv)
    try:
        architecture=configure(args)
        if args.mapper_dir:
            mapper_dir=args.mapper_dir.resolve()
            if not (mapper_dir/'qmap').is_dir():raise ValueError('--mapper-dir must contain qmap/')
            sys.path.insert(0,str(mapper_dir))
        else:
            # Detect the previously supplied local checkout, then fall back to an installed qmap.
            mapper_dir=None
            for parent in Path(__file__).resolve().parents:
                candidate=parent/'tracegen'
                if (candidate/'qmap').is_dir():
                    mapper_dir=candidate;sys.path.insert(0,str(candidate));break
        import qmap
        mapper_dir=mapper_dir or Path(qmap.__file__).resolve().parent.parent
        if args.bench_dir:
            if not (args.bench_dir/'src/mqt/bench').is_dir():
                raise ValueError('--bench-dir must contain src/mqt/bench/')
            sys.path.insert(0,str(args.bench_dir.resolve()/'src'))
        if args.simulate and (not args.ace_dir or not args.sequence_dir):
            raise ValueError('--simulate requires --ace-dir and --sequence-dir')
        options=json.loads(args.workload_options.read_text()) if args.workload_options else {}
        if not isinstance(options,dict):raise ValueError('--workload-options must contain a JSON object')
    except (ValueError,ImportError,OSError) as exc:
        p.error(f'{exc}. See tools/congestion_study/README.md for dependencies.')
    workloads=args.workloads if args.workloads is not None else ([] if args.qasm else DEFAULT_WORKLOADS)
    inputs=[(name,None) for group in workloads for name in group.split(',')]
    try:
        inputs += [(path.stem+'_'+digest(path)[:8],path) for path in args.qasm]
    except OSError as exc:
        p.error(str(exc))
    if len({name for name,_ in inputs}) != len(inputs):
        p.error('duplicate workload names; use --seeds for repeated trials')
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    successful,errors=[],[]
    started=datetime.now(timezone.utc).isoformat()
    provenance=dict(started_at=started,architecture=architecture,policy=args.policy,parameters=vars(args),
                    versions=versions(),mapper_dir=str(mapper_dir),mapper_git_commit=git_commit(mapper_dir),
                    bench_git_commit=git_commit(args.bench_dir) if args.bench_dir else None,
                    mapper_source_sha256={str(path.relative_to(mapper_dir)):digest(path) for path in sorted((mapper_dir/'qmap').rglob('*.py'))},
                    pipeline_source_sha256={path.name:digest(path) for path in Path(__file__).parent.glob('*.py')},
                    benchmark_reference=BENCH_URL)
    for name,qasm_path in inputs:
        try:
            print(f'Generating {name} ({architecture["requested_circuit_qubits"]} requested qubits)...',flush=True)
            circuit,ir,source=load_circuit(name,qasm_path,architecture['requested_circuit_qubits'],args,options)
            if ir.n_qubits>architecture['data_capacity']:
                raise ValueError(f'actual circuit width {ir.n_qubits} exceeds {architecture["data_capacity"]} data slots')
        except Exception as exc:
            errors.append(dict(workload=name,error=f'{type(exc).__name__}: {exc}'));continue
        for seed in architecture['seeds']:
            label=re.sub(r'[^A-Za-z0-9_-]','_',name)
            folder=args.output/label/f'seed_{seed}';folder.mkdir(parents=True,exist_ok=True)
            begin=time.perf_counter()
            try:
                dump_json(folder/'manifest.json',dict(status='running',workload=name,seed=seed,source=source))
                from qiskit import qasm2
                (folder/'circuit.qasm').write_text(qasm2.dumps(circuit),encoding='utf-8')
                print(f'  Mapping {name}, seed {seed}, {len(circuit.data):,} normalized gates...',flush=True)
                trace=map_and_export(ir,architecture,seed,args,folder)
                data=characterize(trace,architecture['rows'],architecture['columns'],args.memory_slots,
                                  architecture['compiler_slots_per_core'],args.buffer_ms,args.hop_service_ms)
                plan=preparation_plan(trace,args.policy,architecture['compiler_slots_per_core'],
                                      args.dynamic_lookahead_layers,args.coherence_time_layers,args.delta_layers)
                summary=data['summary'];summary.update(policy=args.policy,planned_preparations=len(plan),
                    planned_preparation_percent=100*len(plan)/len(trace.hops) if trace.hops else 0,
                    physical_qubit_budget=architecture['physical_qubits'],trace_sha256=digest(folder/'requests.txt'))
                dump_json(folder/'summary.json',summary)
                for key,file in [('layers','layers.csv'),('capacities','capacity_layers.csv'),('cores','cores.csv'),('edges','edges.csv')]:
                    dump_csv(folder/file,data[key],fields=['source','target','hop_requests','active_layers','peak_layer_hops'] if key=='edges' else None)
                dump_csv(folder/'preparation_schedule.csv',plan,fields=['request_id','generation_layer','target_layer','source','target','lead_layers'])
                (folder/'hotspots.svg').write_text(heatmap_svg(data,trace.cores),encoding='utf-8')
                physical=simulate(args,folder,seed) if args.simulate else []
                trial_report(folder,name,seed,architecture,data,plan,args.policy,physical)
                hot=summary['capacity_sensitivity'][str(args.memory_slots)]
                row=dict(workload=name,seed=seed,policy=args.policy,logical_qubits=trace.qubits,
                         layers=trace.layers,active_layers=summary['active_layers'],hop_requests=len(trace.hops),
                         overloaded_layers=hot['overloaded_layers'],overloaded_active_layer_percent=hot['overloaded_active_layer_percent'],
                         overloaded_core_layers=hot['overloaded_core_layers'],excess_endpoint_demand=hot['excess_endpoint_demand'],
                         affected_hops=hot['affected_hops'],peak_core_layer_demand=summary['peak_core_layer_demand'],
                         planned_preparation_percent=summary['planned_preparation_percent'],
                         chains_with_alternative_shortest_paths=summary['chains_with_alternative_shortest_paths'],
                         total_ace_batches=summary['total_ace_batches'],
                         total_greedy_physical_capacity_waves=summary['total_greedy_physical_capacity_waves'],
                         physical_completion_rate=physical[0]['completion_rate'] if physical else None,
                         physical_request_latency_ms=physical[0]['average_request_latency_ms'] if physical else None,
                         physical_makespan_ms=physical[0]['end_to_end_latency_ms'] if physical else None,
                         report=str((folder/'report.html').relative_to(args.output)).replace('\\','/'))
                successful.append(row)
                dump_json(folder/'manifest.json',dict(status='complete',workload=name,seed=seed,source=source,
                    architecture=architecture,policy=args.policy,seconds=time.perf_counter()-begin,
                    versions=provenance['versions'],trace_sha256=summary['trace_sha256'],
                    normalized_circuit_sha256=digest(folder/'circuit.qasm'),physical=physical))
                print(f'  {len(trace.hops):,} hops; {hot["overloaded_layers"]}/{summary["active_layers"]} active layers over {args.memory_slots}; report {folder/"report.html"}',flush=True)
            except Exception as exc:
                error=dict(workload=name,seed=seed,error=f'{type(exc).__name__}: {exc}')
                errors.append(error);dump_json(folder/'manifest.json',dict(status='failed',**error))
                print(f'  FAILED: {error["error"]}',file=sys.stderr,flush=True)
            dump_json(args.output/'study.json',dict(**provenance,status='running',trials=successful,errors=errors))
    dump_csv(args.output/'summary.csv',successful,fields=list(successful[0]) if successful else ['workload','seed'])
    overview(args.output,architecture,successful,errors)
    dump_json(args.output/'study.json',dict(**provenance,status='complete' if not errors else 'partial_failure',
              finished_at=datetime.now(timezone.utc).isoformat(),trials=successful,errors=errors))
    print(f'Report: {args.output/"report.html"}',flush=True)
    for error in errors:print(f'FAILED {error["workload"]}: {error["error"]}',file=sys.stderr)
    return 1 if errors else 0


if __name__=='__main__':
    raise SystemExit(main())
