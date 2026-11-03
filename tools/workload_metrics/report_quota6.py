"""Validate and compare the QAOA compiler quota-six experiment."""
from pathlib import Path
from collections import Counter
import csv
import json


def main():
    root = Path.cwd()
    study = root / 'output/qaoa-history-active16-10ns-2026-11-03'
    output = root / 'docs/research/compiler-pregeneration/quota6-10ns-2026-11-03'
    output.mkdir(parents=True, exist_ok=True)
    old_command = json.loads((study / 'm8/command.json').read_text())
    command = json.loads((study / 'm8-c6/command.json').read_text())
    expected = old_command.copy()
    expected[expected.index('--compiler-memories') + 1] = '6'
    expected[expected.index('--output') + 1] = str(study / 'm8-c6')
    assert expected == command
    rows, audits = [], []
    hashes = None
    for label, folder, strategy in [('ODG', 'odg', 'on-demand'), ('Compiler quota 8', 'm8', 'dynamic'), ('Compiler quota 6', 'm8-c6', 'dynamic')]:
        path = study / folder
        meta = json.loads((path / 'metadata.json').read_text())
        p = meta['parameters']
        for k, v in dict(total_memories=8, generation_capacity=8, empty_layer_gap_ms=0.00001,
                         dynamic_layer_basis='active', dynamic_lookahead_layers=16,
                         planner_lead_layers=2, coherence_time_layers=17,
                         compiler_reservation_ms=50, layer_activation_order='execution-first').items():
            assert p[k] == v, (k, p[k])
        if hashes is None:
            hashes = meta['source_sha256']
        assert meta['source_sha256'] == hashes
        summary = next(csv.DictReader((path / 'summary.csv').open()))
        assert summary['seed'] == '60' and float(summary['completion_rate']) == 1
        audit = json.loads((path / f'audit_{strategy}_60.json').read_text())
        assert not audit['violations'] and audit['completed_requests'] == audit['total_requests'] == 30232
        audits.append(dict(configuration=label, **audit))
        coverage = json.loads((path / f'chain_coverage_{strategy}_60.json').read_text())
        assert len(coverage) == 15900
        counts = Counter(r['coverage'] for r in coverage)
        capacity = json.loads((path / f'capacity_{strategy}_60.json').read_text())
        peak = max(capacity['peak_compiler_bookings_per_node'].values(), default=0)
        if folder == 'm8-c6':
            assert p['compiler_memories'] == 6 and peak <= 6
        row = dict(configuration=label, latency_ms_per_hop=float(summary['request_latency_mean_ms']),
                   fidelity_percent=100 * float(summary['average_delivered_epr_fidelity']),
                   makespan_s=float(summary['end_to_end_latency_ms']) / 1000,
                   hop_readiness_percent=100 * float(summary['pregenerated_success_rate']),
                   admission_wait_ms=float(summary['average_admission_wait_ms']),
                   peak_compiler_bookings=peak, requests=int(summary['requests']))
        for k in ('full', 'partial', 'zero'):
            row[k + '_chains'] = counts[k]
            row[k + '_percent'] = 100 * counts[k] / len(coverage)
        rows.append(row)
    with (output / 'metrics.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (output / 'audits.json').write_text(json.dumps(audits, indent=2))
    table = '| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Chain readiness: full / partial / zero (%) | Hop readiness (%) | Admission wait (ms/hop) |\n| --- | ---: | ---: | ---: | --- | ---: | ---: |\n'
    for r in rows:
        coverage = ' / '.join(f"{r[k + '_percent']:.2f}" for k in ('full', 'partial', 'zero'))
        table += f"| {r['configuration']} | {r['latency_ms_per_hop']:.4f} | {r['fidelity_percent']:.3f} | {r['makespan_s']:.4f} | {coverage} | {r['hop_readiness_percent']:.2f} | {r['admission_wait_ms']:.4f} |\n"
    notes = '''\nSame 208-qubit QAOA History trace, T-HQA/OEE mapping seed42, 4x4 mesh,
14 data slots/core, eight physical communication memories/core, physics seed60.
10ns empty gaps, active-layer lookback2-16, planner age cutoff17, generation
capacity8, execution-first ready-first admission, all-chain preparation, native
handoff and 50ms compiler reservation lifetime. Physical coherence is unchanged.

The quota-six candidate changes only --compiler-memories from8 to6 relative to
the completed quota-eight trial (apart from output path). The existing setting
limits offline compiler occupancy and runtime adaptive reservations at both
endpoints. ODG retains access to all eight physical memories. This is a fixed
compiler cap, not a demand-adaptive borrowing policy. Runtime booking diagnostics
verify at most six live compiler bookings/core. All trials completed30232 hops
with clean audits. Engine-facing source hashes match across all three trials.

Latency includes admission wait from hop eligibility to EPR delivery. Makespan
is the same end_to_end_latency_ms metric across trials. Chain readiness is sampled
at layer opening; hop readiness is sampled at individual hop eligibility. Fidelity
is delivered EPR fidelity, not circuit output fidelity. Single physics seed.
'''
    (output / 'README.md').write_text(table + notes, encoding='utf-8')
    print(table)


if __name__ == '__main__':
    main()
