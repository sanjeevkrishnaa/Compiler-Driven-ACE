"""Report the controlled QAOA History active-layer 2-16 timing experiment."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
from ace.compiler.compiler_trace import parse_compiler_trace, plan_preparations


def main():
    root = Path.cwd()
    baseline = root / 'output/five-workload-c8-2026-11-03/simulation/qaoa/history'
    study = root / 'output/qaoa-history-active16-10ns-2026-11-03'
    candidate = study / 'm8'
    dest = root / 'docs/research/compiler-pregeneration/active16-10ns-2026-11-03'
    dest.mkdir(parents=True, exist_ok=True)
    command = json.loads((candidate / 'command.json').read_text())
    trace_path = Path(command[command.index('--trace') + 1])
    trace = parse_compiler_trace(trace_path)
    rank = {layer: i for i, layer in enumerate(sorted({r.layer for r in trace.requests}))}
    by_id = {r.request_id: r for r in trace.requests}
    schedule, blocked, peak = plan_preparations(
        trace, strategy='dynamic', compiler_memories_per_core=8,
        generation_capacity_per_core=8, coherence_time_layers=17,
        dynamic_lookahead_layers=16, lead_layers=2, layer_basis='active')
    ages = Counter(rank[by_id[s.request_id].layer] - rank[s.generation_layer] for s in schedule)
    assert all(2 <= age <= 16 for age in ages)
    shorter = plan_preparations(
        trace, strategy='dynamic', compiler_memories_per_core=8,
        generation_capacity_per_core=8, coherence_time_layers=10,
        dynamic_lookahead_layers=8, lead_layers=2, layer_basis='active')
    rows, audits = [], []
    for label, folder in [('Original: logical 2-8, 5 ms', baseline), ('Active 2-16, 10 ns', candidate)]:
        summary = next(r for r in csv.DictReader((folder / 'summary.csv').open()) if r['strategy'] == 'dynamic')
        assert int(summary['requests']) == len(trace.requests) and float(summary['completion_rate']) == 1
        audit = json.loads((folder / 'audit_dynamic_60.json').read_text())
        assert not audit['violations']
        audits.append(dict(configuration=label, **audit))
        coverage = json.loads((folder / 'chain_coverage_dynamic_60.json').read_text())
        counts = Counter(r['coverage'] for r in coverage)
        row = dict(configuration=label, latency_ms_per_hop=float(summary['request_latency_mean_ms']),
                   fidelity_percent=100 * float(summary['average_delivered_epr_fidelity']),
                   makespan_s=float(summary['end_to_end_latency_ms']) / 1000,
                   ready_at_hop_arrival_percent=100 * float(summary['pregenerated_success_rate']),
                   chains=len(coverage), requests=int(summary['requests']),
                   scheduled_preparations=int(summary['scheduled_preparations']),
                   planner_blocked_preparations=int(summary['planner_blocked_preparations']),
                   admission_wait_ms=float(summary['average_admission_wait_ms']),
                   storage_time_ms=float(summary['average_storage_time_ms']))
        for k in ('full', 'partial', 'zero'):
            row[k + '_count'] = counts[k]
            row[k + '_percent'] = 100 * counts[k] / len(coverage)
        rows.append(row)
    assert rows[0]['chains'] == rows[1]['chains']
    meta = json.loads((candidate / 'metadata.json').read_text())
    p = meta['parameters']
    for key, expected in dict(total_memories=8, compiler_memories=8, generation_capacity=8,
                              dynamic_layer_basis='active', dynamic_lookahead_layers=16,
                              planner_lead_layers=2, coherence_time_layers=17,
                              empty_layer_gap_ms=0.00001, compiler_reservation_ms=50,
                              layer_activation_order='execution-first').items():
        assert p[key] == expected, (key, p[key])
    assert rows[1]['scheduled_preparations'] == len(schedule)
    assert rows[1]['planner_blocked_preparations'] == blocked
    proof = dict(active_layers=len(rank), logical_layers=trace.layer_count,
                 scheduled=len(schedule), blocked=blocked, peak_planner_slots=peak,
                 active_lookback_histogram=dict(sorted(ages.items())),
                 active_2_8_and_2_16_plans_identical=(shorter == (schedule, blocked, peak)),
                 trace_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest())
    (dest / 'planner_verification.json').write_text(json.dumps(proof, indent=2))
    (dest / 'audits.json').write_text(json.dumps(audits, indent=2))
    with (dest / 'metrics.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    table = '| Configuration | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Chain readiness: full / partial / zero (%) | Hop readiness (%) |\n| --- | ---: | ---: | ---: | --- | ---: |\n'
    for r in rows:
        coverage = ' / '.join(f"{r[k + '_percent']:.2f}" for k in ('full', 'partial', 'zero'))
        table += f"| {r['configuration']} | {r['latency_ms_per_hop']:.4f} | {r['fidelity_percent']:.3f} | {r['makespan_s']:.4f} | {coverage} | {r['ready_at_hop_arrival_percent']:.2f} |\n"
    notes = '''\nSame 208-qubit QAOA History trace, 4x4 mesh, T-HQA mapping seed42,
physics seed60, 14 data slots/core, 8 communication memories, compiler quota8,
generation capacity8, execution-first ready-first admission, all-chain hops,
handoff, 50ms reservation lifetime and unchanged physical coherence.

The candidate uses communication-active layers as its planning axis, skips empty
layers when choosing preparation launch layers, and assigns each empty logical
layer 10ns (0.00001ms). Candidate layers are searched nearest first, from two to
sixteen active layers before demand; capacity constraints determine selection.
Planner age cutoff is17 instead of10 to permit a16-layer lead (strict age < cutoff).
This does not change physical coherence or reservation lifetime. Runtime code and
default settings are unchanged; this is a command-line experiment.

Latency is eligibility-to-EPR-delivery per hop, including admission wait. Makespan
uses the same end_to_end_latency_ms metric in both trials. Chain readiness is
sampled at layer opening before admission/preparation. Hop readiness is the
pregenerated hit fraction at individual hop arrival; it uses a different sampling
time and denominator. Fidelity measures delivered EPR pairs, not circuit outputs.
These are single-seed results; the 10ns gap is a timing assumption, not a local
gate simulation. Commands, raw data and source fingerprints are retained.
'''
    (dest / 'README.md').write_text(table + notes, encoding='utf-8')
    print(table)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
