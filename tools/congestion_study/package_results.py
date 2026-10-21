"""Audit, aggregate and ZIP an existing congestion study without simulation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import shutil
from statistics import fmean, stdev
import zipfile

if __package__:
    from .hotspot_analysis import read_trace
    from .run_study import STYLE, dump_csv, dump_json, table
else:
    from hotspot_analysis import read_trace
    from run_study import STYLE, dump_csv, dump_json, table


PATTERNS = {
    'bmw_quark_cardinality': 'BMW/QUARK cardinality: repeated nearest-neighbor RXX layers',
    'qft': 'Fourier transform: structured long-range interactions',
    'draper_qft_adder': 'Draper arithmetic: Fourier-based structured interactions',
    'bv': 'Bernstein–Vazirani: shared flag/oracle interactions',
    'qaoa': 'QAOA Max-Cut: repeated dense graph interactions',
    'ghz': 'GHZ: sequential nearest-neighbor state preparation',
    'cdkm_ripple_carry_adder': 'CDKM/Cuccaro: carry-dependent ripple arithmetic',
    'vqe_real_amp': 'VQE Real-Amplitudes: repeated reverse-linear entangling ansatz',
    'graphstate': 'Graph state: sparse degree-2 random regular graph',
    'randomcircuit': 'Random: heterogeneous 1–4-qubit operations decomposed to the common basis',
}


def read_csv(path):
    with path.open(encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_trial(folder, row, architecture):
    manifest=json.loads((folder/'manifest.json').read_text())
    summary=json.loads((folder/'summary.json').read_text())
    assert manifest['status']=='complete'
    assert sha256(folder/'requests.txt')==manifest['trace_sha256']
    assert sha256(folder/'circuit.qasm')==manifest['normalized_circuit_sha256']
    trace=read_trace(folder/'requests.txt',architecture['rows'],architecture['columns'])
    assert trace.slots==architecture['physical_slots_per_core']
    assert trace.qubits==row['logical_qubits']
    assert len(trace.hops)==row['hop_requests']
    by_layer=defaultdict(list)
    for hop in trace.hops:by_layer[hop.layer].append(hop)
    location=dict(trace.initial)
    with (folder/'mapping.csv').open(encoding='utf-8',newline='') as stream:
        groups=itertools.groupby(csv.DictReader(stream),key=lambda r:int(r['layer']))
        seen=[]
        for layer,placements in groups:
            seen.append(layer)
            if layer>=0:
                for hop in by_layer[layer]:location[hop.qubit]=hop.target
            actual={int(r['qubit']):int(r['core']) for r in placements}
            assert actual==location, f'mapping/trace mismatch: {folder}, layer {layer}'
            assert max(Counter(actual.values()).values())<=architecture['data_slots_per_core']
        assert seen==list(range(-1,trace.layers))
    layers=read_csv(folder/'layers.csv'); cores=read_csv(folder/'cores.csv');edges=read_csv(folder/'edges.csv')
    assert len(layers)==trace.layers and len(cores)==trace.cores
    assert sum(int(r['hop_requests']) for r in layers)==len(trace.hops)
    assert sum(int(r['incident_hops']) for r in cores)==2*len(trace.hops)
    assert sum(int(r['hop_requests']) for r in edges)==len(trace.hops)
    memory=architecture['communication_slots_per_core']
    assert sum(int(r['peak_core_demand'])>memory for r in layers)==row['overloaded_layers']
    for core in range(trace.cores):
        values=[int(r[f'core_{core}_demand']) for r in layers]
        actual=next(r for r in cores if int(r['core'])==core)
        assert sum(values)==int(actual['incident_hops'])
        assert max(values,default=0)==int(actual['peak_layer_demand'])
    plan=read_csv(folder/'preparation_schedule.csv')
    assert len(plan)==summary['planned_preparations']
    assert len({r['request_id'] for r in plan})==len(plan)
    return layers,cores,edges,summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study_dir',type=Path)
    parser.add_argument('--zip',dest='zip_path',type=Path)
    args=parser.parse_args(argv)
    root=args.study_dir.resolve();study=json.loads((root/'study.json').read_text())
    if study['status']!='complete' or study['errors']:
        parser.error('refusing to package a partial/failed study as complete')
    architecture=study['architecture'];trials=study['trials']
    zip_path=(args.zip_path or root.with_suffix('.zip')).resolve()
    if root==zip_path or root in zip_path.parents:
        parser.error('ZIP output must be outside the study directory')
    grouped=defaultdict(list);combined={'layers':[],'cores':[],'edges':[]};summaries={}
    for row in trials:
        folder=root/Path(row['report']).parent
        layers,cores,edges,summary=audit_trial(folder,row,architecture)
        key=(row['workload'],row['seed']);summaries[key]=summary
        grouped[row['workload']].append(row)
        for kind,values in [('layers',layers),('cores',cores),('edges',edges)]:
            combined[kind].extend(dict(workload=row['workload'],seed=row['seed'],**value) for value in values)
    aggregate=[];aggregate_cores=[]
    for name,rows in grouped.items():
        seeds=[r['seed'] for r in rows]
        manifests=[json.loads((root/Path(r['report']).parent/'manifest.json').read_text()) for r in rows]
        assert len({m['normalized_circuit_sha256'] for m in manifests})==1, 'circuit changed between mapping seeds'
        rates=[r['overloaded_active_layer_percent'] for r in rows]
        aggregate.append(dict(workload=name,pattern=PATTERNS.get(name,'user workload'),
            mapping_seeds=';'.join(map(str,seeds)),trials=len(rows),logical_qubits=rows[0]['logical_qubits'],
            mean_active_layers=fmean(r['active_layers'] for r in rows),
            mean_hop_requests=fmean(r['hop_requests'] for r in rows),
            mean_overloaded_layers=fmean(r['overloaded_layers'] for r in rows),
            min_overloaded_layers=min(r['overloaded_layers'] for r in rows),
            max_overloaded_layers=max(r['overloaded_layers'] for r in rows),
            mean_overloaded_active_layer_percent=fmean(rates),
            sd_overloaded_active_layer_percent=stdev(rates) if len(rates)>1 else 0,
            peak_core_layer_demand=max(r['peak_core_layer_demand'] for r in rows),
            mean_planned_preparation_percent=fmean(r['planned_preparation_percent'] for r in rows),
            mean_excess_endpoint_demand=fmean(r['excess_endpoint_demand'] for r in rows)))
        for core in range(architecture['cores']):
            values=[r for r in combined['cores'] if r['workload']==name and int(r['core'])==core]
            counts=[int(r['incident_hops']) for r in values]
            aggregate_cores.append(dict(workload=name,core=core,row=core//architecture['columns'],
                column=core%architecture['columns'],mapping_seeds=';'.join(map(str,seeds)),
                mean_incident_hops=fmean(counts),sd_incident_hops=stdev(counts) if len(counts)>1 else 0,
                maximum_peak_layer_demand=max(int(r['peak_layer_demand']) for r in values),
                mean_overloaded_layers_at_physical_capacity=fmean(int(r['overloaded_layers_at_physical_capacity']) for r in values),
                mean_overloaded_layers_at_compiler_capacity=fmean(int(r['overloaded_layers_at_compiler_capacity']) for r in values),
                mean_internal_relay_incidences=fmean(int(r['internal_relay_incidences']) for r in values)))
    dump_csv(root/'aggregate_workloads.csv',aggregate)
    dump_csv(root/'aggregate_core_hotspots.csv',aggregate_cores)
    for kind,rows in combined.items():dump_csv(root/f'all_trials_{kind}.csv',rows)
    ordered=sorted(aggregate,key=lambda r:-r['mean_overloaded_active_layer_percent'])
    headers=['Workload','Pattern','Active layers','Hops','Overloaded layers (range)','Mean % active','Peak/core']
    values=[(r['workload'],r['pattern'],f"{r['mean_active_layers']:.0f}",f"{r['mean_hop_requests']:.0f}",
             f"{r['min_overloaded_layers']}–{r['max_overloaded_layers']}",f"{r['mean_overloaded_active_layer_percent']:.2f}%",r['peak_core_layer_demand']) for r in ordered]
    body=f'''<h1>Ten-workload congestion and hotspot study</h1>
<p>{len(grouped)} workloads × {len(architecture['seeds'])} mapping/hardware seeds = {len(trials)} validated analyses. No physical simulation was run.</p>
<div class="note">{architecture['mesh']} mesh, {architecture['physical_qubits']} total physical qubits, {architecture['communication_slots_per_core']} communication memories/core, {architecture['requested_circuit_qubits']} logical circuit qubits. Per core: 3 initially occupied data + 1 spare data + 4 communication slots. Dynamic preparation uses three compiler slots and one fallback slot.</div>
<h2>Cross-workload comparison</h2>{table(headers,values)}
<p>Overload means incident hop demand in a compiler layer exceeds four at any core. Percentages average seeds 42, 43 and 44. Circuit seed is fixed at 42; these are mapping/hardware variations of the same circuit, not independently generated circuits. BMW means BMW/QUARK cardinality; Draper means the fixed Draper QFT adder.</p>
<h2>Interpretation</h2><p>QAOA, QFT and Draper exhibit repeated overload and are useful routing candidates in this setup. Graph state has concentrated bursts in few active layers. Sparse/state-preparation, oracle and carry-dependent workloads provide contrasting controls; absence of overload is a valid result.</p>
<p>These are structural demand statistics. They do not prove simultaneous memory saturation or measured rerouting speedup. ACE batch/buffer estimates and planned preparation percentages are labeled separately from physical latency. Route choices must preserve same-qubit dependencies and should be evaluated against added hops and reliability.</p>
<h2>Open the evidence</h2><ul><li><a href="report.html">All workload/seed reports and heatmaps</a></li><li><a href="aggregate_workloads.csv">Cross-workload aggregate CSV</a></li><li><a href="aggregate_core_hotspots.csv">Per-workload, per-core aggregates</a></li><li><a href="all_trials_cores.csv">Every core in every trial</a></li><li><a href="all_trials_layers.csv">Every layer, including every core's demand</a></li><li><a href="all_trials_edges.csv">Every used link in every trial</a></li><li><a href="README.md">Archive contents and reproduction</a></li><li><a href="validation.json">Validation results</a></li></ul>'''
    (root/'START_HERE.html').write_text('<!doctype html><meta charset="utf-8"><title>Ten-workload hotspot study</title><style>'+STYLE+'</style>'+body,encoding='utf-8')
    pipeline=root/'pipeline';pipeline.mkdir(exist_ok=True)
    for source in Path(__file__).parent.iterdir():
        if source.is_file() and source.suffix in {'.py','.txt','.md'}:
            shutil.copy2(source,pipeline/source.name)
    source_root=Path(study['mapper_dir'])
    for relative,expected in study['mapper_source_sha256'].items():
        source=source_root/relative
        assert sha256(source)==expected, f'mapper changed since study: {relative}'
        destination=root/'mapper_source'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    for name in ['README.md','pyproject.toml','requirements.txt']:
        if (source_root/name).is_file():shutil.copy2(source_root/name,root/'mapper_source'/name)
    (root/'README.md').write_text('''# Ten-workload congestion study

Open **START_HERE.html** after extracting this ZIP. All links and images are local.

## Architecture and scope

- 4x4 mesh, 128 TOTAL physical slots, four communication memories/core.
- Per core: three initially occupied data slots, one spare data slot, four communication slots.
- 48 logical circuit qubits; dynamic preparation, three compiler slots plus one fallback/adoption slot.
- HQA qubit mapping, OEE initial placement, mapper reliability range [0.1, 1.0].
- Mapping/hardware seeds 42, 43, 44; fixed circuit seed 42.
- No physical ACE simulation. Timing outputs are abstract batch/buffer components, not measured congestion delay.
- MQT randomcircuit keeps its upstream internal generator seed 10; the circuit is identical across mapping seeds.

## Workloads

BMW is bmw_quark_cardinality, not the separate BMW copula benchmark. Draper is draper_qft_adder. The complete ten-workload list is in study.json and aggregate_workloads.csv. Five controls/contrasts add GHZ, CDKM/Cuccaro, Real-Amplitudes VQE, graph state and random circuits.

## Underlying data

Every workload/seed folder preserves the normalized circuit, initial and per-layer qubit mapping, validated hop trace, per-core/per-layer/per-link CSVs, dynamic preparation schedule, hotspot heatmap, report and provenance manifest. No raw trial artifacts were removed for packaging.

- aggregate_workloads.csv: mean, range and sample SD across mapping seeds.
- aggregate_core_hotspots.csv: each workload/core aggregated across seeds.
- all_trials_cores.csv: one row per workload/seed/core.
- all_trials_layers.csv: one row per workload/seed/layer, including demand at every core.
- all_trials_edges.csv: per-link traffic, active layers and peak layer demand.
- study.json: exact command settings, versions, pipeline/mapper source hashes and available Git commit IDs.
- SHA256SUMS.csv: checksums for all packaged files except the checksum list itself.
- validation.json: mapping/trace/capacity/accounting audit.

## Reproduce after extracting

Python 3.11+:

```powershell
python -m pip install -r pipeline/requirements.txt
python pipeline/run_study.py --mapper-dir mapper_source --workloads bmw_quark_cardinality qft draper_qft_adder bv qaoa ghz cdkm_ripple_carry_adder vqe_real_amp graphstate randomcircuit --seeds 42 43 44 --circuit-seed 42 --output rerun
```

The supplied mapper's Python source snapshot is included under mapper_source/qmap. MQT Bench is installed as a dependency; the versions and actual circuit/factory hashes used are recorded. These files retain their original copyright/license notices. Consult pipeline/README.md for configuration and optional physical simulation.
''',encoding='utf-8')
    dump_json(root/'validation.json',dict(status='passed',audited_at=datetime.now(timezone.utc).isoformat(),
        workloads=len(grouped),trials=len(trials),per_core_rows=len(combined['cores']),
        per_layer_rows=len(combined['layers']),per_link_rows=len(combined['edges']),
        checks=['all trials complete','circuit/trace hashes','circuit fixed across mapping seeds',
                'complete initial placement','adjacent hops and evolving qubit locations',
                'per-layer mapping agrees with trace','data-only capacity respected',
                'per-core/layer/link demand totals conserved','overload counts agree with underlying rows',
                'preparation request IDs unique','mapper source snapshot matches study hashes']))
    files=[path for path in sorted(root.rglob('*')) if path.is_file() and path.name!='SHA256SUMS.csv']
    dump_csv(root/'SHA256SUMS.csv',[dict(path=str(path.relative_to(root)).replace('\\','/'),bytes=path.stat().st_size,
                                      sha256=sha256(path)) for path in files])
    zip_path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():archive.write(path,Path(root.name)/path.relative_to(root))
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(files)+1
    print(json.dumps(dict(zip=str(zip_path),bytes=zip_path.stat().st_size,workloads=len(grouped),
                          trials=len(trials),core_rows=len(combined['cores']),layer_rows=len(combined['layers'])),indent=2))
    for row in ordered:print(row['workload'],f"{row['mean_overloaded_active_layer_percent']:.2f}%",
                              f"({row['min_overloaded_layers']}–{row['max_overloaded_layers']} layers)")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
