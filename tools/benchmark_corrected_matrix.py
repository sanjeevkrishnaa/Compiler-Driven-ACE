"""Fresh 180-case main-policy matrix after autonomous-ready admission repair."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import benchmark_matrix as matrix
BASE = ROOT / 'output/benchmark-matrix-224-2026-11-04'
OUT = ROOT / 'output/benchmark-matrix-224-readyfix-lookback1-2026-11-04'
matrix.OUT = OUT
CASES = [(label, strategy, memory, (min(3, memory // 2) if strategy in
    ('continuous', 'adaptive-continuous') else quota)) for label, strategy, memory, quota in matrix.CASES]


def publish():
    rows = matrix.collect()
    hashes = None
    for row in rows:
        folder = ROOT / Path(row['source']).parent
        meta = json.loads((folder / 'metadata.json').read_text())
        if hashes is not None and hashes != meta['source_sha256']:
            raise RuntimeError('Simulator source changed during the study.')
        hashes = meta['source_sha256']
        audit = json.loads((folder / f'audit_{row["strategy"]}_60.json').read_text())
        if audit['violations'] or audit['completed_requests'] != audit['total_requests']:
            raise RuntimeError(f'Invalid/incomplete physical execution: {folder}')
        p = meta['parameters']
        if row['strategy'] == 'dynamic':
            assert p['planner_lead_layers'] == 1 and p['dynamic_lookahead_layers'] == 8
            assert p['demand_first'] and p['preparation_priority'] == 'chain-length'
        if row['strategy'] in ('continuous', 'adaptive-continuous'):
            assert p['autonomous_cache_follows_compiler_memories']
            assert p['compiler_memories'] == min(3, p['total_memories'] // 2)
    env = os.environ.copy(); env['ACE_MATRIX_ROOT'] = str(OUT)
    node = Path(r'C:\Users\sanje\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
    with (OUT / 'workbook.log').open('w') as log:
        subprocess.run([str(node), str(BASE / 'build_workbook.mjs')], cwd=ROOT, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    return len(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads((BASE / 'specification.json').read_text())
    spec.update(cases=CASES, minimum_lead_layers=1, maximum_lead_layers=8,
        reused_baseline_count=0, rerun_count=180, autonomous_cache_limit={'4': 2, '8': 3},
        readiness_fixed=True, cd_policy='main: guard, chain-length, async, 1-8 active layers')
    matrix.save(OUT / 'specification.json', spec)
    count = len(matrix.collect())
    for w in matrix.WORKLOADS:
        for route in ('xy', 'history'):
            trace = BASE / 'routed/traces' / w / 'seed_42' / route / 'requests.txt'
            for label, strategy, memory, quota in CASES:
                output = OUT / 'runs' / w / route / label
                if (output / 'pair_lifecycle.json').exists():
                    continue
                output.mkdir(parents=True, exist_ok=True)
                matrix.save(OUT / 'progress.json', dict(stage='simulation', workload=w, route=route,
                    case=label, completed=count, total=180, started=time.time(), pid=os.getpid()))
                command = [sys.executable, '-u', str(ROOT / 'tools/benchmark_matrix.py'), '--worker',
                    '--trace', str(trace), '--strategies', strategy, '--seeds', '60',
                    '--total-memories', str(memory), '--compiler-memories', str(quota),
                    '--generation-capacity', str(memory), '--planner-lead-layers', '1',
                    '--dynamic-lookahead-layers', '8', '--seed-reference-memories', '4',
                    '--stop-after-workload', '--audit-events', '--record-chain-coverage',
                    '--stop-time-s', '1000', '--output', str(output)]
                if strategy in ('continuous', 'adaptive-continuous'):
                    command.append('--autonomous-cache-follows-compiler-memories')
                matrix.save(output / 'command.json', command)
                print('RUN', w, route, label, flush=True)
                with (output / 'run.log').open('w') as log:
                    subprocess.run(command, cwd=ROOT, env=matrix.environment(), stdout=log,
                                   stderr=subprocess.STDOUT, check=True)
                audit = json.loads((output / f'audit_{strategy}_60.json').read_text())
                if audit['violations'] or audit['completed_requests'] != audit['total_requests']:
                    raise RuntimeError(f'Invalid physical run: {output}')
                count = len(matrix.collect())
                print('DONE', count, '/180', flush=True)
        publish()
    assert publish() == 180
    matrix.save(OUT / 'progress.json', dict(stage='complete', completed=180, total=180))


if __name__ == '__main__':
    try:
        if '--after-validation' in sys.argv:
            folder = ROOT / 'output/cgp-diagnosis-2026-11-04/ready-fixed-cache2-full'
            validation = list(csv.DictReader((folder / 'summary.csv').open()))
            assert {r['strategy'] for r in validation} == {'continuous', 'adaptive-continuous'}
            for row in validation:
                audit = json.loads((folder / f'audit_{row["strategy"]}_60.json').read_text())
                assert not audit['violations'] and audit['completed_requests'] == audit['total_requests']
                assert float(row['completion_rate']) == 1
        main()
    except Exception as exc:
        matrix.save(OUT / 'failure.json', dict(error=repr(exc), time=time.time()))
        raise
