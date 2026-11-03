"""Compare controlled quota and preparation-policy trials using hop readiness."""
from pathlib import Path
import csv
import json


def main():
    root = Path.cwd()
    study = root / 'output/qaoa-preparation-policy-2026-11-03'
    output = root / 'docs/research/compiler-pregeneration/preparation-policy-2026-11-03'
    output.mkdir(parents=True, exist_ok=True)
    selected = list(csv.DictReader((study / 'all_seeds.csv').open()))
    names = ['odg', 'quota4', 'quota5', 'quota6', 'quota7', 'demand6', 'release6', 'runtime6']
    assert {r['configuration'] for r in selected} == set(names)
    rows, audits = [], []
    hashes = None
    for name in names:
        trial = next(r for r in selected if r['configuration'] == name)
        folder = Path(trial['folder'])
        meta = json.loads((folder / 'metadata.json').read_text())
        if hashes is None:
            hashes = meta['source_sha256']
        assert meta['source_sha256'] == hashes
        p = meta['parameters']
        for k, v in dict(total_memories=8, generation_capacity=8, empty_layer_gap_ms=0.00001,
                         dynamic_layer_basis='active', dynamic_lookahead_layers=16,
                         planner_lead_layers=2, coherence_time_layers=17,
                         compiler_reservation_ms=50, layer_activation_order='execution-first').items():
            assert p[k] == v, (name, k, p[k])
        strategy = trial['strategy']
        if name in ('quota6', 'odg'):
            old_folder = 'm8-c6' if name == 'quota6' else 'odg'
            old = next(csv.DictReader((root / 'output/qaoa-history-active16-10ns-2026-11-03' / old_folder / 'summary.csv').open()))
            for key in ('request_latency_mean_ms', 'end_to_end_latency_ms',
                        'average_delivered_epr_fidelity', 'pregenerated_success_rate'):
                assert trial[key] == old[key], ('control regression', name, key)
        audit = json.loads((folder / f'audit_{strategy}_60.json').read_text())
        assert not audit['violations'] and audit['completed_requests'] == audit['total_requests'] == 30232
        audits.append(dict(configuration=name, **audit))
        capacity = json.loads((folder / f'capacity_{strategy}_60.json').read_text())
        peak = max(capacity['peak_compiler_bookings_per_node'].values(), default=0)
        assert peak <= int(trial['quota'])
        rows.append(dict(configuration=name, compiler_quota=int(trial['quota']),
                         latency_ms_per_hop=float(trial['request_latency_mean_ms']),
                         makespan_s=float(trial['end_to_end_latency_ms']) / 1000,
                         fidelity_percent=100 * float(trial['average_delivered_epr_fidelity']),
                         hop_readiness_percent=100 * float(trial['pregenerated_success_rate']),
                         admission_wait_ms=float(trial['average_admission_wait_ms']),
                         peak_compiler_bookings=peak, retries=int(trial['total_retries']),
                         generated_compiler_pairs=int(trial['generated_compiler_pairs']),
                         waste_percent=float(trial['compiler_waste_percentage'])))
    with (output / 'metrics.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (output / 'audits.json').write_text(json.dumps(audits, indent=2))
    labels = dict(odg='ODG', quota4='Quota 4', quota5='Quota 5', quota6='Quota 6', quota7='Quota 7',
                  demand6='Quota 6 + demand guard', release6='Quota 6 + guard + release/dependency priority',
                  runtime6='Quota 6 + guard + release/dependency + runtime planner')
    table = '| Configuration | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Hop readiness (%) | Admission wait (ms/hop) |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'
    for r in rows:
        table += f"| {labels[r['configuration']]} | {r['latency_ms_per_hop']:.4f} | {r['fidelity_percent']:.3f} | {r['makespan_s']:.4f} | {r['hop_readiness_percent']:.2f} | {r['admission_wait_ms']:.4f} |\n"
    best = min(rows[1:], key=lambda r: r['latency_ms_per_hop'])
    fastest = min(rows[1:], key=lambda r: r['makespan_s'])
    (output / 'selection.json').write_text(json.dumps(dict(best_latency=best, best_makespan=fastest, trials=8), indent=2))
    (output / 'best_latency_command.json').write_text((study / best['configuration'] / 'command.json').read_text())
    notes = '''\n208-qubit QAOA, same frozen History route and mapping seed42, 4x4 mesh,
14 data slots/core, eight physical communication memories/core, physics seed60.
All trials use10ns empty gaps, active lookback2-16, planner age cutoff17, generation
budget8, 50ms compiler reservation lifetime, execution-first ready-first admission,
all-chain preparation and native handoff. Physical coherence unchanged. Hop
readiness is ready-pair hits at individual hop eligibility; chain readiness is
deliberately omitted. Latency includes admission wait. Fidelity is delivered EPR
fidelity, not circuit output fidelity. Makespan is end_to_end_latency_ms /1000.

Quota-only trials use the original offline planner. Demand guard is an existing
optional control that blocks preparation sharing endpoints with waiting demand
and checks promised application slots. Release mode reuses existing memory-release
notifications, now coalesces bursts into one wake after application admission,
and ranks preparation by target layer and outstanding predecessor starts. This
is a dependency proxy, not a calibrated physical-time prediction. The1ms retry
remains a fallback for missed/non-memory wakeups; resource releases accelerate it.
Runtime planning supplies launch candidates without offline storage reservations;
the runtime enforces storage quota and a per-core eight-launch budget per active
layer. Failed locally booked handshakes count toward this launch budget. A1ms
retry or active-layer transition can revisit deferred candidates. All hops remain
eligible; no first-hop-only policy or pair borrowing is enabled.

The benchmark re-runs ODG and quota6 with the new source to expose regressions.
All eight trials must complete30232 requests, pass audits, share source hashes,
and respect compiler booking limits. This is one workload and physics seed, not
an across-workload guarantee. Defaults remain unchanged: new priority is opt-in.
Exact commands, raw pair/timing/admission records and metadata are retained.
'''
    (output / 'README.md').write_text(table + notes, encoding='utf-8')
    print(table)
    print('Best latency configuration:', best['configuration'])


if __name__ == '__main__':
    main()
