"""Reproducible fixed-placement routing comparison; build, simulate, or plot."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import offline_routing as ro

ROOT = Path(__file__).resolve().parents[2]
WORKLOADS = ('qft', 'draper_qft_adder', 'qaoa')
ALGORITHMS = ('xy', 'yx', 'greedy', 'history', 'minexcess', 'minhop', 'detour2')
ADJ = ro.adjacency('mesh')

def migration_latencies(chains, parts):
    """Sequential hop intervals telescope from layer activation to migration end.

    Per-qubit total_time_ms starts at eligibility, before admission. The separate
    admission_wait_time_ms field describes a subinterval, not additional time.
    """
    return [sum(float(parts[r]['total_time_ms']) for r in ids) for ids in chains.values()]

def write_csv(path, rows):
    with path.open('w', newline='') as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def choose(records, algorithm, history):
    original = [tuple(r['path']) for r in records]
    if algorithm in ('xy', 'yx'):
        paths = []
        for r in records:
            a, b = r['source_core'], r['destination_core']; p = [a]
            for dimension in ((0, 1) if algorithm == 'xy' else (1, 0)):
                while divmod(a, 4)[dimension] != divmod(b, 4)[dimension]:
                    step = 4 if dimension == 0 else 1
                    a += step if divmod(a, 4)[dimension] < divmod(b, 4)[dimension] else -step
                    p.append(a)
            paths.append(tuple(p))
        return paths, True
    shortest = [ro.simple_paths(ADJ, p[0], p[-1], ro.shortest_length(ADJ, p[0], p[-1])) for p in original]
    if algorithm in ('minexcess', 'minhop', 'detour2'):
        # Start from shortest XY, so the historical-path fallback cannot admit long detours.
        base, _ = choose(records, 'xy', history)
        result = ro.optimize_layer(base, 4, 'hop' if algorithm=='minhop' else 'route', ADJ, 2 if algorithm == 'detour2' else 0, 2)
        return result.paths, result.optimal
    load = Counter(); selected = [None] * len(records)
    # Hardest routes first; stable tie breaking makes repeated runs reproducible.
    for i in sorted(range(len(records)), key=lambda i: (-len(original[i]), i)):
        def score(p):
            return (sum(max(0, load[c]+1-4)-max(0, load[c]-4) for c in p),
                    sum(2*load[c]+1 for c in p) + (0.1*sum(history[c] for c in p) if algorithm == 'history' else 0), p)
        selected[i] = min(shortest[i], key=score)
        load.update(selected[i])
    return selected, True

def build(out, inputs=None, algorithms=ALGORITHMS):
    rows = []; manifests = []
    if inputs is not None: inputs=inputs.resolve()
    for workload in WORKLOADS:
        for seed in ((42,) if inputs else (42,43,44)):
            source = inputs/workload/f'seed_{seed}' if inputs else ROOT / f'results/golden_study_2026-10-25/traces/placements/mesh/T-HQA/{workload}/seed_{seed}/routes/xy'
            trace = ro.read_trace(source/'requests.txt',4,4)
            expected = None
            if inputs:
                mapping = np.load(source/'mapping.npz'); expected = mapping['placements']
                before = mapping['initial']; records=[]
                assert len(expected)==trace.layers
                for layer, after in enumerate(expected):
                    for q in np.flatnonzero(before!=after):
                        a,b=int(before[q]),int(after[q])
                        records.append(dict(layer=layer,qubit=int(q),source_core=a,destination_core=b,
                                            path=ro.simple_paths(ADJ,a,b,ro.shortest_length(ADJ,a,b))[0]))
                    before=after
            else:
                records = [json.loads(s) for s in (source/'migrations.jsonl').read_text().splitlines()]
            groups = defaultdict(list)
            for r in records: groups[r['layer']].append(r)
            manifests.append(dict(workload=workload, mapping_seed=seed, qubits=trace.qubits, layers=trace.layers,
                               migrations=len(records), source=str(source.relative_to(ROOT)),
                               sha256=hashlib.sha256((source/'requests.txt').read_bytes()).hexdigest()))
            for algorithm in algorithms:
                start=time.perf_counter(); routes={}; qs={}; history=Counter(); unproved=0
                core=np.zeros((trace.layers,16)); link=Counter(); endpoint_bound=0
                for layer, rs in sorted(groups.items()):
                    paths, optimal = choose(rs, algorithm, history); unproved += not optimal
                    for r,p in zip(rs,paths):
                        assert p[0]==r['source_core'] and p[-1]==r['destination_core']
                        assert len(set(p))==len(p) and all(b in ADJ[a] for a,b in zip(p,p[1:]))
                        assert len(p)-1 <= ro.shortest_length(ADJ,p[0],p[-1])+(2 if algorithm=='detour2' else 0)
                        for c in p: core[layer,c]+=1
                        link.update(tuple(sorted((a,b))) for a,b in zip(p,p[1:]))
                    history.update(c for p in paths for c in p)
                    endpoint_bound += ro.lower_bound(paths,4,'route')
                    routes[layer]=paths; qs[layer]=[r['qubit'] for r in rs]
                dest=out/'traces'/workload/f'seed_{seed}'/algorithm
                ro.write_trace(trace,routes,qs,dest/'requests.txt')
                check=ro.read_trace(dest/'requests.txt',4,4)
                assert check.initial==trace.initial and check.layers==trace.layers and check.qubits==trace.qubits
                # Replay each layer to prove identical placement transitions, including empty layers.
                position=dict(trace.initial)
                for layer in range(trace.layers):
                    for r,p in zip(groups.get(layer,[]),routes.get(layer,[])):
                        assert position[r['qubit']]==p[0]; position[r['qubit']]=p[-1]
                    if expected is not None:
                        assert [position[q] for q in range(trace.qubits)]==expected[layer].tolist()
                np.save(dest/'core_demand.npy',core)
                (dest/'links.json').write_text(json.dumps({f'{a}-{b}':v for (a,b),v in link.items()}))
                active=core.sum(axis=1)>0
                rows.append(dict(workload=workload,mapping_seed=seed,algorithm=algorithm,qubits=trace.qubits,
                                 layers=trace.layers,active_layers=int(active.sum()),migrations=len(records),hops=len(check.hops),
                                 excess=float(np.maximum(core-4,0).sum()),endpoint_lower_bound=endpoint_bound,
                                 overloaded_core_layers=int((core>4).sum()),peak_demand=float(core.max()),
                                 peak_link_hops=max(link.values(),default=0),unproved_layers=unproved,
                                 routing_seconds=time.perf_counter()-start))
                print(workload,seed,algorithm,rows[-1]['hops'],rows[-1]['excess'],flush=True)
    if (out/'structural.csv').exists():
        previous=list(csv.DictReader((out/'structural.csv').open()))
        rows=[r for r in previous if r['algorithm'] not in algorithms]+rows
    write_csv(out/'structural.csv',rows); (out/'inputs.json').write_text(json.dumps(manifests,indent=2))

def simulate(out, seeds, algorithms=ALGORITHMS, workloads=WORKLOADS, simulation_dir='simulation', consumption='handoff'):
    # Archived seeds 42/43/44 have identical trace hashes: do not count duplicates as replicates.
    jobs=[p for p in (out/'traces').glob('*/seed_42/*/requests.txt')
          if p.parent.name in algorithms and p.parent.parent.parent.name in workloads]
    def run(trace):
        rel=trace.parent.relative_to(out/'traces'); dest=out/simulation_dir/rel
        if (dest/'summary.csv').exists():
            metadata=json.loads((dest/'metadata.json').read_text())
            actual=metadata['parameters']['compiler_pair_consumption']
            if actual!=consumption or metadata['seeds']!=[int(s) for s in seeds.split(',')]:
                raise ValueError(f'{dest}: completed results use different consumption/seeds; choose a fresh output folder')
            return
        dest.mkdir(parents=True,exist_ok=True)
        cmd=[sys.executable,'-B','run_trace_comparison.py','--trace',str(trace.resolve()),'--config','config/final_config/grid_4x4_ace_3.json',
             '--strategies','on-demand,dynamic','--seeds',seeds,'--total-memories','4','--compiler-memories','4','--generation-capacity','4',
             '--planner-lead-layers','2','--scheduler','per-qubit','--admission','event','--admission-priority','ready-first',
             '--all-chain-hops','--no-congestion-threshold','--pregeneration-buffer-ms','0','--stop-after-workload','--audit-events',
             '--compiler-pair-consumption',consumption,'--output',str(dest.resolve())]
        (dest/'command.json').write_text(json.dumps(cmd))
        with (dest/'run.log').open('w') as f: subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
        print('completed',str(rel),flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(run,p) for p in jobs]): f.result()
    rows=[]
    for trace in jobs:
        workload, mapping, algorithm=trace.parent.relative_to(out/'traces').parts
        with (out/simulation_dir/workload/mapping/algorithm/'summary.csv').open() as f:
            rows.extend(dict(workload=workload,mapping_seed=mapping[5:],algorithm=algorithm,**r) for r in csv.DictReader(f))
    write_csv(out/('runtime.csv' if simulation_dir=='simulation' else f'{simulation_dir}_runtime.csv'),rows)

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('stage',choices=['build','simulate']); p.add_argument('--output',type=Path,required=True); p.add_argument('--inputs',type=Path); p.add_argument('--seeds',default='60,61,62,63');p.add_argument('--algorithms',nargs='+',choices=ALGORITHMS,default=ALGORITHMS)
    p.add_argument('--workloads',nargs='+',choices=WORKLOADS,default=WORKLOADS);p.add_argument('--simulation-dir',choices=['simulation','validation'],default='simulation')
    p.add_argument('--compiler-pair-consumption',choices=['swap','handoff'],default='handoff')
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    build(a.output,a.inputs,a.algorithms) if a.stage=='build' else simulate(a.output,a.seeds,a.algorithms,a.workloads,a.simulation_dir,a.compiler_pair_consumption)
if __name__=='__main__': main()
