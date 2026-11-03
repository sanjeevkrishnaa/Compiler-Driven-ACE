"""Validate CGP/ACGP latency against the matching QAOA controls."""
from pathlib import Path
import csv
import json


def main():
    root = Path.cwd()
    study = root / 'output/qaoa-cgp-acgp-10ns-2026-11-03'
    controls = root / 'output/qaoa-preparation-policy-2026-11-03'
    dest = root / 'docs/research/compiler-pregeneration/cgp-acgp-10ns-2026-11-03'
    dest.mkdir(parents=True, exist_ok=True)
    cases = [('ODG', controls / 'odg', 'on-demand'),
             ('CGP', study / 'continuous', 'continuous'),
             ('ACGP', study / 'adaptive-continuous', 'adaptive-continuous'),
             ('Compiler quota6 + demand guard', controls / 'demand6', 'dynamic')]
    rows, audits = [], []
    hashes = None
    for label, folder, strategy in cases:
        row = next(csv.DictReader((folder / 'summary.csv').open()))
        assert row['strategy'] == strategy and row['seed'] == '60' and float(row['completion_rate']) == 1
        meta = json.loads((folder / 'metadata.json').read_text())
        if hashes is None:
            hashes = meta['source_sha256']
        assert meta['source_sha256'] == hashes
        p = meta['parameters']
        assert p['total_memories'] == 8 and p['empty_layer_gap_ms'] == 0.00001
        if label in ('CGP', 'ACGP'):
            assert p['compiler_memories'] == 6 and p['autonomous_cache_follows_compiler_memories']
        audit = json.loads((folder / f'audit_{strategy}_60.json').read_text())
        assert not audit['violations'] and audit['completed_requests'] == audit['total_requests'] == 30232
        audits.append(dict(strategy=label, **audit))
        rows.append(dict(strategy=label, latency_ms_per_hop=float(row['request_latency_mean_ms']),
                         fidelity_percent=100 * float(row['average_delivered_epr_fidelity']),
                         makespan_s=float(row['end_to_end_latency_ms']) / 1000,
                         requests=int(row['requests'])))
    with (dest / 'metrics.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (dest / 'audits.json').write_text(json.dumps(audits, indent=2))
    text = '| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) |\n| --- | ---: | ---: | ---: |\n'
    for r in rows:
        text += f"| {r['strategy']} | {r['latency_ms_per_hop']:.4f} | {r['fidelity_percent']:.3f} | {r['makespan_s']:.4f} |\n"
    text += '''\n208-qubit QAOA, same History route and seed42 T-HQA mapping, 4x4 mesh,
14 data slots/core, eight physical communication memories/core, physics seed60,
10ns empty-layer gaps and the same per-qubit event scheduler. CGP and ACGP have
an explicitly configured six-slot autonomous cache cap, matching compiler quota6.
They retain native background-generation behavior and the200ms protocol period
from ace/topology/node.py. Their reservations use the native period rounding;
the compiler's50ms reservation parameter does not apply to them. Compiler active
lookback, generation launch budget, demand guard and directed handoff are compiler
controls, not autonomous-policy overrides. No autonomous timing tuning was done.

Latency is eligibility-to-EPR-delivery per hop and includes admission wait;
makespan is end_to_end_latency_ms /1000. Fidelity is delivered EPR fidelity.
All30232 hop requests completed with clean audits, and engine-facing source
fingerprints match across the four trials. This is a single-seed comparison of
the current implementations. Autonomous hop readiness is not reported: compiler
hit counters are not a valid measurement of generic CGP/ACGP cache readiness.
'''
    (dest / 'README.md').write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
