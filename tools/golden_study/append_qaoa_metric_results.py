#!/usr/bin/env python3
"""Append every validated QAOA base metric to the open LaTeX report."""
from __future__ import annotations
import csv, math, statistics
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/'results/qaoa_2seed_2026-10-26'
REPORT=REPO/'output/pdf/qaoa_methods_congestion'
TEX=REPORT/'main.tex'
SOURCE=ROOT/'summaries/base-evaluation-progress.csv'
FIG=REPORT/'figures/results'; TAB=REPORT/'tables/results'
MEMORIES=(2,3,4,6,8,16,32)
POLICIES=('ODG','CGP','ACGP','Dynamic-full-chain','Dynamic-first-hop')
COLORS={'ODG':'#111111','CGP':'#E69F00','ACGP':'#CC79A7','Dynamic-full-chain':'#0072B2','Dynamic-first-hop':'#56B4E9'}
MARKERS={'ODG':'o','CGP':'s','ACGP':'D','Dynamic-full-chain':'^','Dynamic-first-hop':'v'}
METRICS=(
('request_latency_mean_ms_mean','Mean request latency','ms','performance'),
('request_latency_median_ms_mean','Median request latency','ms','performance'),
('request_latency_p95_ms_mean','95th-percentile request latency','ms','performance'),
('request_latency_max_ms_mean','Maximum request latency','ms','performance'),
('end_to_end_latency_ms_mean','Circuit makespan','s','performance'),
('average_admission_wait_ms_mean','Mean admission wait','ms','performance'),
('max_admission_wait_ms_mean','Maximum admission wait','ms','performance'),
('requests_that_waited_fraction_mean','Requests that waited','fraction','performance'),
('avg_reservation_setup_time_ms_mean','Mean reservation setup time','ms','decomposition'),
('avg_entanglement_generation_time_ms_mean','Mean entanglement-generation time','ms','decomposition'),
('avg_retry_wait_time_ms_mean','Mean retry-wait time','ms','decomposition'),
('average_delivered_epr_fidelity_mean','Mean delivered EPR fidelity','fidelity','quality'),
('total_retries_mean','Total retries','count','reliability'),
('requests_with_retries_mean','Requests with retries','count','reliability'),
('protocol_generated_pairs_mean','Protocol-generated pairs','count','protocol'),
('protocol_used_pairs_mean','Protocol-used pairs','count','protocol'),
('protocol_unused_pairs_mean','Protocol-unused pairs','count','protocol'),
('protocol_waste_percentage_mean','Protocol waste','%','protocol'),
('scheduled_preparations_mean','Scheduled compiler preparations','count','dynamic'),
('planner_blocked_preparations_mean','Planner-blocked preparations','count','dynamic'),
('planner_peak_compiler_memory_per_core_mean','Peak compiler memory/core','banks','dynamic'),
('runtime_admission_attempts_mean','Runtime admission attempts','count','dynamic'),
('runtime_launched_preparations_mean','Runtime-launched preparations','count','dynamic'),
('runtime_accepted_preparations_mean','Runtime-accepted preparations','count','dynamic'),
('runtime_rejected_preparations_mean','Runtime-rejected preparations','count','dynamic'),
('pregenerated_hits_mean','Pregenerated hits','count','dynamic'),
('pregenerated_success_rate_mean','Pregeneration success rate','fraction','dynamic'),
('intended_request_hits_mean','Intended-request hits','count','dynamic'),
('intended_request_hit_rate_mean','Intended-request hit rate','fraction','dynamic'),
('compiler_not_ready_requests_mean','Compiler-not-ready requests','count','dynamic'),
('late_compiler_pair_uses_mean','Late compiler-pair uses','count','dynamic'),
('on_demand_fallbacks_mean','On-demand fallbacks','count','dynamic'),
('on_demand_fallback_rate_mean','On-demand fallback rate','fraction','dynamic'),
('generated_compiler_pairs_mean','Generated compiler pairs','count','dynamic'),
('utilized_compiler_pairs_mean','Utilized compiler pairs','count','dynamic'),
('expired_compiler_pairs_mean','Expired compiler pairs','count','dynamic'),
('remaining_compiler_pairs_mean','Remaining compiler pairs','count','dynamic'),
('compiler_expiry_percentage_mean','Compiler-pair expiry','%','dynamic'),
('compiler_waste_percentage_mean','Compiler-pair waste','%','dynamic'),
('average_fidelity_at_creation_mean','Compiler-pair fidelity at creation','fidelity','dynamic'),
('average_fidelity_at_utilization_mean','Compiler-pair fidelity at utilization','fidelity','dynamic'),
('average_storage_time_ms_mean','Compiler-pair storage time','ms','dynamic'),
)
DYNAMIC=set(m[0] for m in METRICS if m[3]=='dynamic')

def esc(v):
    return str(v).replace('\\',r'\textbackslash{}').replace('&',r'\&').replace('%',r'\%').replace('_',r'\_').replace('#',r'\#')
def fnum(v):
    if v is None or not math.isfinite(v): return '--'
    a=abs(v)
    if a and (a>=1e5 or a<1e-3): return f'{v:.3e}'
    return f'{v:.5f}' if a<1 else f'{v:.3f}'
def applicable(metric,policy):
    return policy.startswith('Dynamic') if metric in DYNAMIC else True
def read():
    rows=list(csv.DictReader(SOURCE.open(newline='',encoding='utf-8')))
    assert len(rows)==3201 and all(float(r['completion_rate_mean'])==1 for r in rows)
    return rows
def aggregate(rows,topology,metric):
    groups=defaultdict(list)
    base=metric[:-5] if metric.endswith('_mean') else metric
    sd_field=base+'_sd'
    for r in rows:
        if r['topology']!=topology or not applicable(metric,r['policy']): continue
        if not r.get(metric): continue
        key=(r['route_policy'],int(r['total_memories_per_core']),r['policy'])
        groups[key].append(r)
    out=[]
    for (route,memory,policy),g in sorted(groups.items()):
        vals=[float(r[metric]) for r in g]
        # Between-cell spread covers mapping traces and legal compiler allocations.
        mean=statistics.fmean(vals); sd=statistics.stdev(vals) if len(vals)>1 else 0.0
        if metric=='end_to_end_latency_ms_mean': mean/=1000; sd/=1000
        out.append({'topology':topology,'route_policy':route,'total_memories_per_core':memory,
                    'policy':policy,'mean':mean,'sd_across_cells':sd,'observations':len(vals),
                    'compiler_allocations':', '.join(map(str,sorted({int(r['compiler_memories_per_core']) for r in g}))),
                    'mapping_trace_groups':len({r['trace_sha256'] for r in g}),
                    'physics_seeds_per_cell':';'.join(sorted({r['physics_seed_count'] for r in g}))})
    return out
def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def make_plot(topology,metric,label,unit,rows,path):
    routes=sorted({r['route_policy'] for r in rows})
    n=len(routes); fig,axes=plt.subplots(1,n,figsize=(4.8*n,4.15),squeeze=False,layout='constrained')
    for ax,route in zip(axes[0],routes):
        for policy in POLICIES:
            pts=sorted((r for r in rows if r['route_policy']==route and r['policy']==policy),key=lambda r:r['total_memories_per_core'])
            if not pts: continue
            x=[r['total_memories_per_core'] for r in pts]; y=[r['mean'] for r in pts]
            ax.plot(x,y,label=policy,color=COLORS[policy],marker=MARKERS[policy],linewidth=1.7,markersize=4)
        ax.set_title(route.replace('_',' ')); ax.set_xticks(MEMORIES); ax.set_xscale('log',base=2); ax.minorticks_off()
        ax.set_xlabel('Total memory banks per core'); ax.set_ylabel(label+(f' ({unit})' if unit else '')); ax.grid(alpha=.25)
        if unit in ('count','ms','s','%','fraction','banks','fidelity'): ax.set_ylim(bottom=0)
    handles,labels=axes[0][0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside upper center',ncol=min(5,len(labels)),fontsize=8)
    fig.suptitle(f'QAOA | {topology.capitalize()} | {label}\nMean across validated mapping-trace / legal-allocation cells',fontsize=12)
    fig.savefig(path,dpi=180,bbox_inches='tight'); plt.close(fig)
def explanation(metric,label,kind):
    generic=(f'This plot asks how {label.lower()} changes when total communication memory per core increases. '
             'Each point is the arithmetic mean of the validated cells listed in the table; the graph does not select a best compiler allocation. '
             'Read comparisons vertically at a fixed memory value and route, then inspect the full capacity trend.')
    if kind=='dynamic':
        return generic+' This counter exists only for Dynamic full-chain and Dynamic first-hop; the other methodologies are N/A by design.'
    if metric=='end_to_end_latency_ms_mean': return generic+' Makespan covers the whole circuit execution and is reported in seconds; it is different from per-request latency.'
    if metric=='requests_that_waited_fraction_mean': return generic+' The fraction ranges from zero to one and counts requests whose admission wait crossed the study threshold.'
    if 'fidelity' in metric: return generic+' Higher fidelity is desirable, but its tradeoff with latency, retries, and storage time must be read from the neighbouring figures.'
    if 'waste' in metric or 'unused' in metric or 'expired' in metric: return generic+' Lower values indicate less unused or expired work, subject to the paired latency and hit-rate results.'
    if 'latency' in metric or 'wait' in metric: return generic+' Lower values indicate faster service; mean, median, p95, and maximum are kept separate because they describe different parts of the latency distribution.'
    return generic
def section(rows):
    FIG.mkdir(parents=True,exist_ok=True); TAB.mkdir(parents=True,exist_ok=True)
    lines=[r'\clearpage',r'\part*{QAOA physical-simulation results}',
    r'\addcontentsline{toc}{part}{QAOA physical-simulation results}',
    r'\section*{How to read the metric results}',
    r'The validated base study is complete: 1,639 of 1,639 jobs and 6,402 of 6,402 policy-seed evaluations. The sections first report mesh results and then torus results. Every graph uses total memory banks per core on the horizontal axis and contains the applicable methodology lines: ODG, CGP, ACGP, Dynamic full-chain, and Dynamic first-hop.',
    r'Each source simulation cell already averages evaluation physics seeds 0 and 1. A plotted point then averages all validated mapping-trace cells and all legal compiler-memory allocations available for its topology, route, total-memory value, and policy. This allocation-averaged view answers the requested total-memory question without selecting a favourable compiler split. The table reports the number of cells and the included compiler allocations so unequal cell counts remain visible. The shaded-error convention is omitted because two physics seeds do not support a strong uncertainty claim; the companion CSV nevertheless records the standard deviation across plotted cells.',
    r'ODG uses compiler allocation zero. The other policies are evaluated over legal compiler allocations. Exact byte-identical route traces were executed once, so XY/YX cells can represent aliases from several mapping seeds while reliability-aware routes may contain three distinct trace groups. Mapping seeds and compiler allocations are controlled inputs, not independent experimental replications.',
    r'All blank or inapplicable values are shown as ``--''. Compiler-planner, compiler-cache, hit, fallback, and storage counters are defined only for Dynamic full-chain and Dynamic first-hop; drawing zero lines for ODG, CGP, or ACGP would falsely imply those methods ran the Dynamic compiler planner.',
    r'Every table follows its graph and links the exact compact CSV used for both. Mean is the plotted value; SD is descriptive variation across mapping-trace/allocation cells, not a confidence interval. The master validated source is \href{run:../../../results/qaoa_2seed_2026-10-26/summaries/base-evaluation-progress.csv}{base-evaluation-progress.csv}.']
    for topology in ('mesh','torus'):
        lines += [r'\clearpage',r'\part*{'+topology.capitalize()+r' results}',r'\addcontentsline{toc}{part}{'+topology.capitalize()+r' results}']
        if topology=='mesh': lines.append(r'The mesh section contains four routing panels per figure: XY, YX, shortest reliable, and maximum reliability. Route choice changes relay paths while the topology remains the 4 by 4 mesh.')
        else: lines.append(r'The torus section uses the approved Dijkstra route on the 4 by 4 wraparound topology. Compare torus with mesh cautiously because both connectivity and mapped placements can differ.')
        last_kind=None
        for metric,label,unit,kind in METRICS:
            if kind!=last_kind:
                heading={'performance':'Latency and waiting','decomposition':'Latency decomposition','quality':'Delivered quality','reliability':'Retries and robustness','protocol':'Protocol pair accounting','dynamic':'Dynamic compiler-planner and cache accounting'}[kind]
                lines += [r'\clearpage',r'\section*{'+heading+r'}']; last_kind=kind
            agg=aggregate(rows,topology,metric); assert agg
            slug=metric.removesuffix('_mean'); png=FIG/f'{topology}__{slug}.png'; csvpath=TAB/f'{topology}__{slug}.csv'
            make_plot(topology,metric,label,unit,agg,png); write_csv(csvpath,agg)
            lines += [r'\clearpage',r'\subsection*{'+esc(label)+r'}',
                      r'\begin{center}\includegraphics[width=\linewidth]{\detokenize{figures/results/'+png.name+r'}}\end{center}',
                      esc(explanation(metric,label,kind)),r'\par',
                      r'\href{run:tables/results/'+csvpath.name+r'}{Exact graph/table CSV: \nolinkurl{'+csvpath.name+r'}}.\par',
                      r'\tiny\setlength{\tabcolsep}{2pt}\begin{longtable}{@{}p{23mm}p{29mm}rrrrp{36mm}r@{}}',
                      r'\toprule Route & Policy & $M$ & Mean & SD & Cells & Allocations & Traces \\ \midrule\endfirsthead',
                      r'\toprule Route & Policy & $M$ & Mean & SD & Cells & Allocations & Traces \\ \midrule\endhead',
                      r'\bottomrule\endfoot']
            for r in agg:
                route={'shortest_reliable':'shortest rel.','max_reliability':'max rel.'}.get(r['route_policy'],r['route_policy'])
                policy={'Dynamic-full-chain':'Dynamic full','Dynamic-first-hop':'Dynamic first'}.get(r['policy'],r['policy'])
                lines.append(f"{esc(route)} & {esc(policy)} & {r['total_memories_per_core']} & {fnum(r['mean'])} & {fnum(r['sd_across_cells'])} & {r['observations']} & {esc(r['compiler_allocations'])} & {r['mapping_trace_groups']} \\\\")
            lines += [r'\end{longtable}\normalsize\setlength{\tabcolsep}{6pt}']
    return '\n'.join(lines)+'\n'
def main():
    rows=read(); source=TEX.read_text(encoding='utf-8')
    marker='% BEGIN QAOA METRIC RESULTS'
    if marker in source: source=source.split(marker)[0].rstrip()+'\n\\end{document}\n'
    assert source.rstrip().endswith(r'\end{document}')
    addition=marker+'\n'+section(rows)+'% END QAOA METRIC RESULTS\n'
    TEX.write_text(source.rsplit(r'\end{document}',1)[0]+addition+r'\end{document}'+'\n',encoding='utf-8')
    print(f'Appended {len(METRICS)*2} metric sections; figures={len(list(FIG.glob("*.png")))} CSVs={len(list(TAB.glob("*.csv")))}')
if __name__=='__main__': main()
