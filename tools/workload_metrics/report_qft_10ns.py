"""Compare QFT quota-six/demand-guard, ODG and native ACGP."""
from pathlib import Path
from collections import Counter
import csv,json


def main():
    root = Path.cwd()
    study = root / 'output/qft-history-three-strategies-10ns-2026-11-03'
    output = root / 'docs/research/compiler-pregeneration/qft-three-strategies-10ns-2026-11-03'
    output.mkdir(parents=True, exist_ok=True)
    rows, audits = [], []
    hashes = None
    labels = {'on-demand': 'ODG', 'adaptive-continuous': 'ACGP', 'dynamic': 'Compiler quota6 + demand guard'}
    for strategy in labels:
        folder = study / strategy
        summary = next(csv.DictReader((folder / 'summary.csv').open()))
        assert summary['strategy'] == strategy and summary['seed'] == '60' and float(summary['completion_rate']) == 1
        meta = json.loads((folder / 'metadata.json').read_text())
        if hashes is None:
            hashes = meta['source_sha256']
        assert hashes == meta['source_sha256']
        p = meta['parameters']
        for k,v in dict(total_memories=8, compiler_memories=6, generation_capacity=8,
                        empty_layer_gap_ms=0.00001, dynamic_layer_basis='active',
                        dynamic_lookahead_layers=16, planner_lead_layers=2,
                        coherence_time_layers=17, compiler_reservation_ms=50,
                        layer_activation_order='execution-first').items():
            assert p[k] == v, (strategy,k,p[k])
        assert p['demand_first'] == (strategy == 'dynamic')
        assert p['autonomous_cache_follows_compiler_memories'] == (strategy == 'adaptive-continuous')
        audit = json.loads((folder / f'audit_{strategy}_60.json').read_text())
        assert not audit['violations'] and audit['completed_requests'] == audit['total_requests'] == 12784
        audits.append(dict(strategy=strategy, **audit))
        diagnostic = json.loads((folder / f'capacity_{strategy}_60.json').read_text())
        if strategy == 'dynamic':
            assert max(diagnostic['peak_compiler_bookings_per_node'].values(), default=0) <= 6
        ready = None if strategy == 'adaptive-continuous' else 100 * float(summary['pregenerated_success_rate'])
        rows.append(dict(strategy=labels[strategy], latency_ms_per_hop=float(summary['request_latency_mean_ms']),
                         fidelity_percent=100 * float(summary['average_delivered_epr_fidelity']),
                         makespan_s=float(summary['end_to_end_latency_ms']) / 1000,
                         hop_readiness_percent=ready, admission_wait_ms=float(summary['average_admission_wait_ms']),
                         requests=int(summary['requests'])))
    with (output / 'metrics.csv').open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (output / 'audits.json').write_text(json.dumps(audits,indent=2))
    text='| Strategy | Latency (ms/hop) | EPR fidelity (%) | Makespan (s) | Hop readiness (%) |\n| --- | ---: | ---: | ---: | ---: |\n'
    for r in rows:
        ready='Not measured' if r['hop_readiness_percent'] is None else f"{r['hop_readiness_percent']:.2f}"
        text+=f"| {r['strategy']} | {r['latency_ms_per_hop']:.4f} | {r['fidelity_percent']:.3f} | {r['makespan_s']:.4f} | {ready} |\n"
    text+='''\n208-qubit QFT, frozen History routing, T-HQA/OEE mapping seed42, 4x4 mesh,
14 data slots/core, eight physical communication memories/core and physics seed60.
All strategies use10ns empty-layer gaps and the same per-qubit event scheduler.
The compiler uses quota6, generation budget8, offline active lookback2-16,
planner age cutoff17, demand guarding, execution-first ready-first admission,
all-chain preparation and native handoff. Release/dependency priority and runtime
planning are disabled. Physical coherence is unchanged; compiler reservations50ms.
ACGP has an explicit six-slot autonomous cache cap and retains native background
generation,200ms protocol period and period-aligned reservation expiries. Compiler
lookback, demand guard and launch budget do not govern ACGP. No ACGP tuning.
The compiler booking-counter check applies only to compiler reservations; generic
autonomous booking IDs are not a validated live-occupancy measurement in this
diagnostic. The ACGP cap reported here is the configured native protocol limit.

Latency is eligibility-to-EPR-delivery per hop, including admission wait. Fidelity
is delivered EPR fidelity, not circuit output fidelity. Makespan uses the same
end_to_end_latency_ms /1000 metric. Compiler hop readiness is the pregenerated-pair
hit fraction at individual hop eligibility. ACGP hop readiness is not measured
by that compiler-specific counter and is deliberately not inferred from protocol
pair totals or chain coverage. ODG readiness is zero by construction. All12784
requests completed in each trial, with clean audits and matching source hashes.
These are single-seed results.
'''
    (output/'README.md').write_text(text,encoding='utf-8')
    pairs=list(csv.DictReader((study/'dynamic/pairs_dynamic_60.csv').open()))
    states=Counter((r['status'],r['expiry_reason']) for r in pairs)
    assert len(pairs)==7380 and states==Counter({('used',''):7359,('expired','reservation_expired'):21})
    autonomous=next(csv.DictReader((study/'adaptive-continuous/summary.csv').open()))
    waste=dict(compiler_generated=7380,compiler_used=7359,compiler_expiry=21,
               compiler_eviction=0,compiler_remaining=0,compiler_waste_percent=100*21/7380,
               acgp_reported_protocol_waste_percent=float(autonomous['protocol_waste_percentage']),
               acgp_pair_waste_validated=False,
               reason='num_unused_entanglement_pairs increments on adaptive memory release even when no generated pair exists; this is not a unique generated-pair lifecycle ledger')
    (output/'wastage.json').write_text(json.dumps(waste,indent=2))
    with (output/'README.md').open('a',encoding='utf-8') as f:
        f.write('\nCompiler wastage:21 reservation-expired pairs out of7380 generated (0.28455%);7359 used,0 evictions,0 remaining. ACGP raw protocol counter reports3.85199%, but is not validated pair wastage: its unused counter increments on memory release even when no generated pair exists. It must not be compared directly with compiler lifecycle wastage. ODG has no speculative pair inventory.\n')
    print(text)


if __name__=='__main__':
    main()
