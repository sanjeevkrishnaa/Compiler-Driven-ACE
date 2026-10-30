"""Aggregate complete window trials, including pair age and reservation-start-to-use."""
from __future__ import annotations
import argparse,csv,json
from collections import Counter
from pathlib import Path
from statistics import mean,stdev
import numpy as np

FIELDS=('request_latency_mean_ms','request_latency_p95_ms','end_to_end_latency_ms',
        'average_admission_wait_ms','compiler_expiry_percentage','compiler_waste_percentage',
        'pregenerated_success_rate','total_retries','average_delivered_epr_fidelity')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);a=p.parse_args()
    rows=[]
    for phase in sorted(a.study.iterdir()):
        if not (phase/'all_seeds.csv').exists():continue
        trials=list(csv.DictReader((phase/'all_seeds.csv').open()))
        for workload in sorted({r['workload'] for r in trials}):
            for window in sorted({float(r['window_ms']) for r in trials if r['workload']==workload}):
                rs=[r for r in trials if r['workload']==workload and float(r['window_ms'])==window]
                d=dict(phase=phase.name,workload=workload,window_ms=window,compiler_memories=rs[0]['compiler_memories'],trials=len(rs))
                for field in FIELDS:
                    vs=[float(r[field]) for r in rs];d[field]=mean(vs);d[field+'_sd']=stdev(vs) if len(vs)>1 else 0
                ages=[];reservation_ages=[];reasons=Counter();generated=0
                for r in rs:
                    dest=phase/workload/f'{window:g}ms'
                    audit=json.loads((dest/f"audit_dynamic_{r['seed']}.json").read_text())
                    assert not audit['violations'] and audit['completed_requests']==audit['total_requests'] and float(r['completion_rate'])==1
                    for pair in csv.DictReader((dest/f"pairs_dynamic_{r['seed']}.csv").open()):
                        generated+=1
                        if pair['status']=='expired':reasons[pair['expiry_reason']]+=1
                        if pair['reservation_start_ps']:
                            assert np.isclose(float(pair['reservation_end_ps'])-float(pair['reservation_start_ps']),window*1e9,rtol=0,atol=1)
                        if pair['status']!='used':continue
                        ages.append((float(pair['utilized_at_ps'])-float(pair['generated_at_ps']))/1e9)
                        if pair['reservation_start_ps']:reservation_ages.append((float(pair['utilized_at_ps'])-float(pair['reservation_start_ps']))/1e9)
                d['deadline_expired_pairs_mean']=reasons['reservation_expired']/len(rs)
                d['deadline_expiry_percentage_pooled']=100*reasons['reservation_expired']/generated if generated else 0
                d['demand_progress_expired_pairs_mean']=reasons['demand_progress']/len(rs)
                for name,vs in [('pair_ready_age',ages),('reservation_start_to_use',reservation_ages)]:
                    for suffix,percentile in [('p95_ms',95),('p99_ms',99),('max_ms',100)]:d[name+'_'+suffix]=float(np.percentile(vs,percentile)) if vs else None
                rows.append(d)
    with (a.study/'aggregate.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    for r in rows:print(r['phase'],r['workload'],r['window_ms'],'mean',round(r['request_latency_mean_ms'],4),'p95',round(r['request_latency_p95_ms'],3),'span',round(r['end_to_end_latency_ms'],1),'expiry%',round(r['compiler_expiry_percentage'],3),'lease-use max',round(r['reservation_start_to_use_max_ms'],2))

if __name__=='__main__':main()
