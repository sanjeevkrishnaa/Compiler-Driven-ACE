"""Compare stored C=8 metrics with capacity-verified unbounded-memory runs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    baseline = [dict(r) for r in csv.DictReader(args.baseline.open()) if r['strategy'] == 'dynamic']
    selected = list(csv.DictReader((args.study / 'all_seeds.csv').open()))
    assert len(baseline) == len(selected) == 10
    reference = json.loads((args.study / 'reference_node_seeds.json').read_text())
    planner = json.loads((args.study / 'planner_verification.json').read_text())
    assert len(planner) == 10 and all(r['finite_matches_unconstrained'] for r in planner)
    output, audits, reasons, bounds = [], [], [], []
    hashes = None
    for workload in ('qft', 'qpeexact', 'qaoa', 'draper_qft_adder', 'quantum_volume'):
        for route in ('xy', 'history'):
            old = next(dict(r) for r in baseline if r['workload'] == workload and r['route'] == route)
            old.update(memory='8', physical_capacity=8, compiler_quota=8, peak_capacity_bound=None)
            output.append(old)
            trial = next(r for r in selected if r['workload'] == workload and r['route'] == route)
            folder = Path(trial['folder'])
            meta = json.loads((folder / 'metadata.json').read_text())
            parameters = meta['parameters']
            capacity = int(trial['capacity'])
            assert parameters['total_memories'] == parameters['compiler_memories'] == capacity
            assert parameters['generation_capacity'] == 8 and parameters['seed_reference_memories'] == 8
            assert parameters['compiler_reservation_ms'] == 50 and parameters['empty_layer_gap_ms'] == 5
            assert parameters['planner_lead_layers'] == 2 and parameters['dynamic_layer_basis'] == 'logical'
            assert parameters['layer_activation_order'] == 'execution-first' and not parameters['demand_first']
            if hashes is None:
                hashes = meta['source_sha256']
            assert meta['source_sha256'] == hashes
            audit = json.loads((folder / 'audit_dynamic_60.json').read_text())
            assert not audit['violations'] and audit['completed_requests'] == audit['total_requests']
            audits.append(dict(workload=workload, route=route, **audit))
            diagnostic = json.loads((folder / 'capacity_dynamic_60.json').read_text())
            assert diagnostic['node_seeds'] == reference
            peak = max(diagnostic['peak_booked_plus_outstanding_bound_per_node'].values())
            compiler_peak = max(diagnostic['peak_compiler_bookings_per_node'].values())
            assert peak < capacity and compiler_peak < capacity
            for reason in ('local_memory_quota', 'local_timecard', 'remote_memory_or_timecard'):
                assert diagnostic['compiler_rejection_reasons'].get(reason, 0) == 0
            bounds.append(dict(workload=workload, route=route, capacity=capacity, peak_bound=peak,
                               compiler_peak=compiler_peak, **diagnostic))
            row = next(csv.DictReader((folder / 'summary.csv').open()))
            assert row['seed'] == '60' and row['strategy'] == 'dynamic' and float(row['completion_rate']) == 1
            coverage = json.loads((folder / 'chain_coverage_dynamic_60.json').read_text())
            assert len(coverage) == int(old['migrations'])
            assert sum(r['hops'] for r in coverage) == int(old['hops']) == int(row['requests'])
            classes = Counter(r['coverage'] for r in coverage)
            timing = {int(r['request_id']): r for r in csv.DictReader((folder / 'timing_dynamic_60.csv').open())}
            chain_latency = mean(sum(float(timing[rid]['total_time_ms']) for rid in c['request_ids']) for c in coverage)
            d = dict(old)
            d.update(memory='Unbounded', physical_capacity=capacity, compiler_quota=capacity,
                     peak_capacity_bound=peak, latency_hop_ms=float(row['request_latency_mean_ms']),
                     latency_chain_ms=chain_latency, fidelity_percent=100*float(row['average_delivered_epr_fidelity']))
            for label in ('full', 'partial', 'zero'):
                d['coverage_' + label + '_count'] = classes[label]
                d['coverage_' + label + '_percent'] = 100*classes[label]/len(coverage)
            counts, why = Counter(), Counter()
            pairs = list(csv.DictReader((folder / 'pairs_dynamic_60.csv').open()))
            for pair in pairs:
                if pair['status'] == 'used':
                    counts['used'] += 1
                elif pair['status'] == 'remaining':
                    counts['unused'] += 1
                elif pair['status'] == 'expired':
                    reason = pair['expiry_reason']
                    why[reason] += 1
                    counts['expiry' if reason in {'reservation_expired', 'memory_coherence', 'replaced_after_expiry'} else 'eviction'] += 1
                else:
                    raise AssertionError('unexpected final pair status')
            assert sum(counts.values()) == len(pairs) == int(row['generated_compiler_pairs'])
            d.update(generated_pairs=len(pairs), used_pairs=counts['used'])
            for kind in ('eviction', 'expiry', 'unused'):
                d[kind + '_pairs'] = counts[kind]
                d[kind + '_percent'] = 100*counts[kind]/len(pairs)
            d['total_waste_percent'] = 100*(len(pairs)-counts['used'])/len(pairs)
            assert abs(d['total_waste_percent']-float(row['compiler_waste_percentage'])) < 1e-9
            output.append(d)
            reasons.append(dict(workload=workload, route=route, reasons=dict(why)))
    with (args.output / 'metrics.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    for name, value in [('audits.json', audits), ('capacity_verification.json', bounds), ('waste_reasons.json', reasons)]:
        (args.output / name).write_text(json.dumps(value, indent=2))
    names = {'qft': 'QFT', 'qpeexact': 'QPE (exact)', 'qaoa': 'QAOA', 'draper_qft_adder': 'Draper', 'quantum_volume': 'Quantum Volume'}
    text = '| Workload | Route | Memory/core | Latency (ms/hop) | EPR fidelity (%) | Chain coverage: full / partial / zero (%) | Wastage: eviction / expiry / unused (%) |\n| --- | --- | --- | ---: | ---: | --- | --- |\n'
    for d in output:
        coverage = ' / '.join(f"{float(d['coverage_'+k+'_percent']):.2f}" for k in ('full', 'partial', 'zero'))
        waste = ' / '.join(f"{float(d[k+'_percent']):.2f}" for k in ('eviction', 'expiry', 'unused'))
        text += f"| {names[d['workload']]} | {d['route']} | {d['memory']} | {float(d['latency_hop_ms']):.4f} | {float(d['fidelity_percent']):.3f} | {coverage} | {waste} |\n"
    (args.output / 'README.md').write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
