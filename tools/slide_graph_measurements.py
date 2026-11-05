"""Additional physical measurements for Google Slides chart slots.

Run only after the corrected 180-case matrix has completed. Uses its frozen
QFT mapping and routing, and never edits simulator-policy source files.
"""
from __future__ import annotations
from collections import defaultdict
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import benchmark_matrix as matrix
BASE = ROOT / 'output/benchmark-matrix-224-2026-11-04'
MAIN = ROOT / 'output/benchmark-matrix-224-readyfix-lookback1-2026-11-04'
OUT = ROOT / 'output/slide-graphs-2026-11-04'


def headroom(result, output):
    """Integrate actual lease windows, truncated by early releases, per core."""
    from ace.observability.execution_events import Booked, Unbooked
    manager = result['request_manager']
    start, end = manager.series_start_time, manager.series_end_time
    leases = {}
    for e in manager.recorder.events:
        if isinstance(e, Booked):
            key = (e.node, e.memory_index, e.reservation_id)
            assert e.start_ps is not None and e.end_ps is not None
            leases[key] = [e.start_ps, e.end_ps]
        elif isinstance(e, Unbooked):
            key = (e.node, e.memory_index, e.reservation_id)
            if key in leases:
                leases[key][1] = min(leases[key][1], e.time_ps)
    transitions = defaultdict(list)
    for (node, slot, _), (a, b) in leases.items():
        a, b = max(start, a), min(end, b)
        if a < b:
            transitions[node].extend([(a, slot, 1), (b, slot, -1)])
    rows = []
    for node in sorted(manager.name_to_apps):
        occupied, duration, last = defaultdict(int), [0, 0, 0], start
        groups = defaultdict(list)
        for t, slot, change in transitions[node]:
            groups[t].append((slot, change))
        for t in sorted(groups):
            free = 8 - sum(v > 0 for v in occupied.values())
            duration[min(2, max(0, free))] += t - last
            for slot, change in groups[t]:
                occupied[slot] += change
                assert occupied[slot] >= 0
            last = t
        free = 8 - sum(v > 0 for v in occupied.values())
        duration[min(2, max(0, free))] += end - last
        assert sum(duration) == end - start
        rows.append(dict(core=node, zero_free=duration[0] / (end-start),
            one_free=duration[1] / (end-start), two_or_more_free=duration[2] / (end-start)))
    matrix.save(output / 'headroom.json', dict(definition='time-weighted free physical reservation slots, capped at two; not dedicated ODG slots',
        start_ps=start, end_ps=end, rows=rows))


def worker():
    sys.path[:0] = [str(ROOT/'third_party/SeQUeNCe'), str(ROOT)]
    from ace.cli import run_trace_comparison as cli
    output = Path(sys.argv[sys.argv.index('--output')+1])
    record_headroom = '--headroom' in sys.argv
    if record_headroom:
        sys.argv.remove('--headroom')
    original_row = cli._row
    def row(strategy, seed, result, *args):
        if record_headroom or output.name == 'headroom-qft-xy-cd8':
            headroom(result, output)
        return original_row(strategy, seed, result, *args)
    cli._row = row
    matrix.worker()


def main():
    status = json.loads((MAIN/'progress.json').read_text())
    if '--supplement-only' not in sys.argv and status['stage'] != 'complete':
        # The user reprioritized the existing supervisor to graph-required work.
        from tools.graph_priority import main as prioritize
        prioritize()
        return
    cases = []
    for route in ('xy', 'history'):
        for memory in (1, 2, 3, 6):
            for strategy in ('on-demand', 'continuous', 'adaptive-continuous', 'dynamic'):
                quota = (memory*3//4 if strategy == 'dynamic' else min(3, memory//2))
                cases.append((route, strategy, memory, quota, f'{route}-{strategy}-k{memory}'))
        for strategy in ('on-demand', 'continuous', 'adaptive-continuous'):
            cases.append((route, strategy, 256, 3, f'{route}-{strategy}-k256'))
    existing_headroom = MAIN/'runs/qft/xy/CD-8/headroom.json'
    if existing_headroom.exists():
        matrix.save(OUT/'runs/headroom-qft-xy-cd8/headroom.json', json.loads(existing_headroom.read_text()))
    else:
        cases.append(('xy', 'dynamic', 8, 6, 'headroom-qft-xy-cd8'))
    matrix.save(OUT/'supplement-specification.json', dict(cases=cases, count=len(cases), seed=60,
        workloads=['qft'], minimum_lead=1, maximum_lead=8,
        small_memory_seed_reference='min(4, K), constant within each K',
        compiler_quota='floor(3*K/4) for finite K', autonomous_cache='min(3, floor(K/2))'))
    rows = []
    for index, (route, strategy, memory, quota, label) in enumerate(cases):
        output = OUT/'runs'/label
        if not (output/'pair_lifecycle.json').exists():
            output.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
                '--trace', str(BASE/'routed/traces/qft/seed_42'/route/'requests.txt'),
                '--strategies', strategy, '--seeds', '60', '--total-memories', str(memory),
                '--compiler-memories', str(quota), '--generation-capacity', str(memory),
                '--seed-reference-memories', str(min(4, memory)), '--planner-lead-layers', '1',
                '--dynamic-lookahead-layers', '8', '--stop-after-workload', '--audit-events',
                '--record-chain-coverage', '--stop-time-s', '1000', '--output', str(output)]
            if strategy in ('continuous', 'adaptive-continuous'):
                command.append('--autonomous-cache-follows-compiler-memories')
            matrix.save(OUT/'supplement-progress.json', dict(stage='simulation', completed=index,
                total=len(cases), case=label, pid=__import__('os').getpid(), started=time.time()))
            matrix.save(output/'command.json', command)
            print('RUN', index+1, '/', len(cases), label, flush=True)
            with (output/'run.log').open('w') as log:
                subprocess.run(command, cwd=ROOT, env=matrix.environment(), stdout=log, stderr=subprocess.STDOUT, check=True)
        row = next(csv.DictReader((output/'summary.csv').open()))
        audit = json.loads((output/f'audit_{strategy}_60.json').read_text())
        assert not audit['violations'] and audit['completed_requests'] == audit['total_requests']
        rows.append(dict(route=route, memory=memory, quota=quota, label=label, **row))
        matrix.save(OUT/'supplement-results.json', rows)
    matrix.save(OUT/'supplement-progress.json', dict(stage='complete', completed=len(cases), total=len(cases)))


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.argv.remove('--worker'); worker()
    else:
        try:
            main()
        except Exception as exc:
            matrix.save(OUT/'supplement-failure.json', dict(error=repr(exc)))
            raise
