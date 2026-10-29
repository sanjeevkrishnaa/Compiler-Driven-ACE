"""Plot shared-scale routing heatmaps and aggregate physical evidence."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from heavy_routing import ALGORITHMS, WORKLOADS, ro, write_csv, migration_latencies

def grid(out, arrays, name, title, units, cmap='magma'):
    fig, axes=plt.subplots(3,len(ALGORITHMS),figsize=(20,9),layout='constrained')
    vmax=max(float(a.max()) for a in arrays.values()) or 1
    for i,w in enumerate(WORKLOADS):
        for j,a in enumerate(ALGORITHMS):
            ax=axes[i,j]; values=arrays[w,a].reshape(4,4)
            im=ax.imshow(values,vmin=0,vmax=vmax,cmap=cmap)
            for r in range(4):
                for c in range(4):
                    v=values[r,c]; label=f'{v:.2f}' if 'wait' in name else f'{v:.1f}'
                    ax.text(c,r,label,ha='center',va='center',fontsize=8,color='white' if v<vmax*.6 else 'black')
            ax.set_xticks([]);ax.set_yticks([])
            if i==0: ax.set_title(a)
            if j==0: ax.set_ylabel(w.replace('draper_qft_adder','Draper'),fontsize=11)
    fig.suptitle(title+'\n96 qubits · fixed T-HQA placement · 4×4 mesh · four communication memories/core',fontsize=14)
    fig.colorbar(im,ax=axes.ravel().tolist(),label=units,shrink=.8)
    fig.savefig(out/f'{name}.png',dpi=170);fig.savefig(out/f'{name}.pdf');plt.close(fig)

def report(out):
    figures=out/'figures';figures.mkdir(exist_ok=True)
    structural=list(csv.DictReader((out/'structural.csv').open()))
    demand={};traffic={}; temporal={};prefetch={}
    for w in WORKLOADS:
        for a in ALGORITHMS:
            folder=out/'traces'/w/'seed_42'/a
            core=np.load(folder/'core_demand.npy'); active=core.sum(axis=1)>0
            demand[w,a]=100*(core[active]>4).mean(axis=0)
            traffic[w,a]=core.sum(axis=0);temporal[w,a]=core
            trace=ro.read_trace(folder/'requests.txt',4,4)
            reconstructed=np.zeros_like(core)
            for layer,paths in ro.layer_routes(trace).items():
                for path in paths:
                    for c in path: reconstructed[layer,c]+=1
            assert np.array_equal(core,reconstructed)
            hop_core=np.zeros_like(core)
            for h in trace.hops:
                hop_core[h.layer,h.source]+=1;hop_core[h.layer,h.target]+=1
            prefetch[w,a]=100*(hop_core[active]>4).mean(axis=0)
            r=next(r for r in structural if r['workload']==w and r['algorithm']==a)
            r.update(hop_incidence_excess=float(np.maximum(hop_core-4,0).sum()),
                     hop_incidence_overloaded_core_layers=int((hop_core>4).sum()),hop_incidence_peak=float(hop_core.max()))
    write_csv(out/'structural.csv',structural)
    grid(figures,demand,'core_overload','Compile-time congestion: routes touching a core exceed C=4','% of communication-active layers')
    grid(figures,prefetch,'hop_incidence_overload','Compile-time hop incidence: incoming + outgoing demand exceeds C=4','% of communication-active layers')
    grid(figures,traffic,'core_traffic','Total routed core visits (endpoints and relays)','route visits')
    links={}
    for w in WORKLOADS:
        for a in ALGORITHMS:
            links[w,a]=json.loads((out/'traces'/w/'seed_42'/a/'links.json').read_text())
    vmax=max(max(v.values()) for v in links.values())
    fig,axes=plt.subplots(3,len(ALGORITHMS),figsize=(20,9),layout='constrained')
    norm=plt.Normalize(0,vmax);cmap=plt.get_cmap('magma')
    for i,w in enumerate(WORKLOADS):
        for j,a in enumerate(ALGORITHMS):
            ax=axes[i,j]
            for edge,v in links[w,a].items():
                u,t=map(int,edge.split('-'));r,c=divmod(u,4);rr,cc=divmod(t,4)
                ax.plot([c,cc],[r,rr],color=cmap(norm(v)),linewidth=6,solid_capstyle='round')
            for c in range(16):
                r,x=divmod(c,4);ax.plot(x,r,'o',color='#94a3b8',markersize=5)
            ax.set_aspect('equal');ax.invert_yaxis();ax.axis('off')
            if i==0:ax.set_title(a)
            if j==0:ax.text(-.5,1.5,w.replace('draper_qft_adder','Draper'),rotation=90,va='center')
    fig.suptitle('Link traffic heatmaps: total adjacent-hop requests per undirected link\n96 qubits · fixed placement · common color scale')
    fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),ax=axes.ravel().tolist(),label='hop requests',shrink=.8)
    fig.savefig(figures/'link_traffic.png',dpi=170);fig.savefig(figures/'link_traffic.pdf');plt.close(fig)
    # Temporal plots use original layer indices, preserving empty layers.
    for w in WORKLOADS:
        fig,axes=plt.subplots(len(ALGORITHMS),1,figsize=(14,11),sharex=True,layout='constrained')
        vmax=max(temporal[w,a].max() for a in ALGORITHMS)
        for ax,a in zip(axes,ALGORITHMS):
            im=ax.imshow(temporal[w,a].T,aspect='auto',origin='lower',vmin=0,vmax=vmax,cmap='magma',interpolation='nearest')
            ax.set_ylabel(a);ax.set_yticks([0,5,10,15])
        axes[-1].set_xlabel('Original circuit layer (including empty communication layers)')
        fig.suptitle(f'{w}: compile-time route demand per core and layer; C=4')
        fig.colorbar(im,ax=axes.tolist(),label='routes touching core',shrink=.8)
        fig.savefig(figures/f'temporal_{w}.png',dpi=160);plt.close(fig)
    if len(list((out/'simulation').glob('*/*/*/summary.csv')))<len(WORKLOADS)*len(ALGORITHMS):
        print('Structural heatmaps saved; physical simulations still running.');return
    runtime=[];waits=defaultdict(list);source_hashes=None
    for summary in sorted((out/'simulation').glob('*/*/*/summary.csv')):
        w,mapping,a=summary.parent.relative_to(out/'simulation').parts
        metadata=json.loads((summary.parent/'metadata.json').read_text())
        if source_hashes is None: source_hashes=metadata['source_sha256']
        assert metadata['source_sha256']==source_hashes
        trace=ro.read_trace(out/'traces'/w/mapping/a/'requests.txt',4,4)
        chains=defaultdict(list)
        for h in trace.hops: chains[h.layer,h.qubit].append(h.request_id)
        for row in csv.DictReader(summary.open()):
            assert float(row['completion_rate'])==1 and int(row['metric_version'])==3
            strategy,seed=row['strategy'],row['seed']
            audit=json.loads((summary.parent/f'audit_{strategy}_{seed}.json').read_text())
            assert not audit['violations'] and audit['completed_requests']==len(trace.hops)
            parts={int(r['request_id']):r for r in csv.DictReader((summary.parent/f'timing_{strategy}_{seed}.csv').open())}
            assert set(parts)=={h.request_id for h in trace.hops}
            # Per-qubit manager initializes request_submission_times at eligibility:
            # total_time_ms ALREADY includes admission waiting. Never add it again.
            assert np.isclose(np.mean([float(r['total_time_ms']) for r in parts.values()]),float(row['request_latency_mean_ms']),rtol=1e-9,atol=1e-9)
            latencies=migration_latencies(chains,parts)
            core_wait=np.zeros(16);counts=np.zeros(16)
            for h in trace.hops:
                for c in (h.source,h.target):
                    core_wait[c]+=float(parts[h.request_id]['admission_wait_time_ms']);counts[c]+=1
            waits[w,a,strategy].append(np.divide(core_wait,counts,out=np.zeros(16),where=counts>0))
            runtime.append(dict(workload=w,mapping_seed=mapping[5:],algorithm=a,**row,
                                migration_latency_mean_ms=float(np.mean(latencies)),migration_latency_p95_ms=float(np.percentile(latencies,95))))
    if not runtime: return
    write_csv(out/'runtime.csv',runtime)
    aggregated=[]
    for w in WORKLOADS:
        for a in ALGORITHMS:
            for s in ('on-demand','dynamic'):
                rs=[r for r in runtime if r['workload']==w and r['algorithm']==a and r['strategy']==s]
                if not rs: continue
                fields=('end_to_end_latency_ms','migration_latency_mean_ms','migration_latency_p95_ms','request_latency_mean_ms',
                        'average_admission_wait_ms','average_delivered_epr_fidelity')
                aggregate=dict(workload=w,algorithm=a,strategy=s,trials=len(rs))
                for f in fields:
                    values=[float(r[f]) for r in rs];aggregate[f]=float(np.mean(values));aggregate[f+'_sd']=float(np.std(values,ddof=1)) if len(values)>1 else 0
                aggregated.append(aggregate)
    write_csv(out/'aggregate.csv',aggregated)
    ranking=[]
    for s in ('dynamic','on-demand'):
        grid(figures,{(w,a):np.mean(waits[w,a,s],axis=0) for w in WORKLOADS for a in ALGORITHMS},
             f'admission_wait_{s}',f'Measured admission waiting: {s}','mean incident request admission wait (ms)')
    for metric,label,filename in (('migration_latency_mean_ms','Mean logical migration latency (ms)','migration_latency'),
                                  ('end_to_end_latency_ms','Workload completion time (ms)','makespan')):
        fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
        for ax,w in zip(axes,WORKLOADS):
            for offset,s,color in ((-.19,'on-demand','#64748b'),(.19,'dynamic','#0d9488')):
                rs=[next(r for r in aggregated if r['workload']==w and r['algorithm']==a and r['strategy']==s) for a in ALGORITHMS]
                ax.bar(np.arange(len(ALGORITHMS))+offset,[r[metric] for r in rs],width=.38,color=color,label='ODG' if s=='on-demand' else 'Compiler C=4',
                       yerr=[r[metric+'_sd'] for r in rs],capsize=2)
            ax.set_xticks(range(len(ALGORITHMS)),ALGORITHMS,rotation=35,ha='right');ax.set_title(w.replace('draper_qft_adder','Draper'));ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
        axes[0].legend();fig.suptitle('Physical simulation: four seeds per route · error bars = one sample standard deviation')
        fig.savefig(figures/f'{filename}.png',dpi=170);fig.savefig(figures/f'{filename}.pdf');plt.close(fig)
    for s in ('dynamic','on-demand'):
        values={a:[] for a in ALGORITHMS}
        for w in WORKLOADS:
            baseline=next(r for r in aggregated if r['workload']==w and r['algorithm']=='xy' and r['strategy']==s)
            for a in ALGORITHMS:
                r=next(r for r in aggregated if r['workload']==w and r['algorithm']==a and r['strategy']==s)
                values[a].append(r['end_to_end_latency_ms']/baseline['end_to_end_latency_ms'])
        scores=sorted((float(np.prod(v)**(1/3)),a) for a,v in values.items())
        for score,a in scores:
            ranking.append(dict(strategy=s,algorithm=a,geometric_mean_makespan_relative_to_xy=score))
        print(s,'geometric mean makespan / XY:',[(round(score,5),a) for score,a in scores])
    write_csv(out/'ranking.csv',ranking)
    def table(headers, rows):
        return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+
                         ['| '+' | '.join(map(str,row))+' |' for row in rows])
    lookup={(r['workload'],r['algorithm'],r['strategy']):r for r in aggregated}
    winner=min((r for r in ranking if r['strategy']=='dynamic'),key=lambda r:r['geometric_mean_makespan_relative_to_xy'])
    lines=['# Heavy-workload routing comparison — 2026-10-28','',
           f"Lowest measured aggregate compiler makespan: **{winner['algorithm']}**, ranked by the equal-workload geometric mean of makespan relative to XY.",
           '', 'This is an exploratory result for these three fixed 96-qubit placements, not a universal routing optimum. Each route was tested with simulator seeds 60–63 under both ODG and compiler C=4: 168 complete physical trials.',
           '', '## Compiler logical migration latency (ms)', '',
           'Mean ± sample standard deviation across four trials. A migration includes every sequential hop, admission waiting, reservation/control time, generation, retries and consumption. No pre-generation window is subtracted.', '',
           table(['Algorithm']+[w.replace('draper_qft_adder','Draper') for w in WORKLOADS],
                 [[a]+[f"{lookup[w,a,'dynamic']['migration_latency_mean_ms']:.4f} ± {lookup[w,a,'dynamic']['migration_latency_mean_ms_sd']:.4f}" for w in WORKLOADS] for a in ALGORITHMS]),
           '', '## Compiler workload completion time (ms)', '',
           table(['Algorithm']+list(WORKLOADS),[[a]+[f"{lookup[w,a,'dynamic']['end_to_end_latency_ms']:.2f}" for w in WORKLOADS] for a in ALGORITHMS]),
           '', '## ODG logical migration latency (ms)', '',
           table(['Algorithm']+list(WORKLOADS),[[a]+[f"{lookup[w,a,'on-demand']['migration_latency_mean_ms']:.4f}" for w in WORKLOADS] for a in ALGORITHMS]),
           '', '## Trace congestion and route length', '',
           'Excess = sum over all original layers and cores of max(0, number of routes touching core − 4). This is a compile-time demand proxy, not measured simultaneous occupancy.', '',
           table(['Workload','Algorithm','Hops','Route excess','Hop-incidence excess','Endpoint lower bound','MILP unproved layers'],
                 [[r[k] for k in ('workload','algorithm','hops','excess','hop_incidence_excess','endpoint_lower_bound','unproved_layers')] for r in structural]),
           '', '## Heatmaps and runtime plots', '',
           '![Core overload](figures/core_overload.png)', '', '![Link traffic](figures/link_traffic.png)', '',
           '![Measured compiler admission waiting](figures/admission_wait_dynamic.png)', '',
           '![Logical migration latency](figures/migration_latency.png)', '',
           '## Method and limits', '',
           '- MQT Bench 2.3.0 circuits, 96 qubits each; normalized into rz/sx/x/cx at optimization level 0; T-HQA/OEE placement, mapping and circuit seed 42.',
           '- Four-by-four mesh, 192 physical slots: eight data slots and four communication memories per core. Initial occupancy: 96 data qubits, 32 free data slots, 64 communication memories.',
           '- Paths retain every migration endpoint, qubit, order and original circuit layer. Replay is checked against every layer of the complete placement matrix. No truncation or conflict-free batching is introduced.',
           '- Compiler: all chain hops eligible for pre-generation, lead two layers, event admission, ready-first, native ownership handoff, no extra buffer. ODG gets the same four communication memories. Existing physical link configuration is fixed across all routes.',
           '- Physical timing retains the existing layer barrier and empty-layer timing. Workload completion excludes offline mapping/routing computation; structural.csv separately reports route construction/export/validation wall time.',
           '- Global MILP minimizes route-count excess (minexcess/detour2) or hop-incidence excess (minhop), with hops as tie breaker. All tested layers were solved to optimality within their candidate sets; this does not prove optimal runtime latency. Shortest+2 is a bounded search, not unrestricted routing.',
           '- The measured waiting heatmap averages admission wait over incident hop requests and attributes each request to both endpoint cores. It is not a measured queue length or a causal attribution to the blocking endpoint. Link heatmaps show counts, not utilization.',
           '- P95 in aggregate.csv is the average of the four trial p95s. Fidelity is delivered EPR fidelity per hop, not final circuit fidelity.',
           '- Four simulator seeds characterize noise on one placement per circuit. These runs selected the recommendation; broader held-out placements and hardware parameters remain untested.',
           '', 'See aggregate.csv, runtime.csv, structural.csv, ranking.csv and inputs.json for numeric evidence. Each raw trial includes its exact command, metadata/source hashes, invariant audit, admission decisions and timing records.']
    validation=[]
    for summary in sorted((out/'validation').glob('*/*/*/summary.csv')):
        w,mapping,a=summary.parent.relative_to(out/'validation').parts
        metadata=json.loads((summary.parent/'metadata.json').read_text())
        assert metadata['source_sha256']==source_hashes
        trace=ro.read_trace(out/'traces'/w/mapping/a/'requests.txt',4,4)
        chains=defaultdict(list)
        for h in trace.hops:chains[h.layer,h.qubit].append(h.request_id)
        for row in csv.DictReader(summary.open()):
            s,seed=row['strategy'],row['seed']
            audit=json.loads((summary.parent/f'audit_{s}_{seed}.json').read_text())
            assert not audit['violations'] and audit['completed_requests']==len(trace.hops)
            parts={int(r['request_id']):r for r in csv.DictReader((summary.parent/f'timing_{s}_{seed}.csv').open())}
            assert len(parts)==len(trace.hops)
            latencies=migration_latencies(chains,parts)
            assert np.isclose(np.mean([float(r['total_time_ms']) for r in parts.values()]),float(row['request_latency_mean_ms']),rtol=1e-9)
            validation.append(dict(workload=w,mapping_seed=mapping[5:],algorithm=a,**row,
                                   migration_latency_mean_ms=float(np.mean(latencies)),migration_latency_p95_ms=float(np.percentile(latencies,95))))
    if len(validation)==24:
        write_csv(out/'validation_runtime.csv',validation)
        validation_aggregate=[]
        for a in ('xy','greedy','minhop'):
            for s in ('dynamic','on-demand'):
                rs=[r for r in validation if r['algorithm']==a and r['strategy']==s]
                result=dict(algorithm=a,strategy=s,trials=len(rs))
                for field in ('request_latency_mean_ms','migration_latency_mean_ms','migration_latency_p95_ms',
                              'end_to_end_latency_ms','average_admission_wait_ms','average_delivered_epr_fidelity'):
                    values=[float(r[field]) for r in rs];result[field]=float(np.mean(values));result[field+'_sd']=float(np.std(values,ddof=1))
                validation_aggregate.append(result)
        write_csv(out/'validation_aggregate.csv',validation_aggregate)
        lines.extend(['','## Fresh QAOA simulator-seed validation','',
                      'After the seven-route comparison, XY and the two aggregate leaders (greedy and minhop) were tested on simulator seeds 64–67. Routes and weights were frozen. This adds 24 complete, audited trials (192 total). These remain the same QAOA circuit and placement; only the simulator randomness is held out.', '',
                      table(['Algorithm','Policy','Mean hop (ms)','Mean migration (ms)','P95 migration (ms)','Completion time (ms)'],
                            [[r['algorithm'],r['strategy'],f"{r['request_latency_mean_ms']:.4f}",f"{r['migration_latency_mean_ms']:.4f}",
                              f"{r['migration_latency_p95_ms']:.4f}",f"{r['end_to_end_latency_ms']:.2f} ± {r['end_to_end_latency_ms_sd']:.2f}"] for r in validation_aggregate])])
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved',figures,'and aggregate.csv')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);report(p.parse_args().output)
