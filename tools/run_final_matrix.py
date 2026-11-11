"""Resumable 224-logical-qubit final matrix; CSV output, physical audits and progress."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import benchmark_matrix as matrix

CASES = {name: (strategy, slots, quota) for name, strategy, slots, quota in matrix.CASES}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(path)


def fingerprint():
    paths = [*ROOT.glob('ace/**/*.py'), *ROOT.glob('mapper/**/*.py'),
             *ROOT.glob('tools/routing_research/*.py'), ROOT/'tools/congestion_study/run_study.py',
             Path(__file__), ROOT/'tools/benchmark_matrix.py',
             ROOT/'config/final_config/grid_4x4_ace_3.json',
             *[ROOT/f'benchmarks/{w}/{w}_224.qasm' for w in matrix.WORKLOADS]]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def environment(engine, out):
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(map(str, [engine, ROOT, ROOT/'mapper']))
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    for key, name in [('TEMP', 'temp'), ('TMP', 'temp'), ('MPLCONFIGDIR', 'mpl-cache')]:
        folder = out/name; folder.mkdir(parents=True, exist_ok=True); env[key] = str(folder)
    return env


def command(trace, output, case, seed, args):
    strategy, slots, quota = CASES[case]
    if case == 'CD-unlimited': slots = quota = args.unlimited_slots
    cmd = [sys.executable, '-B', '-u', str(Path(__file__).resolve()), '--worker',
           '--trace', str(trace), '--strategies', strategy, '--seeds', str(seed),
           '--total-memories', str(slots), '--compiler-memories', str(quota),
           '--generation-capacity', str(slots), '--mesh', '4x4',
           '--seed-reference-memories', '4', '--planner-lead-layers', '2',
           '--dynamic-lookahead-layers', '2', '--preparation-priority', 'trace',
           '--dynamic-layer-basis', 'active', '--borrow-compiler-pairs',
           '--scheduler', 'per-qubit', '--admission', 'event', '--admission-priority', 'ready-first',
           '--demand-first', '--refill-on-release', '--empty-layer-gap-ms', '0.00001',
           '--compiler-reservation-ms', '50', '--stop-after-workload', '--audit-events',
           '--record-chain-coverage', '--stop-time-s', str(args.stop_time_s), '--output', str(output)]
    if args.autonomous_cache == 'quota': cmd.append('--autonomous-cache-follows-compiler-memories')
    return cmd


def worker():
    # Observe progress without injecting simulator events or changing simulated time.
    output = Path(sys.argv[sys.argv.index('--output')+1])
    def monitor():
        while True:
            time.sleep(5)
            frame = sys._current_frames().get(threading.main_thread().ident)
            while frame:
                if frame.f_code.co_name == 'run_parallel_experiment':
                    manager = frame.f_locals.get('request_manager')
                    if manager is not None:
                        save(output/'request_progress.json', dict(completed=len(manager.request_end_times),
                             simulation_ms=manager.timeline.now()/1e9))
                    break
                frame = frame.f_back
    threading.Thread(target=monitor, daemon=True).start()
    # Shared canonical pair observer; each worker handles exactly one case/seed.
    matrix.worker()


def verify_unlimited(folder, row, args):
    from ace.compiler.compiler_trace import parse_compiler_trace, plan_preparations
    meta = json.loads((folder/'metadata.json').read_text())
    trace = parse_compiler_trace(Path(meta['parameters']['trace']))
    def plan(slots):
        return plan_preparations(trace, strategy='dynamic', compiler_memories_per_core=slots,
            generation_capacity_per_core=slots, coherence_time_layers=10,
            dynamic_lookahead_layers=2, lead_layers=2, layer_basis='active', preparation_priority='trace')
    reference_slots = max(args.unlimited_slots*2, 2*len(trace.requests)+1)
    small, large = plan(args.unlimited_slots), plan(reference_slots)
    cap = json.loads((folder/f"capacity_dynamic_{row['seed']}.json").read_text())
    bound = max(cap['peak_booked_plus_outstanding_bound_per_node'].values(), default=0)
    # Blocked includes requests with no legal L-2 launch (the first two active
    # layers), even with infinite memory. Compare against a provably sufficient
    # offline bound instead of requiring that this count be zero.
    verified = small[0] == large[0] and small[1] == large[1] and small[2] < args.unlimited_slots and bound < args.unlimited_slots
    save(folder/'unlimited_verification.json', dict(verified=verified, slots=args.unlimited_slots,
         planner_peak=small[2], planner_blocked=small[1], physical_demand_bound=bound,
         reference_slots=reference_slots, reference_plan_identical=small[0] == large[0]))
    if not verified:
        raise ValueError('CD unlimited bound saturated; rerun in a NEW output with larger --unlimited-slots')


def result(folder, workload, route, case, seed, args):
    with (folder/'summary.csv').open() as stream:
        row = next(csv.DictReader(stream))
    audit = json.loads((folder/f"audit_{row['strategy']}_{seed}.json").read_text())
    if audit['violations'] or audit['completed_requests'] != audit['total_requests']:
        raise ValueError(f'Incomplete/invalid physical audit: {folder}')
    if int(row['requests']) != int(row['completed_requests']):
        raise ValueError(f'Incomplete summary: {folder}')
    life = json.loads((folder/'pair_lifecycle.json').read_text())
    statuses = life['statuses']
    if case.startswith('CD'):
        generated, used, expired, cancelled, unused = [int(float(row[k])) for k in
            ('generated_compiler_pairs','utilized_compiler_pairs','expired_compiler_pairs',
             'cancelled_compiler_pairs','remaining_compiler_pairs')]
    else:
        generated = life['generated']; used = statuses.get('used', 0)
        expired = sum(v for k,v in statuses.items() if k.startswith('expired'))
        cancelled = sum(v for k,v in statuses.items() if k.startswith('cancelled'))
        unused = statuses.get('remaining', 0)
    if generated != used+expired+cancelled+unused:
        raise ValueError(f'Pair conservation failed: {folder}')
    if life['observed_requests'] != int(row['requests']):
        raise ValueError(f'Coverage observer missed requests: {folder}')
    if case == 'CD-unlimited': verify_unlimited(folder, row, args)
    waste = expired+cancelled+unused
    return dict(workload=workload, route=route, case=case, physics_seed=seed,
        latency_ms=float(row['average_request_latency_ms']),
        makespan_ms=float(row['end_to_end_latency_ms']),
        avg_fidelity=float(row['average_delivered_epr_fidelity']) if row['average_delivered_epr_fidelity'] else '',
        coverage=life['ready_requests']/life['observed_requests'] if life['observed_requests'] else '',
        pregenerated_pairs=generated, used_pairs=used, eviction_pairs=0,
        expiry_pairs=expired, cancelled_pairs=cancelled, unused_pairs=unused,
        wasted_pairs=waste, wastage=waste/generated if generated else '',
        expiry_fraction=expired/generated if generated else '',
        cancelled_fraction=cancelled/generated if generated else '',
        unused_fraction=unused/generated if generated else '',
        audit_violations=0, source=str(folder), **{f'raw_{k}':v for k,v in row.items()})


def export(out, rows):
    if not rows: return
    target = out/'results.csv'; temp = out/'results.csv.tmp'
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with temp.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    try: temp.replace(target)
    except PermissionError:
        raise RuntimeError(f'Close {target} in Excel, then rerun to resume.')
    save(out/'results.json', rows)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT/'output/final-matrix-224')
    p.add_argument('--workloads', nargs='+', choices=matrix.WORKLOADS, default=list(matrix.WORKLOADS))
    p.add_argument('--routes', nargs='+', choices=['history','xy'], default=['history','xy'])
    p.add_argument('--cases', nargs='+', choices=list(CASES), default=list(CASES))
    p.add_argument('--seeds', default='60', help='Comma-separated physics seeds; mapping seed stays 42')
    p.add_argument('--jobs', type=int, default=1)
    p.add_argument('--engine-root', type=Path, default=ROOT/'third_party/SeQUeNCe')
    p.add_argument('--autonomous-cache', choices=['quota','legacy3'], default='quota')
    p.add_argument('--unlimited-slots', type=int, default=256)
    p.add_argument('--stop-time-s', type=float, default=1000)
    p.add_argument('--dry-run', action='store_true')
    return p


def main():
    args = parser().parse_args(); out = args.output.resolve()
    seeds = list(dict.fromkeys(int(s) for s in args.seeds.split(',')))
    if args.jobs < 1 or args.unlimited_slots < 8: raise ValueError('Invalid jobs/unlimited-slots')
    jobs = [(w,r,c,s) for w in dict.fromkeys(args.workloads) for r in dict.fromkeys(args.routes)
            for c in dict.fromkeys(args.cases) for s in seeds]
    spec = dict(workloads=args.workloads, routes=args.routes, cases=args.cases, seeds=seeds,
        mesh='4x4', data_slots_per_core=16, initially_occupied_per_core=14, logical_qubits=224,
        mapping_seed=42, lead_layers=2, preparation_priority='trace', borrow_and_refill=True,
        autonomous_cache=args.autonomous_cache, unlimited_slots=args.unlimited_slots,
        stop_time_s=args.stop_time_s, total_runs=len(jobs), sources=fingerprint())
    if args.dry_run:
        print(json.dumps(spec, indent=2)); return
    engine = args.engine_root.resolve()
    sys.path.insert(0, str(engine))
    if not (engine/'sequence/__init__.py').exists():
        raise ValueError('Initialize engine: git submodule update --init --recursive; or set --engine-root')
    env = environment(engine, out)
    subprocess.run([sys.executable, '-c', "import sequence; assert sequence.__version__ == '0.8.1', sequence.__version__"],
                   cwd=ROOT, env=env, check=True)
    spec['engine_sources'] = {str(p.relative_to(engine)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(engine.glob('sequence/**/*.py'))}
    previous = out/'specification.json'
    if previous.exists() and json.loads(previous.read_text()) != spec:
        raise ValueError('Output specification/source changed. Use a new --output directory.')
    save(previous, spec)
    # Existing generator fixes T-HQA mapping seed 42, 16 data slots/core, 2 spare slots,
    # 224 logical qubits; route both variants from the SAME placement/migrations.
    matrix.OUT = out
    for w in dict.fromkeys(args.workloads):
        print(f'MAPPING {w} (16 cores, 14 occupied + 2 spare data slots/core)', flush=True)
        subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--prepare', str(out), w],
                       cwd=ROOT, env=env, check=True)
    rows=[]; pending=[]
    for job in jobs:
        w,r,c,s=job; folder=out/'runs'/w/r/c/f'seed_{s}'
        trace=out/'routed/traces'/w/'seed_42'/r/'requests.txt'
        from ace.compiler.compiler_trace import parse_compiler_trace
        from collections import Counter
        parsed=parse_compiler_trace(trace)
        mapping=json.loads((out/'inputs'/w/'seed_42'/'mapping_summary.json').read_text())
        # Export header is 20 total slots (16 data + 4 reference comm. slots).
        # Mapper validation, rather than that combined header, enforces data capacity.
        if (parsed.core_count,parsed.qubit_slots_per_core,parsed.qubit_count)!=(16,20,224) or \
                mapping['data_capacity_enforced'] != 16 or mapping['maximum_data_occupancy'] > 16 or \
                sorted(Counter(parsed.initial_placement.values()).values()) != [14]*16:
            raise ValueError(f'Trace does not match the requested 16-core/224-qubit architecture: {trace}')
        digest=hashlib.sha256(trace.read_bytes()).hexdigest()
        identity=dict(job=list(job), trace_sha256=digest)
        marker=folder/'validated.json'
        if marker.exists():
            if json.loads(marker.read_text()) != identity: raise ValueError(f'Changed trace/job: {folder}')
            rows.append(result(folder,*job,args))
        else: pending.append((job,folder,trace,identity))
    export(out,rows); active=[]; completed=len(rows); last=0
    try:
        while pending or active:
            while pending and len(active)<args.jobs:
                job,folder,trace,identity=pending.pop(0);folder.mkdir(parents=True,exist_ok=True)
                cmd=command(trace,folder,job[2],job[3],args);save(folder/'command.json',cmd)
                (folder/'request_progress.json').unlink(missing_ok=True)
                log=(folder/'run.log').open('w');proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                active.append((job,folder,identity,proc,log))
            for job,folder,identity,proc,log in list(active):
                code=proc.poll()
                if code is None: continue
                log.close();active.remove((job,folder,identity,proc,log))
                if code: raise RuntimeError(f'{job} failed ({code}); see {folder / "run.log"}')
                if fingerprint()!=spec['sources']:
                    raise RuntimeError('Source changed during simulation; use a new output directory.')
                rows.append(result(folder,*job,args));export(out,rows)
                save(folder/'validated.json',identity);completed+=1
            if time.time()-last>=5 or not active:
                details=[]
                for job,folder,_,_,_ in active:
                    p=folder/'request_progress.json'
                    try: count=json.loads(p.read_text())['completed']
                    except (OSError,ValueError,KeyError): count=0
                    details.append(f'{"/".join(map(str,job))}: {count:,} requests')
                percent=completed/len(jobs);bar='#'*int(percent*24)+'-'*(24-int(percent*24))
                print(f'[{bar}] {completed}/{len(jobs)} ({percent:.1%}) | '+ '; '.join(details),flush=True)
                save(out/'progress.json',dict(completed=completed,total=len(jobs),fraction=percent,
                     running=details,stage='running' if active or pending else 'complete'));last=time.time()
            if active: time.sleep(1)
    finally:
        for _,_,_,proc,log in active:
            proc.terminate();proc.wait();log.close()
    print(f'DONE: {out / "results.csv"}',flush=True)


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.argv.remove('--worker');worker()
    elif '--prepare' in sys.argv:
        matrix.OUT=Path(sys.argv[2]);matrix.prepare(sys.argv[3])
    else:
        main()
