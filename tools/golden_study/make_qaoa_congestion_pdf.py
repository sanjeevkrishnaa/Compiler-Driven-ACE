#!/usr/bin/env python3
"""Step-one QAOA methods and complete congestion atlas; rebuild from source CSVs."""
from pathlib import Path
import csv
import hashlib
import json
import math
from collections import defaultdict
from html import escape
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from tools.golden_study.analyze_qft96_congestion import analyse

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / 'results/qaoa_2seed_2026-10-26'
OUT = REPO / 'output/pdf/qaoa_methods_congestion'
CAPS = (2,3,4,6,8,16,32)
ARMS = [('mesh','xy'),('mesh','yx'),('mesh','shortest_reliable'),('mesh','max_reliability'),('torus','dijkstra')]

def read(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))

def write(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'figures').mkdir(exist_ok=True); (OUT/'tables').mkdir(exist_ok=True)
    cores = read(ROOT/'congestion/per_core_congestion.csv')
    summaries = read(ROOT/'congestion/trace_congestion_summary.csv')
    assert len(cores)==3360 and len(summaries)==210
    grouped=defaultdict(list)
    for r in cores:
        assert r['workload']=='qaoa' and r['mapping_algorithm']=='T-HQA'
        grouped[(r['topology'],r['route_policy'],int(r['mapping_seed']),int(r['capacity']),r['variant'])].append(r)
    assert len(grouped)==210
    # Independently recompute all values from hash-checked traces before reporting.
    for topology,route in ARMS:
        for seed in (42,43,44):
            original=next(r for r in cores if r['topology']==topology and r['route_policy']==route and int(r['mapping_seed'])==seed)
            alias={k:original[k] for k in ('topology','mapping_algorithm','workload','mapping_seed','route_policy','trace_path','trace_sha256')}
            assert hashlib.sha256((ROOT/alias['trace_path']).read_bytes()).hexdigest()==alias['trace_sha256']
            _,recomputed=analyse(alias,ROOT,CAPS)
            for r in recomputed:
                match=next(x for x in grouped[(topology,route,seed,r['capacity'],r['variant'])] if int(x['core'])==r['core'])
                for field in ('overloaded_percent','own_percent','relay_only_percent','incident_demand','endpoint_demand','peak_demand'):
                    assert math.isclose(float(match[field]),float(r[field]),abs_tol=1e-10)
                assert math.isclose(r['overloaded_percent'],r['own_percent']+r['relay_only_percent'],abs_tol=1e-10)
    styles=getSampleStyleSheet()
    styles['Normal'].fontSize=10; styles['Normal'].leading=14
    styles['Heading1'].textColor=colors.HexColor('#15334d')
    story=[]
    def p(text,style='Normal'): story.append(Paragraph(text,styles[style])); story.append(Spacer(1,7))
    def link(path,label=None): return '<link href="'+path.as_uri()+'" color="#176697">'+escape(label or str(path.relative_to(REPO)))+'</link>'
    def code(path): return link(REPO/path,path)
    def table(rows,widths=None):
        t=Table(rows,colWidths=widths,hAlign='LEFT',repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#15334d')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),('LEADING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#eff4f7')]),('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(t); story.append(Spacer(1,8))
    p('QAOA: methods and congestion atlas','Title')
    p('Step 1 | Audited QAOA study of 26 October 2026','Heading2')
    p('Purpose. Understand how the mapped QAOA circuit becomes routed communication, where those routes concentrate demand, and how the structural congestion changes as capacity increases. This edition covers methods and congestion only. Physical simulation comparisons and dynamic-policy results are reserved for the next step.')
    p('1. Circuit to placement','Heading1')
    p('The input is a 48-qubit QAOA circuit in OpenQASM. The architecture has 16 cores arranged in a 4 x 4 mesh or torus. A mesh connects neighbouring grid positions; a torus also connects opposite boundaries. The current experiment selects T-HQA, with mapping seeds 42, 43 and 44.')
    p('T-HQA is the topology-aware HQA implementation. It constructs assignment costs from shortest-hop distances and uses lookahead attraction from future interactions. A Hungarian assignment solver selects assignments from the feasible cost matrix. This encourages interacting qubits to meet while accounting for transfer distance; it does not directly minimise the congestion percentages defined later.')
    p('The recorded mapper configuration uses OEE initial placement, four data-qubit slots per core, and link-reliability values in the range 0.1 to 1.0. Initial-placement implementation: '+code('mapper/qmap/placement/initial.py')+'. Data-qubit placement capacity is distinct from the communication-memory threshold C swept in the congestion study.')
    p('Implementation: '+code('mapper/qmap/placement/T_HQA.py')+'; '+code('mapper/qmap/placement/cost.py')+'; '+code('mapper/qmap/placement/assignment.py')+'.')
    p('The QAOA run imports previously generated placements and routes from the audited golden-study corpus. It does not rerun placement during each policy simulation. Placement contracts record assignments[t][q], the core occupied by qubit q at slice t. Reusing a fixed trace lets scheduler comparisons share the same communication input.')
    p('Mapping orchestration: '+code('tools/golden_study/map_inputs.py')+'. Placement contract: '+code('tools/mapper_ace/placement_contract.py')+'. Audited QAOA import: '+code('tools/golden_study/prepare_qaoa.py')+'.')
    p('Input and provenance: '+link(ROOT/'inputs/qaoa/circuit.qasm')+'; '+link(ROOT/'mapping_contract.json')+'; '+link(ROOT/'validation/mapping_audit.csv')+'.')
    story.append(PageBreak())
    p('2. Placement to physical routes','Heading1')
    p('A placement change gives a logical migration: a qubit moves from one core to another at a compiler layer. The adapter assigns a path to that migration, checks its endpoints and physical adjacency, and exports adjacent-hop requests. Routing changes the path while preserving the required placement transitions.')
    table([['Topology','Route','Decision rule'],['Mesh','XY','Coordinate dimension 0, then dimension 1'],['Mesh','YX','Coordinate dimension 1, then dimension 0'],['Mesh','shortest_reliable','Shortest hops; reliability breaks ties'],['Mesh','max_reliability','Maximum product reliability; hops break ties'],['Torus','dijkstra','Shortest hops with reliability tie-breaks']], [55,115,325])
    p('XY and YX test how equal-length paths redistribute load. Reliability-aware paths can choose different relays; maximum reliability may accept extra hops. The torus tests a different connectivity graph as well as its approved routing policy, so mesh-versus-torus differences cannot be attributed to routing alone.')
    p('Implementation: '+code('tools/mapper_ace/routing.py')+'; '+code('mapper/qmap/metrics/distance.py')+'; migration construction and validation in '+code('tools/mapper_ace/adapter.py')+'. The oracle also uses EPR latency as a later tie-breaker when hop and reliability costs tie.')
    p('There are 15 conceptual route aliases: (4 mesh routes + 1 torus route) x 3 seeds. Only 11 request files have distinct SHA-256 hashes. Identical files remain visible as separate route labels in this atlas, but they are not independent observations. Simulation planning deduplicates exact traces.')
    p('3. Routed traces to ACE experiments','Heading1')
    p('The broader study compares on-demand generation (ODG), continuous generation (CGP), adaptive continuous generation (ACGP), and Dynamic full-chain/first-hop preparation. It sweeps total memories 2, 3, 4, 6, 8, 16 and 32, legal compiler allocations, and evaluation physics seeds 0 and 1. These simulation dimensions do not multiply the trace-only congestion atlas.')
    p('Execution definition: '+link(ROOT/'execution_spec.json')+'. Planning/running: '+code('tools/golden_study/plan_execution.py')+'; '+code('tools/golden_study/run_execution.py')+'. Simulator entry: '+code('run_trace_comparison.py')+'; compiler scheduling: '+code('compiler_scheduler.py')+'.')
    story.append(PageBreak())
    p('4. What congestion means here','Heading1')
    p('For each communication-active compiler layer l and core c, let D(c,l) be total route demand and E(c,l) the demand from route endpoints. Capacity C is a structural threshold. Overload requires D &gt; C; equality is not overload. Empty communication layers are excluded from the denominator A.')
    p('<b>Hop counting:</b> a source or destination contributes one demand unit; each internal relay contributes two (arrival and departure). <b>Route counting:</b> each distinct core visited by a qubit route contributes one unit. Both views are included because relay accounting changes the structural pressure estimate.')
    p('Example: path C0 - C1 - C2 contributes [1,2,1] in hop counting and [1,1,1] in route counting. At C=1, C1 is overloaded only under hop counting. This demonstrates why the two definitions cannot be pooled as if they measured the same resource model.')
    p('<b>Total overload:</b> 100 x count(D &gt; C) / A. <b>Endpoint overload:</b> 100 x count(E &gt; C) / A. <b>Relay-only overload:</b> 100 x count(E &lt;= C &lt; D) / A. Endpoint overload and relay-only overload partition the total-overload layers for each core; their percentages add to total.')
    p('Relay-only does not mean the core has no endpoint traffic. It means endpoint demand alone fits, but additional relay demand pushes the total above capacity. Endpoint overload also does not exclude simultaneous relay traffic.')
    p('The trace-level statistic is different: percentage of active layers with <i>any</i> overloaded core. It is not the mean of the 16 per-core percentages. The overview graphs use this any-core measure; the spatial heatmaps use per-core percentages.')
    p('Why sweep capacity? Increasing C while holding the trace fixed isolates the threshold sensitivity of the same demand pattern. Overload must be non-increasing with C. Zero overload means demand stays within this structural threshold, not that the physical simulator has no waiting, retries, or fidelity loss.')
    p('These figures do not simulate occupancy, link timing, memory expiry, or dynamic cache state. They cannot establish a winning scheduler or a latency speedup. Mapping seeds vary compiler inputs; physics seeds do not enter this calculation. Three seed values are shown individually rather than treated as strong statistical evidence.')
    p('Analysis implementation: '+code('tools/golden_study/analyze_qft96_congestion.py')+'. Its historical filename refers to QFT, but this PDF verifies QAOA CSV rows and hashes and regenerates QAOA-labelled figures. Sources: '+link(ROOT/'congestion/per_core_congestion.csv')+' and '+link(ROOT/'congestion/trace_congestion_summary.csv')+'.')
    story.append(PageBreak())
    # Two overview pages, with exact plotted values and companion CSVs.
    for variant in ('hop','route'):
        p('Congestion overview | '+variant+' counting','Heading1')
        rows=[]; fig,ax=plt.subplots(figsize=(9,4))
        for topology,route in ARMS:
            values=[]
            for cap in CAPS:
                subset=[r for r in summaries if r['topology']==topology and r['route_policy']==route and r['variant']==variant and int(r['capacity'])==cap]
                value=sum(float(r['overloaded_layer_percent']) for r in subset)/3
                values.append(value); rows.append(dict(topology=topology,route=route,capacity=cap,mean_any_core_overload_percent=value))
            ax.plot(CAPS,values,marker='o',label=topology+' / '+route)
        ax.set(xscale='log',xlabel='Structural capacity C',ylabel='Active layers with any overloaded core (%)',ylim=(-2,102),title='QAOA | '+variant+' counting | mean of mapping seeds 42/43/44')
        ax.set_xticks(CAPS,labels=CAPS); ax.minorticks_off(); ax.grid(alpha=.25); ax.legend(fontsize=7); fig.tight_layout()
        path=OUT/'figures'/('overview_'+variant+'.png'); fig.savefig(path,dpi=160); plt.close(fig)
        story.append(Image(str(path),width=495,height=220))
        table([['Topology / route']+[str(c) for c in CAPS]]+[[t+' / '+r]+[f"{next(x['mean_any_core_overload_percent'] for x in rows if x['topology']==t and x['route']==r and x['capacity']==c):.2f}" for c in CAPS] for t,r in ARMS],[180]+[45]*7)
        csvpath=OUT/'tables'/('overview_'+variant+'.csv'); write(csvpath,rows)
        p('Table values are the exact graph series rounded to two decimals; each is an unweighted mean of three seed-specific percentages. Source values: '+link(csvpath,'graph and table CSV')+'. Original source: '+link(ROOT/'congestion/trace_congestion_summary.csv','trace congestion CSV')+'.')
        p('Read the capacity trend within each line first. Differences between mesh routes reflect their chosen paths on each fixed mesh placement. Torus comparisons additionally change topology and may use different placements. Coincident lines can reflect identical trace content. The atlas that follows retains every seed and both demand definitions.')
        story.append(PageBreak())
    # Each heatmap gets its own matching 16-core table and exact source slice.
    index=[]
    for topology,route in ARMS:
      for variant in ('hop','route'):
       for cap in CAPS:
        for seed in (42,43,44):
            key=(topology,route,seed,cap,variant); subset=sorted(grouped[key],key=lambda r:int(r['core']))
            assert [int(r['core']) for r in subset]==list(range(16))
            name=f'{topology}__{route}__seed{seed}__cap{cap}__{variant}'
            fig,axes=plt.subplots(1,3,figsize=(12,3.4),layout='constrained')
            for ax,field,title in zip(axes,('overloaded_percent','own_percent','relay_only_percent'),('Total overload','Endpoint overload','Relay-only overload')):
                values=[float(r[field]) for r in subset]
                im=ax.imshow([values[i:i+4] for i in range(0,16,4)],cmap='YlOrRd',vmin=0,vmax=100)
                ax.set_title(title,fontsize=11); ax.set_xticks(range(4)); ax.set_yticks(range(4))
                for i,value in enumerate(values): ax.text(i%4,i//4,f'C{i}\n{value:.1f}%',ha='center',va='center',fontsize=8,color='white' if value>60 else 'black')
            fig.colorbar(im,ax=axes,label='% of communication-active layers')
            path=OUT/'figures'/(name+'.png'); fig.savefig(path,dpi=150); plt.close(fig)
            csvpath=OUT/'tables'/(name+'.csv'); write(csvpath,subset)
            p(f'{topology.upper()} / {route} | {variant} counting','Heading1')
            p(f'Capacity {cap} | Mapping seed {seed} | QAOA / T-HQA','Heading2')
            story.append(Image(str(path),width=495,height=145)); story.append(Spacer(1,8))
            table([['Core','Total %','Endpoint %','Relay-only %','Peak D','Total demand']]+[[r['core']]+[f'{float(r[k]):.2f}' for k in ('overloaded_percent','own_percent','relay_only_percent')]+[r['peak_demand'],r['incident_demand']] for r in subset],[50,80,90,90,65,120])
            total=next(r for r in summaries if (r['topology'],r['route_policy'],int(r['mapping_seed']),int(r['capacity']),r['variant'])==key)
            hot=max(subset,key=lambda r:float(r['overloaded_percent']))
            p(f"This trace has {total['active_layers']} active layers out of {total['layers']} compiler layers and {total['physical_hops']} physical hop requests. At capacity {cap}, {float(total['overloaded_layer_percent']):.2f}% of active layers have at least one overloaded core. Highest per-core overload: C{hot['core']} at {float(hot['overloaded_percent']):.2f}% (ties possible).")
            p('Compare the endpoint and relay-only panels to identify whether demand already exceeds capacity at endpoints or crosses the threshold after relay demand is added. All panels use the same 0-100% colour scale. Peak D is the maximum layer demand; total demand sums demand units over active layers.')
            p('Exact figure/table data: '+link(csvpath,name+'.csv')+'. Full source: '+link(ROOT/'congestion/per_core_congestion.csv','per_core_congestion.csv')+'. Percentages in the figure use one decimal and in the table two decimals.')
            index.append(dict(figure=name,source_csv=str(csvpath),trace_sha256=subset[0]['trace_sha256']))
            story.append(PageBreak())
    story.pop() # no trailing blank page
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8); canvas.setFillColor(colors.HexColor('#527084'))
        canvas.drawString(50,25,'QAOA | Step 1: methods and structural congestion'); canvas.drawRightString(545,25,str(doc.page))
    # Keep the same reviewed content as an editable, native LaTeX project.
    from html.parser import HTMLParser
    def latex_escape(value):
        return ''.join({'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}.get(c,c) for c in str(value))
    class Inline(HTMLParser):
        def __init__(self): super().__init__(); self.parts=[]
        def handle_starttag(self,tag,attrs):
            if tag=='b': self.parts.append(r'\textbf{')
            elif tag=='i': self.parts.append(r'\emph{')
            elif tag=='link': self.parts.append(r'\href{\detokenize{'+dict(attrs)['href']+'}}{')
        def handle_endtag(self,tag):
            if tag in ('b','i','link'): self.parts.append('}')
        def handle_data(self,data):
            if ('/' in data or '_' in data) and ' ' not in data:
                self.parts.append(r'\nolinkurl{'+data+'}')
            else:
                self.parts.append(latex_escape(data))
    texlines=[r'\documentclass[10pt,a4paper]{article}',r'\usepackage[margin=20mm]{geometry}',r'\usepackage[T1]{fontenc}',r'\usepackage{lmodern,graphicx,booktabs,array,longtable,xcolor,hyperref,xurl,fancyhdr}',r'\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue,pdftitle={QAOA methods and congestion atlas}}',r'\pagestyle{fancy}\fancyhf{}\fancyfoot[L]{\footnotesize QAOA | Methods and structural congestion}\fancyfoot[R]{\thepage}',r'\setlength{\headheight}{14pt}\setlength{\parindent}{0pt}\setlength{\parskip}{6pt}\renewcommand{\arraystretch}{1.1}',r'\begin{document}']
    for item in story:
        if isinstance(item,Paragraph):
            parser=Inline(); parser.feed(item.text); content=''.join(parser.parts)
            if item.style.name=='Title': texlines.append(r'{\LARGE\bfseries '+content+r'\par}')
            elif item.style.name=='Heading1': texlines.append(r'\section*{'+content+'}')
            elif item.style.name=='Heading2': texlines.append(r'\subsection*{'+content+'}')
            else: texlines.append(content+r'\par')
        elif isinstance(item,Table):
            n=len(item._cellvalues[0]); texlines.append(r'\begingroup\small\setlength{\tabcolsep}{4pt}\begin{center}\begin{tabular}{'+('l'+'r'*(n-1))+r'}\toprule')
            for i,row in enumerate(item._cellvalues):
                texlines.append(' & '.join(latex_escape(x) for x in row)+r' \\')
                if i==0: texlines.append(r'\midrule')
            texlines.append(r'\bottomrule\end{tabular}\end{center}\endgroup')
        elif isinstance(item,Image): texlines.append(r'\begin{center}\includegraphics[width=\linewidth]{\detokenize{'+str(Path(item.filename).relative_to(OUT))+r'}}\end{center}')
        elif isinstance(item,PageBreak): texlines.append(r'\clearpage')
    texlines.append(r'\end{document}')
    (OUT/'main.tex').write_text('\n'.join(texlines)+'\n')
    pdf=OUT/'qaoa_methods_and_congestion.pdf'
    SimpleDocTemplate(str(pdf),pagesize=(595.28,841.89),leftMargin=50,rightMargin=50,topMargin=40,bottomMargin=43,title='QAOA methods and congestion atlas',author='BTP research study').build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader, PdfWriter
    writer=PdfWriter(); writer.clone_document_from_reader(PdfReader(pdf))
    for page,title in enumerate(('Circuit and mapping','Routing and ACE pipeline','Congestion definitions','Overview: hop counting','Overview: route counting')):
        writer.add_outline_item(title,page)
    page=5
    for topology,route in ARMS:
        parent=writer.add_outline_item(topology+' / '+route,page)
        for variant in ('hop','route'):
            child=writer.add_outline_item(variant+' counting',page,parent=parent)
            for cap in CAPS:
                writer.add_outline_item('Capacity '+str(cap)+' | seeds 42/43/44',page,parent=child); page+=3
    with pdf.open('wb') as stream: writer.write(stream)
    (OUT/'validation.json').write_text(json.dumps(dict(heatmaps=210,core_rows=3360,trace_aliases=15,distinct_traces=len({r['trace_sha256'] for r in cores}),all_trace_hashes_checked=True,all_core_metrics_recomputed=True,index=index),indent=2))
    print(pdf)

if __name__=='__main__': main()
