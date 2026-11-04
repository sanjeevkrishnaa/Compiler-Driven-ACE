"""Main-policy matrix: rerun 60 CD cases at 1-8, reuse 120 unaffected baselines."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import benchmark_matrix as matrix

BASE = ROOT / 'output/benchmark-matrix-224-2026-11-04'
OUT = ROOT / 'output/benchmark-matrix-224-lookback1-2026-11-04'
matrix.OUT = OUT
NODE = Path(r'C:\Users\sanje\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')


def publish():
    rows = matrix.collect()
    source = None
    cd = 0
    for row in rows:
        folder = ROOT / Path(row['source']).parent
        meta = json.loads((folder / 'metadata.json').read_text())
        audit = json.loads((folder / f'audit_{row["strategy"]}_60.json').read_text())
        if audit['violations'] or audit['completed_requests'] != audit['total_requests']:
            raise RuntimeError(f'Invalid audit: {folder}')
        hashes = {k: v for k, v in meta['source_sha256'].items() if k != 'compiler_settings.py'}
        if source is not None and source != hashes:
            raise RuntimeError('Non-default simulator source differs across the reused/new runs.')
        source = hashes
        if row['strategy'] == 'dynamic':
            p = meta['parameters']
            assert p['planner_lead_layers'] == 1 and p['dynamic_lookahead_layers'] == 8
            assert p['demand_first'] is True and p['preparation_priority'] == 'chain-length'
            if folder.name == 'CD-unlimited':
                assert json.loads((folder / 'unlimited_verification.json').read_text())['verified']
            cd += 1
    env = os.environ.copy()
    env['ACE_MATRIX_ROOT'] = str(OUT)
    with (OUT / 'workbook.log').open('w') as log:
        subprocess.run([str(NODE), str(BASE / 'build_workbook.mjs')], cwd=ROOT, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    return len(rows), cd


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads((BASE / 'specification.json').read_text())
    spec.update(minimum_lead_layers=1, maximum_lead_layers=8, reused_baseline_count=120,
                cd_policy='main: demand guard, longest-chain priority, async refill, 1-8 active layers',
                baseline_source=str(BASE), rerun_count=60)
    matrix.save(OUT / 'specification.json', spec)
    # Copy only the small authoritative result/audit files. Original runs remain intact.
    for w in matrix.WORKLOADS:
        for route in ('xy', 'history'):
            for label, strategy, memory, quota in matrix.CASES:
                if strategy == 'dynamic':
                    continue
                src = BASE / 'runs' / w / route / label
                dst = OUT / 'runs' / w / route / label
                dst.mkdir(parents=True, exist_ok=True)
                for name in ('summary.csv', 'metadata.json', 'pair_lifecycle.json', f'audit_{strategy}_60.json'):
                    if not (dst / name).exists():
                        shutil.copy2(src / name, dst / name)
                matrix.save(dst / 'reused_from.json', dict(source=str(src),
                    reason='Lookback is unused by ODG, CGP, ACGP; measurements reused without modification.'))
    total, completed = publish()
    for w in matrix.WORKLOADS:
        for route in ('xy', 'history'):
            trace = BASE / 'routed/traces' / w / 'seed_42' / route / 'requests.txt'
            for label, strategy, memory, quota in matrix.CASES:
                if strategy != 'dynamic':
                    continue
                output = OUT / 'runs' / w / route / label
                if (output / 'pair_lifecycle.json').exists():
                    continue
                output.mkdir(parents=True, exist_ok=True)
                matrix.save(OUT / 'progress.json', dict(stage='simulation', workload=w, route=route,
                    case=label, completed_cd=completed, total_cd=60, total_rows=180,
                    reused_baselines=120, started=time.time()))
                command = [sys.executable, '-u', str(ROOT / 'tools/benchmark_matrix.py'), '--worker',
                    '--trace', str(trace), '--strategies', 'dynamic', '--seeds', '60',
                    '--total-memories', str(memory), '--compiler-memories', str(quota),
                    '--generation-capacity', str(memory), '--planner-lead-layers', '1',
                    '--dynamic-lookahead-layers', '8', '--seed-reference-memories', '4',
                    '--stop-after-workload', '--audit-events', '--record-chain-coverage',
                    '--stop-time-s', '1000', '--output', str(output)]
                matrix.save(output / 'command.json', command)
                print('RUN', w, route, label, flush=True)
                with (output / 'run.log').open('w') as log:
                    subprocess.run(command, cwd=ROOT, env=matrix.environment(), stdout=log,
                                   stderr=subprocess.STDOUT, check=True)
                completed += 1
                matrix.collect()
                print('DONE', completed, '/60 new CD runs', flush=True)
        publish()
    total, completed = publish()
    assert total == 180 and completed == 60
    matrix.save(OUT / 'progress.json', dict(stage='complete', completed_cd=60, total_cd=60,
        completed=180, total=180, reused_baselines=120))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        matrix.save(OUT / 'failure.json', dict(error=repr(exc), time=time.time()))
        raise
