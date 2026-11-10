"""Archive a controlled before/after comparison without changing prior evidence."""
import csv,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ACE=ROOT.parents[1]
d=json.loads((ROOT/'evidence.json').read_text());assert d['completed']==18
old=json.loads((ACE/'results/compiler_lead_sweep_2026-11-10/evidence.json').read_text())
diag=json.loads((ROOT/'completion_diagnostics.json').read_text())
assert len(diag)==18 and max(r['after_max_delay_ms'] for r in diag)<0.100001
rows=[dict(route=r['route'],lead=r['lead'],reused=r['reused'],**r['metrics'],reservation_timeout_pairs=r['reservation_timeout_pairs'],summary_source=r['summary']) for r in d['records']]
for name,records in [('runs',rows),('aggregate',d['aggregate'])]:
    with (ROOT/f'{name}.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
w=d['winner'];previous=next(a for a in old['aggregate'] if a['lead']==w['lead'])
lines=['# QAOA lead sweep after completion cleanup','',
 f"Best observed lead by lowest pooled mean request latency: **L-{w['lead']}**, **{w['mean_latency_ms']:.6f} ms**. XY winner: L-{d['route_winners']['xy']}; cumulative History winner: L-{d['route_winners']['history']}.",'',
 f"Compared with the same lead before cleanup, mean latency changed by {(w['mean_latency_ms']/previous['mean_latency_ms']-1)*100:.3f}%, delivered fidelity by {(w['delivered_fidelity']-previous['delivered_fidelity'])*100:.6f} percentage points, and total compiler waste by {(w['waste']-previous['waste'])*100:.4f} percentage points.",'',
 '| Lead | Before mean (ms) | After mean (ms) | Change | Fidelity | Waste | Mean makespan (s) |',
 '|---|---:|---:|---:|---:|---:|---:|']
for a in d['aggregate']:
    b=next(x for x in old['aggregate'] if x['lead']==a['lead'])
    lines.append(f"| L-{a['lead']} | {b['mean_latency_ms']:.6f} | {a['mean_latency_ms']:.6f} | {(a['mean_latency_ms']/b['mean_latency_ms']-1)*100:.3f}% | {a['delivered_fidelity']:.6f} | {a['waste']*100:.4f}% | {a['mean_completion_s']:.6f} |")
lines+=['','## Controls and validation','',
 'All 18 post-cleanup cases were freshly simulated at implementation commit 38aad24, with identical source fingerprints. Each case completed 29,605 requests and passed physical and ordering audits. Compiler tests: 187 passed. The earlier preliminary cleanup sweep was discarded and is not included.', '',
 'Matched to the archived pre-cleanup sweep: mapping seed 42, physics seed 60, XY and cumulative all-past-layer History routing, exact L-1 through L-9 initial generation on communication-active layers, trace order, borrowing and immediate refill, 8 memories with compiler quota 6 and generation capacity 8. The 10-layer coherence planner guard is unchanged. Refill remains an immediate scheduling exception subject to demand and hardware constraints. Default lead remains L-2.', '',
 'Collection independently validates unchanged per-case runtime parameters except output location, the expected cleanup-only source changes, exact planned lead, completed request counts, no audit violations, immediate replacement counts, and generated = used + expired + cancelled + remaining.', '',
 'Waste includes (expired + cancelled + remaining) / generated. Cancellation is therefore counted as wasted generation, not hidden as a successful cleanup. The legacy expired category also includes rejected and failed-handoff releases; actual reservation-timeout counts are reported separately in the Runs sheet. Fidelity includes all delivered EPR pairs, including fallback. Makespan is total workload completion; the pooled makespan column is the arithmetic mean of both routes.', '',
 'Completion diagnostics compare pair generation timestamps against the target request completion time. In-flight work may complete within the one-way classical cancellation delay; the cleanup prevents continued obsolete preparation beyond that delay. Per-case timings and reasons are stored in completion_diagnostics.json.', '',
 f"Across the sweep, generated-after-completion records fell from {sum(r['before_generated_after_completion'] for r in diag):,} to {sum(r['after_generated_after_completion'] for r in diag):,}. Maximum delay fell from {max(r['before_max_delay_ms'] for r in diag):.6f} ms to {max(r['after_max_delay_ms'] for r in diag):.9f} ms. Every post-cleanup case is within 0.100001 ms.", '',
 'The new workbook preserves the old workbook and adds a BeforeAfter sheet, all three latency/fidelity/waste charts, route-level results, cancellation and actual-timeout counts, formula-based rankings, and protocol/source evidence. Formula recalculation and cached XLSX values are checked against independent aggregation, with visual inspection of rendered sheets. Native Microsoft Excel recalculation was not tested.', '',
 'These results use one fixed mapping and physics seed. They identify the best observed lead for this matched sweep, not a cross-seed statistical winner. No scheduling strategy or default lead was changed after fixing cleanup.']
(ROOT/'report.md').write_text('\n'.join(lines)+'\n')
archive=ACE/'results/compiler_cleanup_sweep_2026-11-10';archive.mkdir(exist_ok=True)
for name in ['evidence.json','runs.csv','aggregate.csv','completion_diagnostics.json','report.md','manifest.json','run.py','worker.py','collect.py','completion_diagnostics.py','write_report.py','build_workbook.mjs','verify_xlsx.py','workbook_inspection.ndjson','workbook_errors.ndjson']:
    shutil.copy2(ROOT/name,archive/name)
for r in d['records']:
    folder=Path(r['summary']).parent;target=archive/f"{r['route']}-L{r['lead']}";target.mkdir(exist_ok=True)
    for name in ['summary.csv','metadata.json','command.json','audit_dynamic_60.json']:
        shutil.copy2(folder/name,target/name)
print(json.dumps(dict(winner=w,route_winners=d['route_winners'],archive=str(archive)),indent=2))
