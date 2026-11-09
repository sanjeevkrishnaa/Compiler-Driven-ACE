"""Validate physical results and assemble immutable evidence for the workbook."""
import csv,hashlib,json
from pathlib import Path
from ace.compiler.compiler_trace import parse_compiler_trace,plan_preparations

OUT=Path(__file__).resolve().parent
manifest=json.loads((OUT/'manifest.json').read_text())
complete=[m for m in manifest if (Path(m['folder'])/'summary.csv').exists()]
records=[];source=None;reference=None
requests_by_route={}
for m in complete:
    folder=Path(m['folder'])
    meta=json.loads((folder/'metadata.json').read_text())
    params=meta['parameters']
    if source is None:
        source=meta['source_sha256'];reference=params
    assert source==meta['source_sha256'],folder
    allowed={'planner_lead_layers','dynamic_lookahead_layers','trace','output'}
    assert {k for k in params if params[k]!=reference[k]}<=allowed
    assert params['planner_lead_layers']==params['dynamic_lookahead_layers']==m['lead']
    assert params['borrow_compiler_pairs'] is True and params['preparation_priority']=='trace'
    if m['route'] not in requests_by_route:
        trace=parse_compiler_trace(Path(params['trace']))
        requests_by_route[m['route']]=trace
    trace=requests_by_route[m['route']]
    ranks={l:i for i,l in enumerate(sorted({r.layer for r in trace.requests}))}
    req={r.request_id:r for r in trace.requests}
    plan,blocked,peak=plan_preparations(trace,strategy='dynamic',compiler_memories_per_core=6,
        generation_capacity_per_core=8,coherence_time_layers=10,lead_layers=m['lead'],
        dynamic_lookahead_layers=m['lead'],layer_basis='active',preparation_priority='trace')
    assert all(ranks[req[p.request_id].layer]-ranks[p.generation_layer]==m['lead'] for p in plan)
    samples=list(csv.DictReader((folder/'summary.csv').open()));assert len(samples)==1
    raw=samples[0]
    metrics={k:float(v) for k,v in raw.items() if v and k not in {'strategy','latency_scope'}}
    assert int(metrics['seed'])==60
    assert int(metrics['requests'])==int(metrics['completed_requests'])==29605
    assert int(metrics['scheduled_preparations'])==len(plan)
    assert int(metrics['planner_blocked_preparations'])==blocked
    assert int(metrics['replacement_preparations_requested'])==int(metrics['replacement_attempts_immediate'])
    audit=json.loads((folder/'audit_dynamic_60.json').read_text())
    assert not audit['violations'] and audit['completed_requests']==audit['total_requests']==29605
    assert metrics['generated_compiler_pairs']==sum(metrics[k] for k in ('utilized_compiler_pairs','expired_compiler_pairs','remaining_compiler_pairs'))
    assert abs(metrics['compiler_waste_percentage']-100*(metrics['expired_compiler_pairs']+metrics['remaining_compiler_pairs'])/metrics['generated_compiler_pairs'])<1e-9
    records.append(dict(route=m['route'],lead=m['lead'],reused=m['reused'],metrics=metrics,
        summary=str(folder/'summary.csv'),audit=str(folder/'audit_dynamic_60.json'),
        metadata=str(folder/'metadata.json'),trace=str(Path(params['trace'])),
        trace_sha256=hashlib.sha256(Path(params['trace']).read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
        ace_commit=meta['runtime']['ace']['git_commit'],engine_version=meta['runtime']['sequence']['version'],
        engine_path=meta['runtime']['sequence']['module_file'],created_at=meta['created_at']))
records.sort(key=lambda r:({'xy':0,'history':1}[r['route']],r['lead']))
aggregate=[]
if len(records)==18:
    for lead in range(1,10):
        cells=[r for r in records if r['lead']==lead];assert len(cells)==2
        n=sum(r['metrics']['requests'] for r in cells)
        generated=sum(r['metrics']['generated_compiler_pairs'] for r in cells)
        aggregate.append(dict(lead=lead,
            mean_latency_ms=sum(r['metrics']['average_request_latency_ms']*r['metrics']['requests'] for r in cells)/n,
            mean_completion_s=sum(r['metrics']['end_to_end_latency_ms'] for r in cells)/2000,
            delivered_fidelity=sum(r['metrics']['average_delivered_epr_fidelity']*r['metrics']['requests'] for r in cells)/n,
            waste=sum(r['metrics']['expired_compiler_pairs']+r['metrics']['remaining_compiler_pairs'] for r in cells)/generated,
            coverage=sum(r['metrics']['pregenerated_hits'] for r in cells)/n))
data=dict(completed=len(records),total=18,records=records,aggregate=aggregate,
    selection='Lowest pooled mean request latency across both equally sized routes',
    coherence_limit_layers=10,source_sha256=source)
if aggregate:
    data['winner']=min(aggregate,key=lambda r:r['mean_latency_ms'])
    data['route_winners']={route:min((r for r in records if r['route']==route),key=lambda r:r['metrics']['average_request_latency_ms'])['lead'] for route in ('xy','history')}
    data['lowest_waste']=min(aggregate,key=lambda r:r['waste'])
(OUT/'evidence.json').write_text(json.dumps(data,indent=2))
print(json.dumps({k:v for k,v in data.items() if k not in {'records','source_sha256'}},indent=2))
