import csv,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/'evidence.json').read_text());assert d['completed']==18
rows=[dict(route=r['route'],lead=r['lead'],reused=r['reused'],**r['metrics'],summary_source=r['summary']) for r in d['records']]
with (ROOT/'runs.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
with (ROOT/'aggregate.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(d['aggregate'][0]));writer.writeheader();writer.writerows(d['aggregate'])
w=d['winner'];low=d['lowest_waste']
lines=['# QAOA exact lead sweep with borrowing','',
    f"Best observed initial lead by lowest pooled mean request latency: **L-{w['lead']}**, **{w['mean_latency_ms']:.6f} ms**. "
    f"XY route winner: L-{d['route_winners']['xy']}; History route winner: L-{d['route_winners']['history']}.", '',
    'The primary ranking is transfer-count-weighted mean latency across XY and cumulative History, as requested. Each route has 29,605 transfers. The lowest pooled compiler waste occurs at '
    f"L-{low['lead']} ({100*low['waste']:.4f}%). No weighted composite score is used.", '',
    '| Initial lead | XY mean (ms) | History mean (ms) | Pooled mean (ms) | Mean completion (s) | Delivered fidelity | Pooled waste | Coverage |',
    '|---|---:|---:|---:|---:|---:|---:|---:|']
for a in d['aggregate']:
    lead=a['lead'];xy=next(r for r in d['records'] if r['route']=='xy' and r['lead']==lead);hi=next(r for r in d['records'] if r['route']=='history' and r['lead']==lead)
    lines.append(f"| L-{lead} | {xy['metrics']['average_request_latency_ms']:.6f} | {hi['metrics']['average_request_latency_ms']:.6f} | {a['mean_latency_ms']:.6f} | {a['mean_completion_s']:.6f} | {a['delivered_fidelity']:.6f} | {100*a['waste']:.4f}% | {100*a['coverage']:.3f}% |")
lines+=['','## Protocol and evidence','',
    'Same implementation source fingerprints for all 18 cases on codex/l2-borrow-refill. Borrowing and immediate replenishment enabled, trace-order initial preparations, exact lead on communication-active layers, 8 communication memories per core with compiler quota 6, generation capacity 8, 50 ms reservation lifetime, mapping seed 42 and physics seed 60. Initial generation is restricted to the single configured layer; replacements remain immediate exceptions, subject to hardware capacity and demand priority.', '',
    'All 18 cases completed 29,605 transfers and passed physical/ordering audits. Independently verified: exact initial planner lead, generation/use/expiry/remaining conservation, immediate replacement-request counts, source fingerprint equality, and matching parameters apart from lead and route/output paths.', '',
    'L-2 and L-3 measurements were reused from the prior audited runs after these checks; the other 14 cases were simulated for this sweep. The 10-layer planner coherence guard admits preparation ages strictly below 10, so this sweep covers L-1 through L-9 without changing that guard.', '',
    'Fidelity covers delivered EPR pairs, including on-demand fallback. Compiler pair waste is (expired + remaining) / generated. Prepared-pair fidelity is measured only among consumed compiler pairs. Total workload completion is separate from mean request latency. These are EPR-delivery metrics and exclude local data-qubit teleportation gates.', '',
    'The Excel workbook contains the formula-based ranking, native charts, all route/lead observations, computed utilization/expiry/waste/coverage, and a provenance/protocol sheet. It was recalculated, checked against independent Python aggregation, and rendered for visual review. Native Excel application recalculation was not tested.', '',
    'This is one fixed mapping and one matched physics seed, so the winner is the best observed setting in this sweep, not a cross-seed statistical conclusion. Strategy defaults were not changed.']
(ROOT/'report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(winner=w,route_winners=d['route_winners'],lowest_waste=low),indent=2))
