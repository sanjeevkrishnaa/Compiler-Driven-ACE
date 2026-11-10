"""Measure generation that finishes after its target's recorded completion."""
import csv,json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent
before=json.loads((ROOT.parents[1]/'results/compiler_lead_sweep_2026-11-10/evidence.json').read_text())
manifest=json.loads((ROOT/'manifest.json').read_text())
rows=[]
for m in manifest:
    new=Path(m['folder'])
    if not (new/'summary.csv').exists():continue
    old=next(r for r in before['records'] if r['route']==m['route'] and r['lead']==m['lead'])
    row=dict(route=m['route'],lead=m['lead'])
    for phase,folder in [('before',Path(old['summary']).parent),('after',new)]:
        timing={int(r['request_id']):float(r['total_time_ms'])*1e9
                for r in csv.DictReader((folder/'timing_dynamic_60.csv').open())}
        late=[];reasons=Counter()
        for r in csv.DictReader((folder/'pairs_dynamic_60.csv').open()):
            if r['status'] in ('expired','cancelled'):reasons[r['status']+':'+r['expiry_reason']]+=1
            if r['target_request_start_ps']:
                completed=float(r['target_request_start_ps'])+timing[int(r['target_request_id'])]
                delay=float(r['generated_at_ps'])-completed
                if delay>1:late.append(delay/1e9)
        row[phase+'_generated_after_completion']=len(late)
        row[phase+'_max_delay_ms']=max(late,default=0)
        row[phase+'_loss_reasons']=dict(reasons)
    rows.append(row)
(ROOT/'completion_diagnostics.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
