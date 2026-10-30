"""Matched full-trace compiler reservation-window sweep; timing rules stay fixed."""
from __future__ import annotations
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORKLOADS = ('qft', 'draper_qft_adder', 'qaoa')

def prepare_inputs(study):
    archive=ROOT/'results/heavy_routing_2026-10-28/evidence.zip'
    manifest=[]
    with zipfile.ZipFile(archive) as z:
        for workload in WORKLOADS:
            member=f'study/traces/{workload}/seed_42/xy/requests.txt'
            content=z.read(member);dest=study/'inputs'/workload/'requests.txt'
            dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists() and dest.read_bytes()!=content:raise ValueError('Study inputs differ from frozen XY traces')
            if not dest.exists():dest.write_bytes(content)
            manifest.append(dict(workload=workload,logical_qubits=96,mapping='T-HQA',mapping_seed=42,
                                 routing='xy',archive=str(archive.relative_to(ROOT)),member=member,
                                 sha256=hashlib.sha256(content).hexdigest()))
    (study/'inputs_manifest.json').write_text(json.dumps(manifest,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True)
    p.add_argument('--phase',default='selection')
    p.add_argument('--windows',default='10,20,50,100,1000')
    p.add_argument('--seeds',default='60,61')
    p.add_argument('--compiler-memories',type=int,default=4)
    a=p.parse_args();out=a.study/a.phase;out.mkdir(parents=True,exist_ok=True)
    prepare_inputs(a.study)
    windows=[float(x) for x in a.windows.split(',')]
    if any(x<=0 for x in windows):p.error('windows must be positive')
    def run(workload,window):
        dest=out/workload/f'{window:g}ms'
        cmd=[sys.executable,'-u','-B',str(ROOT/'run_trace_comparison.py'),
             '--trace',str((a.study/'inputs'/workload/'requests.txt').resolve()),
             '--config',str(ROOT/'config/final_config/grid_4x4_ace_3.json'),
             '--strategies','dynamic','--seeds',a.seeds,'--total-memories','4',
             '--compiler-memories',str(a.compiler_memories),'--generation-capacity',str(a.compiler_memories),
             '--planner-lead-layers','2','--scheduler','per-qubit','--admission','event',
             '--admission-priority','ready-first','--all-chain-hops','--no-congestion-threshold',
             '--pregeneration-buffer-ms','0','--compiler-pair-consumption','handoff',
             '--compiler-reservation-ms',str(window),'--stop-after-workload','--audit-events',
             '--output',str(dest.resolve())]
        dest.mkdir(parents=True,exist_ok=True)
        if (dest/'summary.csv').exists():
            if json.loads((dest/'command.json').read_text())!=cmd:raise ValueError('Completed output has different parameters')
        else:
            (dest/'command.json').write_text(json.dumps(cmd,indent=2))
            with (dest/'run.log').open('w') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
        rows=[]
        for r in csv.DictReader((dest/'summary.csv').open()):
            audit=json.loads((dest/f"audit_dynamic_{r['seed']}.json").read_text())
            assert float(r['completion_rate'])==1 and not audit['violations']
            rows.append(dict(phase=a.phase,workload=workload,window_ms=window,compiler_memories=a.compiler_memories,**r))
        print(workload,window,[(r['seed'],round(float(r['request_latency_mean_ms']),4),round(float(r['compiler_expiry_percentage']),2)) for r in rows],flush=True)
        return rows
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(run,w,t) for w in WORKLOADS for t in windows]):rows.extend(f.result())
    with (out/'all_seeds.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

if __name__=='__main__':main()
