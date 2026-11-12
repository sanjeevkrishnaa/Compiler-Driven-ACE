"""Sequential, resumable 224-qubit benchmark matrix. No simulator-policy changes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'benchmark-matrix-224-2026-11-04'
WORKLOADS = ('bv', 'dj', 'ghz', 'graphstate', 'bmw_quark_cardinality',
             'draper_qft_adder', 'qft', 'qaoa', 'qpeexact', 'bmw_quark_copula')
CASES = [('ODG-4', 'on-demand', 4, 3), ('CGP-4', 'continuous', 4, 3),
         ('ACGP-4', 'adaptive-continuous', 4, 3), ('CD-4', 'dynamic', 4, 3),
         ('ODG-8', 'on-demand', 8, 6), ('CGP-8', 'continuous', 8, 6),
         ('ACGP-8', 'adaptive-continuous', 8, 6), ('CD-8', 'dynamic', 8, 6),
         ('CD-unlimited', 'dynamic', 256, 256)]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')
    temporary.replace(path)


def environment():
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(map(str, [ROOT / 'third_party/SeQUeNCe', ROOT, ROOT / 'mapper']))
    env['PYTHONUNBUFFERED'] = '1'
    return env


def worker():
    """Read-only observers supply pair lifecycle metrics without changing scheduling."""
    sys.path[:0] = [str(ROOT / 'third_party/SeQUeNCe'), str(ROOT)]
    from ace.protocols.adaptive_continuous import AdaptiveContinuousProtocol
    from ace.simulation.request_scheduler import QubitOrderedRequestManager as PerQubitRequestManager
    from ace.cli import run_trace_comparison as cli
    # Observations are canonical physical pairs, not double-counted endpoints.
    live, records, request_ready = {}, [], {}
    def key(pair):
        return tuple(sorted(tuple(e) for e in pair))
    def finish(pair, status, now):
        record = live.pop(key(pair), None)
        if record is not None:
            record.update(status=status, ended_ps=now)
    original_add = AdaptiveContinuousProtocol.add_generated_entanglement_pair
    def add(self, pair, reservation=None):
        original_add(self, pair, reservation)
        k = key(pair)
        if k not in live:
            rec = dict(pair=k, created_ps=self.owner.timeline.now(), status='remaining')
            live[k] = rec
            records.append(rec)
    AdaptiveContinuousProtocol.add_generated_entanglement_pair = add
    original_remove = AdaptiveContinuousProtocol.remove_entanglement_pair
    def remove(self, pair):
        original_remove(self, pair)
        finish(pair, 'used', self.owner.timeline.now())
    AdaptiveContinuousProtocol.remove_entanglement_pair = remove
    original_expire = AdaptiveContinuousProtocol.note_memory_expiration
    def expire(self, memory, reason='memory_coherence'):
        pairs = [p for p in self.generated_entanglement_pairs if memory.name in (p[0][1], p[1][1])]
        original_expire(self, memory, reason)
        for p in pairs:
            finish(p, ('cancelled_' if reason == 'request_completed' else 'expired_') + reason, self.owner.timeline.now())
    AdaptiveContinuousProtocol.note_memory_expiration = expire
    original_release = AdaptiveContinuousProtocol.adaptive_memory_used_minus_one
    def release(self, memory):
        pairs = [p for p in self.generated_entanglement_pairs if memory.name in (p[0][1], p[1][1])]
        original_release(self, memory)
        for p in pairs:
            if p not in self.generated_entanglement_pairs:
                finish(p, 'expired_reservation', self.owner.timeline.now())
    AdaptiveContinuousProtocol.adaptive_memory_used_minus_one = release
    original_submit = PerQubitRequestManager._submit_and_arm
    def submit(self, request, now):
        rid, source, dest = request[:3]
        if rid not in request_ready:
            if self.compiler_controller is not None:
                ready = self.compiler_controller.request_has_ready_pair(rid)
            else:
                protocol = self.name_to_apps[source].node.adaptive_continuous
                remote = self.name_to_apps[dest].node.adaptive_continuous
                ready = any(p[0][0] == source and p[1][0] == dest
                            and (p[1], p[0]) in remote.generated_entanglement_pairs
                            and live.get(key(p), {}).get('created_ps', now) < now
                            for p in protocol.generated_entanglement_pairs)
            request_ready[rid] = bool(ready)
        return original_submit(self, request, now)
    PerQubitRequestManager._submit_and_arm = submit
    cli.main()
    output = Path(sys.argv[sys.argv.index('--output') + 1])
    if output.name == 'CD-unlimited':
        parameters = json.loads((output / 'metadata.json').read_text())['parameters']
        from ace.compiler.compiler_trace import parse_compiler_trace, plan_preparations
        trace = parse_compiler_trace(Path(sys.argv[sys.argv.index('--trace') + 1]))
        def plan(capacity):
            return plan_preparations(trace, strategy='dynamic', compiler_memories_per_core=capacity,
                generation_capacity_per_core=capacity, coherence_time_layers=10,
                dynamic_lookahead_layers=parameters['dynamic_lookahead_layers'],
                lead_layers=parameters['planner_lead_layers'], layer_basis='active',
                preparation_priority='chain-length')
        current, doubled = plan(256), plan(512)
        capacity = json.loads((output / 'capacity_dynamic_60.json').read_text())
        bound = max(capacity['peak_booked_plus_outstanding_bound_per_node'].values(), default=0)
        verified = current[0] == doubled[0] and current[2] < 256 and bound < 256
        save(output / 'unlimited_verification.json', dict(verified=verified,
            actual_slots=256, doubled_plan_slots=512, planner_peak=current[2],
            identical_plan_when_doubled=current[0] == doubled[0], physical_demand_bound=bound))
        if not verified:
            raise RuntimeError(f'Finite memory bound is not verified as unlimited: {output}')
    statuses = {}
    for rec in records:
        statuses[rec['status']] = statuses.get(rec['status'], 0) + 1
    save(output / 'pair_lifecycle.json', dict(generated=len(records), statuses=statuses,
         ready_requests=sum(request_ready.values()), observed_requests=len(request_ready),
         readiness_definition='cached physical pair before first application submission; not guaranteed adoption',
         eviction_count=0, eviction_note='No separate cache eviction operation exists; removals are use or expiry.'))


def routed_directory(out, capacity=4):
    """Keep legacy C4 traces separate from capacity-matched reroutes."""
    return out / ('routed' if capacity == 4 else f'routed-c{capacity}')


def prepare(workload, capacity=4):
    """Map the actual committed QASM once, then freeze two routing variants."""
    sys.path[:0] = [str(ROOT), str(ROOT / 'mapper'), str(ROOT / 'tools/routing_research')]
    from tools.congestion_study import run_study as generator
    import heavy_routing
    folder = OUT / 'inputs' / workload / 'seed_42'
    if not (folder / 'mapping_summary.json').exists():
        qasm = ROOT / 'benchmarks' / workload / f'{workload}_224.qasm'
        args = generator.parser().parse_args(['--mesh', '4x4', '--total-qubits', '320',
            '--memory-slots', '4', '--logical-qubits', '224', '--spare-data-slots-per-core', '2',
            '--placer', 'T-HQA', '--mapping-only'])
        architecture = generator.configure(args)
        circuit, ir, source = generator.load_circuit(workload, qasm, 224, args, {})
        folder.mkdir(parents=True, exist_ok=True)
        generator.map_and_export(ir, architecture, 42, args, folder)
        save(folder / 'source.json', source)
    if capacity < 1:
        raise ValueError('Routing capacity must be positive')
    routed = routed_directory(OUT, capacity)
    marker = routed / 'routing_specification.json'
    routing_spec = dict(capacity=capacity, history='cumulative-all-past-layers')
    if marker.exists() and json.loads(marker.read_text()) != routing_spec:
        raise ValueError(f'Routing specification changed: {routed}')
    if not marker.exists() and capacity != 4 and (routed/'traces').exists():
        raise ValueError(f'Unverified routing capacity: {routed}; use a new output')
    # Persist before building so an interrupted build can resume with a known C.
    save(marker, routing_spec)
    if not all((routed / 'traces' / workload / 'seed_42' / r / 'requests.txt').exists()
               for r in ('xy', 'history')):
        routed.mkdir(parents=True, exist_ok=True)
        heavy_routing.build(routed, OUT / 'inputs', ('xy', 'history'), (workload,), capacity=capacity)


def collect():
    rows = []
    for path in sorted((OUT / 'runs').glob('*/*/*/summary.csv')):
        row = next(csv.DictReader(path.open()))
        workload, route, case = path.parent.relative_to(OUT / 'runs').parts
        life = json.loads((path.parent / 'pair_lifecycle.json').read_text())
        statuses = life['statuses']
        row = dict(workload=workload, route=route, case=case, **row,
                   cached_ready_requests=life['ready_requests'],
                   observed_requests=life['observed_requests'],
                   unique_generated_pairs=life['generated'],
                   unique_used_pairs=statuses.get('used', 0),
                   unique_expired_pairs=sum(v for k, v in statuses.items() if k.startswith('expired')),
                   unique_remaining_pairs=statuses.get('remaining', 0),
                   source=str(path.relative_to(ROOT)))
        rows.append(row)
    save(OUT / 'results.json', rows)
    if rows:
        with (OUT / 'results.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    save(OUT / 'specification.json', dict(workloads=WORKLOADS, cases=CASES, routes=['xy', 'history'],
        mapping_seed=42, physics_seed=60, logical_qubits=224, data_slots_per_core=16,
        initial_occupied_data_slots=14, total_runs=180,
        autonomous_cache_limit=3, generation_capacity='physical communication memory count',
        cd_policy='main: async, guard, chain-length, 2-8 active layers, 10 ns empty layers',
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()))
    completed = len(collect())
    for workload in WORKLOADS:
        print('PREPARE', workload, flush=True)
        save(OUT / 'progress.json', dict(stage='mapping', workload=workload, completed=completed, total=180))
        prepare(workload)
        for route in ('xy', 'history'):
            trace = OUT / 'routed/traces' / workload / 'seed_42' / route / 'requests.txt'
            for case, strategy, memory, quota in CASES:
                output = OUT / 'runs' / workload / route / case
                if (output / 'pair_lifecycle.json').exists() and (output / 'summary.csv').exists():
                    continue
                output.mkdir(parents=True, exist_ok=True)
                save(OUT / 'progress.json', dict(stage='simulation', workload=workload, route=route,
                     case=case, completed=completed, total=180, started=time.time()))
                cmd = [sys.executable, '-u', str(Path(__file__).resolve()), '--worker', '--trace', str(trace),
                       '--strategies', strategy, '--seeds', '60', '--total-memories', str(memory),
                       '--compiler-memories', str(quota), '--generation-capacity', str(memory),
                       '--seed-reference-memories', '4', '--stop-after-workload', '--audit-events',
                       '--record-chain-coverage', '--stop-time-s', '1000', '--output', str(output)]
                save(output / 'command.json', cmd)
                print('RUN', workload, route, case, flush=True)
                with (output / 'run.log').open('w') as log:
                    code = subprocess.run(cmd, cwd=ROOT, env=environment(), stdout=log, stderr=subprocess.STDOUT).returncode
                if code:
                    raise RuntimeError(f'{workload}/{route}/{case} failed ({code}); see {output / "run.log"}')
                audit = json.loads((output / f'audit_{strategy}_60.json').read_text())
                if audit['violations'] or audit['completed_requests'] != audit['total_requests']:
                    raise RuntimeError(f'Invalid/incomplete run: {output}')
                completed = len(collect())
                print('DONE', completed, '/180', flush=True)
                if (OUT / 'pause_after_run').exists():
                    save(OUT / 'progress.json', dict(stage='paused-at-checkpoint', completed=completed, total=180))
                    return
        export_workbook()
    export_workbook()
    save(OUT / 'progress.json', dict(stage='complete', completed=completed, total=180))


def export_workbook():
    # Verify every completed row against its physical audit and common source.
    source = None
    for path in sorted((OUT / 'runs').glob('*/*/*/summary.csv')):
        row = next(csv.DictReader(path.open()))
        meta = json.loads((path.parent / 'metadata.json').read_text())
        audit = json.loads((path.parent / f'audit_{row["strategy"]}_60.json').read_text())
        if audit['violations'] or audit['completed_requests'] != audit['total_requests']:
            raise RuntimeError(f'Cannot publish incomplete/invalid row: {path}')
        hashes = meta['source_sha256']
        if source is None:
            source = hashes
        elif source != hashes:
            raise RuntimeError('Simulator source changed during the matrix; comparisons require review.')
        if path.parent.name == 'CD-unlimited':
            from ace.compiler.compiler_trace import parse_compiler_trace, plan_preparations
            trace = parse_compiler_trace(Path(meta['trace']))
            def plan(capacity):
                return plan_preparations(trace, strategy='dynamic', compiler_memories_per_core=capacity,
                    generation_capacity_per_core=capacity, coherence_time_layers=10,
                    dynamic_lookahead_layers=8, lead_layers=2, layer_basis='active',
                    preparation_priority='chain-length')
            small, large = plan(256), plan(512)
            capacity = json.loads((path.parent / 'capacity_dynamic_60.json').read_text())
            bound = max(capacity['peak_booked_plus_outstanding_bound_per_node'].values(), default=0)
            verified = small[0] == large[0] and small[2] < 256 and bound < 256
            save(path.parent / 'unlimited_verification.json', dict(verified=verified,
                actual_slots=256, doubled_plan_slots=512, planner_peak=small[2],
                identical_plan_when_doubled=small[0] == large[0], physical_demand_bound=bound))
            if not verified:
                raise RuntimeError(f'Unlimited capacity not verified: {path}')
    node = Path(r'C:\Users\sanje\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
    with (OUT / 'workbook.log').open('w') as log:
        subprocess.run([str(node), str(OUT / 'build_workbook.mjs')], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True)


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.argv.remove('--worker')
        worker()
    else:
        try:
            main()
        except Exception as exc:
            save(OUT / 'failure.json', dict(error=repr(exc), time=time.time()))
            raise
