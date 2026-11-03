"""Compile audited workload metrics and chain-start coverage."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    input_study = json.loads((a.study / 'inputs' / 'study.json').read_text())
    architecture = input_study['architecture']
    assert input_study['status'] == 'complete'
    assert architecture['mesh'] == '4x4' and architecture['data_slots_per_core'] == 14
    assert architecture['communication_slots_per_core'] == 8
    assert architecture['requested_circuit_qubits'] == 208
    workloads = ('qft', 'qpeexact', 'qaoa', 'draper_qft_adder', 'quantum_volume')
    metrics, audits, reasons = [], [], []
    hashes = None
    for workload in workloads:
        manifest = json.loads((a.study / 'inputs' / workload / 'seed_42' / 'manifest.json').read_text())
        assert manifest['source']['actual_qubits'] == 208
        for route in ('xy', 'history'):
            folder = a.study / 'simulation' / workload / route
            meta = json.loads((folder / 'metadata.json').read_text())
            args = meta['parameters']
            assert meta['seeds'] == [60]
            assert args['total_memories'] == args['compiler_memories'] == args['generation_capacity'] == 8
            assert args['dynamic_layer_basis'] == 'logical' and args['empty_layer_gap_ms'] == 5
            assert args['layer_activation_order'] == 'execution-first' and args['planner_lead_layers'] == 2
            assert args['compiler_reservation_ms'] == 50
            assert not args['demand_first'] and args['record_chain_coverage']
            expected_trace = a.study / 'traces' / workload / 'seed_42' / route / 'requests.txt'
            assert Path(meta['trace']).resolve() == expected_trace.resolve()
            if hashes is None:
                hashes = meta['source_sha256']
            assert meta['source_sha256'] == hashes
            for row in csv.DictReader((folder / 'summary.csv').open()):
                strategy = row['strategy']
                audit = json.loads((folder / f'audit_{strategy}_60.json').read_text())
                assert float(row['completion_rate']) == 1 and not audit['violations']
                assert audit['completed_requests'] == audit['total_requests'] == int(row['requests'])
                audits.append(dict(workload=workload, route=route, strategy=strategy, **audit))
                coverage = json.loads((folder / f'chain_coverage_{strategy}_60.json').read_text())
                assert len({(r['layer'], r['qubit']) for r in coverage}) == len(coverage)
                for r in coverage:
                    assert r['hops'] == len(r['request_ids']) and r['ready_hops'] == len(r['ready_request_ids'])
                    expected = 'zero' if r['ready_hops'] == 0 else 'full' if r['ready_hops'] == r['hops'] else 'partial'
                    assert expected == r['coverage']
                assert sum(r['hops'] for r in coverage) == int(row['requests'])
                classes = Counter(r['coverage'] for r in coverage)
                timing = {int(r['request_id']): r for r in csv.DictReader((folder / f'timing_{strategy}_60.csv').open())}
                chain_latency = mean(sum(float(timing[rid]['total_time_ms']) for rid in chain['request_ids']) for chain in coverage)
                d = dict(workload=workload, route=route, strategy=strategy, logical_qubits=208,
                         migrations=len(coverage), hops=int(row['requests']),
                         latency_hop_ms=float(row['request_latency_mean_ms']), latency_chain_ms=chain_latency,
                         fidelity_percent=100 * float(row['average_delivered_epr_fidelity']))
                for label in ('full', 'partial', 'zero'):
                    d['coverage_' + label + '_count'] = classes[label]
                    d['coverage_' + label + '_percent'] = 100 * classes[label] / len(coverage)
                d.update(generated_pairs=0, used_pairs=0, eviction_pairs=0, expiry_pairs=0, unused_pairs=0,
                         eviction_percent=None, expiry_percent=None, unused_percent=None, total_waste_percent=None)
                if strategy == 'dynamic':
                    pairs = list(csv.DictReader((folder / 'pairs_dynamic_60.csv').open()))
                    counts = Counter()
                    for pair in pairs:
                        if pair['status'] == 'used':
                            d['used_pairs'] += 1
                        elif pair['status'] == 'remaining':
                            d['unused_pairs'] += 1
                        elif pair['status'] == 'expired':
                            reason = pair['expiry_reason']
                            counts[reason] += 1
                            key = 'expiry_pairs' if reason in {'reservation_expired', 'memory_coherence', 'replaced_after_expiry'} else 'eviction_pairs'
                            d[key] += 1
                        else:
                            raise AssertionError('unexpected pair status: ' + pair['status'])
                    d['generated_pairs'] = len(pairs)
                    assert sum(d[k] for k in ('used_pairs', 'eviction_pairs', 'expiry_pairs', 'unused_pairs')) == len(pairs)
                    assert len(pairs) == int(row['generated_compiler_pairs'])
                    for kind in ('eviction', 'expiry', 'unused'):
                        d[kind + '_percent'] = 100 * d[kind + '_pairs'] / len(pairs) if pairs else None
                    d['total_waste_percent'] = 100 * (len(pairs) - d['used_pairs']) / len(pairs) if pairs else None
                    assert abs(d['total_waste_percent'] - float(row['compiler_waste_percentage'])) < 1e-9
                    reasons.append(dict(workload=workload, route=route, reasons=dict(counts)))
                else:
                    assert classes['full'] == classes['partial'] == 0
                metrics.append(d)
    assert len(metrics) == len(audits) == 20
    with (a.output / 'metrics.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    (a.output / 'audits.json').write_text(json.dumps(audits, indent=2))
    (a.output / 'waste_reasons.json').write_text(json.dumps(reasons, indent=2))
    names = {'qft': 'QFT', 'qpeexact': 'QPE (exact)', 'qaoa': 'QAOA', 'draper_qft_adder': 'Draper', 'quantum_volume': 'Quantum Volume'}
    text = '| Workload | Route | Generation | Latency (ms/hop) | Fidelity (%) | Chain coverage: full / partial / zero (%) | Wastage: eviction / expiry / unused (%) |\n| --- | --- | --- | ---: | ---: | --- | --- |\n'
    for d in metrics:
        coverage = ' / '.join(f"{d['coverage_' + label + '_percent']:.2f}" for label in ('full', 'partial', 'zero'))
        waste = ' / '.join(f"{d[kind + '_percent']:.2f}" for kind in ('eviction', 'expiry', 'unused')) if d['strategy'] == 'dynamic' else 'N/A'
        text += f"| {names[d['workload']]} | {d['route']} | {'Compiler' if d['strategy'] == 'dynamic' else 'ODG'} | {d['latency_hop_ms']:.4f} | {d['fidelity_percent']:.3f} | {coverage} | {waste} |\n"
    (a.output / 'README.md').write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
