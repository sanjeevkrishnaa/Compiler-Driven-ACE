"""Run only the corrected simulations needed for the presentation's graph slots."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import benchmark_matrix as matrix
from tools.benchmark_corrected_matrix import CASES
BASE=ROOT/'output/benchmark-matrix-224-2026-11-04'
MAIN=ROOT/'output/benchmark-matrix-224-readyfix-lookback1-2026-11-04'
OUT=ROOT/'output/slide-graphs-2026-11-04'
DENSE=('qft','qpeexact','qaoa','bmw_quark_copula')


def jobs():
    required=[]
    for w in matrix.WORKLOADS:
        required += [(w,'xy',case) for case in CASES if case[0] in ('ODG-8','CGP-8','ACGP-8','CD-8')]
    for w in DENSE:
        required += [(w,'history',case) for case in CASES if case[0] in ('ODG-8','CGP-8','ACGP-8','CD-8')]
    for route in ('xy','history'):
        required += [('qft',route,case) for case in CASES if case[0] in ('ODG-4','CGP-4','ACGP-4','CD-4','CD-unlimited')]
    return required


def main():
    required=jobs()
    matrix.save(OUT/'graph-required-cases.json',required)
    old=json.loads((MAIN/'progress.json').read_text())
    if old.get('stage') not in ('paused_for_graph_priority','complete'):
        matrix.save(MAIN/'progress.json',dict(stage='paused_for_graph_priority',
            completed=old.get('completed',0),total=180,reason='User requested only graph-required cases now.'))
    matrix.OUT=MAIN
    complete=lambda: sum((MAIN/'runs'/w/r/c[0]/'pair_lifecycle.json').exists() for w,r,c in required)
    for w,route,(label,strategy,memory,quota) in required:
        output=MAIN/'runs'/w/route/label
        if (output/'pair_lifecycle.json').exists():
            continue
        output.mkdir(parents=True,exist_ok=True)
        matrix.save(OUT/'graph-priority-progress.json',dict(stage='simulation',completed=complete(),
            total=len(required),workload=w,route=route,case=label,pid=__import__('os').getpid(),started=time.time()))
        command=[sys.executable,'-u',str(ROOT/'tools/slide_graph_measurements.py'),'--worker',
            '--trace',str(BASE/'routed/traces'/w/'seed_42'/route/'requests.txt'),
            '--strategies',strategy,'--seeds','60','--total-memories',str(memory),
            '--compiler-memories',str(quota),'--generation-capacity',str(memory),
            '--planner-lead-layers','1','--dynamic-lookahead-layers','8',
            '--seed-reference-memories','4','--stop-after-workload','--audit-events',
            '--record-chain-coverage','--stop-time-s','1000','--output',str(output)]
        if strategy in ('continuous','adaptive-continuous'):
            command.append('--autonomous-cache-follows-compiler-memories')
        if w=='qft' and route=='xy' and label=='CD-8':
            command.append('--headroom')
        matrix.save(output/'command.json',command)
        print('GRAPH RUN',w,route,label,flush=True)
        with (output/'run.log').open('w') as log:
            subprocess.run(command,cwd=ROOT,env=matrix.environment(),stdout=log,stderr=subprocess.STDOUT,check=True)
        audit=json.loads((output/f'audit_{strategy}_60.json').read_text())
        assert not audit['violations'] and audit['completed_requests']==audit['total_requests']
        matrix.collect()
        print('GRAPH DONE',complete(),'/',len(required),flush=True)
    matrix.save(OUT/'graph-priority-progress.json',dict(stage='supplemental',completed=complete(),total=len(required)))
    subprocess.run([sys.executable,'-u',str(ROOT/'tools/slide_graph_measurements.py'),'--supplement-only'],
                   cwd=ROOT,env=matrix.environment(),check=True)
    matrix.save(OUT/'graph-priority-progress.json',dict(stage='complete',completed=complete(),total=len(required),
        scope='All graph-required main cases and supplemental measurements complete; broad180-case study remains paused.'))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        matrix.save(OUT/'graph-priority-failure.json',dict(error=repr(exc)))
        raise
