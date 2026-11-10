"""Resumable exact L-1..L-9 QAOA sweep with four physical workers."""
import json,os,subprocess,sys,time
from pathlib import Path

OUT=Path(__file__).resolve().parent
ACE=OUT.parents[1]
INPUTS=Path(r'C:\Users\sanje\Desktop\BTP\ACE')
env=os.environ.copy()
env.update(PYTHONPATH=os.pathsep.join(map(str,[INPUTS/'third_party/SeQUeNCe',ACE])),
    PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(OUT/'mpl-cache'),TEMP=str(OUT/'temp'),TMP=str(OUT/'temp'))
for name in ('temp','mpl-cache'):
    (OUT/name).mkdir(exist_ok=True)
manifest=[]
for route in ('xy','history'):
    for lead in range(1,10):
        folder=OUT/f'{route}-L{lead}'
        manifest.append(dict(route=route,lead=lead,folder=str(folder),reused=False))
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
pending=[m for m in manifest if not (Path(m['folder'])/'summary.csv').exists()]
jobs=[]
print('REUSED/COMPLETE',len(manifest)-len(pending),'NEW',len(pending),flush=True)
try:
    while pending or jobs:
        while pending and len(jobs)<4:
            m=pending.pop(0);folder=Path(m['folder']);folder.mkdir(exist_ok=True)
            cmd=[sys.executable,'-B','-u',str(OUT/'worker.py'),'--worker','--trace',
                str(INPUTS/f"output/benchmark-matrix-224-2026-11-04/routed/traces/qaoa/seed_42/{m['route']}/requests.txt"),
                '--strategies','dynamic','--seeds','60','--total-memories','8','--compiler-memories','6',
                '--generation-capacity','8','--preparation-priority','trace',
                '--planner-lead-layers',str(m['lead']),'--dynamic-lookahead-layers',str(m['lead']),
                '--seed-reference-memories','4','--stop-after-workload','--audit-events',
                '--record-chain-coverage','--stop-time-s','1000','--borrow-compiler-pairs','--output',str(folder)]
            (folder/'command.json').write_text(json.dumps(cmd,indent=2))
            log=(folder/'run.log').open('w')
            proc=subprocess.Popen(cmd,cwd=ACE,env=env,stdout=log,stderr=subprocess.STDOUT)
            jobs.append((m,proc,log));print('START',folder.name,flush=True)
        for m,proc,log in list(jobs):
            code=proc.poll()
            if code is not None:
                log.close();jobs.remove((m,proc,log))
                print('FINISH',m['route'],m['lead'],code,flush=True)
                if code:
                    raise RuntimeError((Path(m['folder'])/'run.log').read_text()[-5000:])
        complete=sum((Path(m['folder'])/'summary.csv').exists() for m in manifest)
        (OUT/'sweep_progress.json').write_text(json.dumps(dict(completed=complete,total=18,
            running=[dict(route=m['route'],lead=m['lead']) for m,_,_ in jobs],pending=len(pending),updated=time.time())))
        if jobs:
            time.sleep(3)
finally:
    for m,proc,log in jobs:
        proc.terminate();proc.wait();log.close()
