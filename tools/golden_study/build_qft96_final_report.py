#!/usr/bin/env python3
"""Audit the completed QFT-96 campaign and build its standalone report.

No simulator is launched and no historical result is edited. Rebuild with:
python -m tools.golden_study.build_qft96_final_report
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, stdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .run_execution import read_jobs, validate_output, verify_source_lock
from .run_qft96_dynamic_variants import VARIANTS, validate_output as validate_variant
from .summarize_execution import METRICS as ARCHIVED_METRICS, policy_label

REPO = Path(__file__).resolve().parents[2]
STUDY = REPO / "results/qft96_2seed_2026-10-26"
OUT = REPO / "docs/latex/qft96_final"
WEB = "https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE"
ROUTES = [("mesh", "xy"), ("mesh", "yx"), ("mesh", "shortest_reliable"), ("mesh", "max_reliability"), ("torus", "dijkstra")]
POLICIES = ["ODG", "CGP", "ACGP", "Dynamic-full-chain", "Dynamic-first-hop"]
LABELS = {"ODG":"ODG", "CGP":"CGP", "ACGP":"ACGP", "Dynamic-full-chain":"Dynamic full", "Dynamic-first-hop":"Dynamic first"}
COLORS = dict(zip(POLICIES, ["#111111", "#d18800", "#b0549a", "#0072b2", "#56b4e9"]))
TITLES = {
    "request_latency_mean_ms":"Mean request latency", "request_latency_median_ms":"Median request latency",
    "request_latency_p95_ms":"p95 request latency", "request_latency_max_ms":"Maximum request latency",
    "end_to_end_latency_ms":"Communication makespan", "average_admission_wait_ms":"Mean admission wait",
    "max_admission_wait_ms":"Maximum admission wait", "requests_that_waited_fraction":"Requests with admission wait",
    "avg_reservation_setup_time_ms":"Recorded reservation-setup counter", "avg_entanglement_generation_time_ms":"Mean generation/service time",
    "avg_retry_wait_time_ms":"Recorded retry-wait time", "average_delivered_epr_fidelity":"Delivered EPR fidelity",
    "total_retries":"Request retries", "requests_with_retries":"Requests with retries",
    "protocol_generated_pairs":"Native-protocol generated-pair counter", "protocol_used_pairs":"Native-protocol used-pair counter",
    "protocol_unused_pairs":"Native-protocol unused-pair counter", "protocol_waste_percentage":"Native-protocol waste",
    "scheduled_preparations":"Scheduled compiler preparations", "planner_blocked_preparations":"Planner-blocked preparations",
    "planner_peak_compiler_memory_per_core":"Planner peak compiler memory",
    "runtime_admission_attempts":"Compiler preparation admission attempts", "runtime_launched_preparations":"Launched compiler preparations",
    "runtime_accepted_preparations":"Accepted compiler preparations", "runtime_rejected_preparations":"Rejected compiler preparations",
    "pregenerated_hits":"Compiler-ready request count", "pregenerated_success_rate":"Compiler readiness fraction",
    "intended_request_hits":"Intended compiler-hit count", "intended_request_hit_rate":"Intended compiler-hit fraction",
    "compiler_not_ready_requests":"Compiler-not-ready request count", "late_compiler_pair_uses":"Late compiler-pair uses",
    "on_demand_fallbacks":"Compiler fallback count", "on_demand_fallback_rate":"Compiler fallback fraction",
    "generated_compiler_pairs":"Generated compiler pairs", "utilized_compiler_pairs":"Used compiler pairs",
    "expired_compiler_pairs":"Expired compiler pairs", "remaining_compiler_pairs":"Remaining compiler pairs",
    "compiler_expiry_percentage":"Compiler-pair expiry", "compiler_waste_percentage":"Compiler-cache waste",
    "average_fidelity_at_creation":"Compiler fidelity at creation", "average_fidelity_at_utilization":"Compiler fidelity at use",
    "average_storage_time_ms":"Used compiler-pair storage time", "completion_rate":"Completion fraction",
    "hop_throughput_s":"Delivered-hop throughput", "avg_layer_latency_ms":"Mean layer latency",
    "max_layer_latency_ms":"Maximum layer latency", "min_layer_latency_ms":"Minimum layer latency",
}
PRIMARY = ["request_latency_mean_ms", "request_latency_median_ms", "request_latency_p95_ms", "request_latency_max_ms",
           "end_to_end_latency_ms", "average_admission_wait_ms", "average_delivered_epr_fidelity",
           "pregenerated_success_rate", "intended_request_hit_rate", "on_demand_fallback_rate",
           "compiler_waste_percentage", "protocol_waste_percentage", "compiler_expiry_percentage",
           "average_storage_time_ms", "hop_throughput_s", "completion_rate"]
METRICS = PRIMARY + [m for m in ARCHIVED_METRICS if m not in PRIMARY] + ["avg_layer_latency_ms", "max_layer_latency_ms", "min_layer_latency_ms"]
COMMON = set(ARCHIVED_METRICS[:14]) | {"completion_rate", "hop_throughput_s", "avg_layer_latency_ms", "max_layer_latency_ms", "min_layer_latency_ms"}
PROTOCOL = {"protocol_generated_pairs", "protocol_used_pairs", "protocol_unused_pairs", "protocol_waste_percentage"}
VARIANT_METRICS = PRIMARY
checks, sources, jobs_ledger, raw_base, raw_variants = [], {}, [], [], []


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source(path):
    path = Path(path)
    key = str(path.relative_to(REPO))
    if key not in sources: sources[key] = {"path": key, "sha256": digest(path)}
    return path


def js(path):
    return json.loads(source(path).read_text())


def read_csv(path):
    with source(path).open(newline="") as f: return list(csv.DictReader(f))


def write_csv(name, rows):
    path = OUT / "data" / (name + ".csv"); path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rows)


def check(name, ok, detail=""):
    checks.append({"check": name, "passed": bool(ok), "detail": detail})
    if not ok: raise ValueError(name + ": " + str(detail))


def text(s):
    return str(s).replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")


def url(name):
    return WEB + "/blob/codex/ace-scheduler-correctness/docs/latex/qft96_final/data/" + name + ".csv"


def unit(metric):
    if metric == "end_to_end_latency_ms": return "s", .001
    if metric.endswith("_ms"): return "ms", 1
    if metric.endswith("percentage"): return "%", 1
    if metric == "hop_throughput_s": return "hops/s", 1
    if "fidelity" in metric: return "", 1
    if metric.endswith("rate") or metric.endswith("fraction"): return "fraction", 1
    return "count", 1


def applicable(policy, metric):
    if policy.startswith("Dynamic") or policy == "variant": return True
    if metric in PROTOCOL: return policy in ("CGP", "ACGP")
    return metric in COMMON


def stats(rows, metric, policy):
    if not applicable(policy, metric): return None
    # Aggregate CSV column names retain the runner's native units. Conversion
    # belongs only to presentation tables/figures, e.g. makespan ms -> seconds.
    values = [float(r[metric]) for r in rows if r.get(metric) not in (None, "") and math.isfinite(float(r[metric]))]
    if not values: return None
    return fmean(values), stdev(values) if len(values)>1 else 0., len(values)


def fmt(s):
    if s is None: return "n/a"
    mean,sd,n=s
    digits = 4 if abs(mean)<1 else (2 if abs(mean)>100 else 3)
    return f"${mean:.{digits}f}\\pm{sd:.{digits}f}$"


def table(headers, rows, csvname, caption=""):
    lines = [r"\begin{center}{\scriptsize\setlength{\tabcolsep}{3pt}",
             r"\begin{tabular}{"+"l"+"r"*(len(headers)-1)+"}", r"\toprule",
             " & ".join(map(text,headers))+r" \\", r"\midrule"]
    lines += [" & ".join(map(str,r))+r" \\" for r in rows]
    lines += [r"\bottomrule\end{tabular}}",r"\captionof{table}{"+caption+"}",
              r"{\footnotesize\href{"+url(csvname)+r"}{Exact CSV values and sample counts}}",r"\end{center}"]
    return "\n".join(lines)


def figure(name, caption, height=".255"):
    return r"\begin{center}\includegraphics[width=.94\linewidth,height="+height+r"\textheight,keepaspectratio]{figures/"+name+r".pdf}\captionof{figure}{"+caption+r"}\end{center}"


def save(name):
    path=OUT/"figures"/name;path.parent.mkdir(parents=True,exist_ok=True)
    plt.savefig(path.with_suffix(".pdf"),bbox_inches="tight",metadata={"CreationDate":None,"ModDate":None})
    # PNG previews are retained for substantive summary figures and the atlas.
    if name.startswith(("atlas/","summary/")):plt.savefig(path.with_suffix(".png"),dpi=150,bbox_inches="tight")
    plt.close()


def metadata_check(job, variant, lock):
    directory=STUDY/job["output_path"]
    if variant: validate_variant(directory,job)
    else: validate_output(directory,job,require_execution_record=True)
    md=js(directory/"metadata.json");record=js(directory/"execution.json");rows=read_csv(directory/"summary.csv")
    expected={(s,str(seed)) for s in (["dynamic"] if variant else job["runner_strategies"]) for seed in job["physics_seeds"]}
    check("unique complete seed rows "+job["job_id"],len(rows)==len(expected) and {(r["strategy"],r["seed"]) for r in rows}==expected and all(int(r["completed_requests"])==int(r["requests"])==md["trace_requests"] and float(r["completion_rate"])==1 and int(r["metric_version"])==3 for r in rows))
    check("SeQUeNCe record "+job["job_id"],record["sequence"]==lock["sequence"])
    check("source hashes in metadata "+job["job_id"],all(lock["repository_files"].get(k)==v for k,v in md["source_sha256"].items()))
    expected_params=dict(job["runner_parameters"])
    if not variant:
        expected_params.update(total_memories=job["total_memories_per_core"],compiler_memories=job["compiler_memories_per_core"],generation_capacity=job["generation_capacity_per_core"])
    expected_params.update(chain_hops_prepared=job["chain_hops_prepared"],congestion_threshold=None)
    failures={k:(md["parameters"].get(k),v) for k,v in expected_params.items() if k!="starvation_guard" and md["parameters"].get(k)!=v}
    check("all runtime parameters "+job["job_id"],not failures,str(failures))
    check("starvation guard "+job["job_id"],md["parameters"]["no_starvation_guard"]== (not expected_params["starvation_guard"]))
    for r in rows:
        r["hop_throughput_s"]=1000*int(r["completed_requests"])/float(r["end_to_end_latency_ms"])
    jobs_ledger.append({"job_id":job["job_id"],"phase":"variants" if variant else "base","git_sha":record["git_sha"],"trace_sha256":job["trace_sha256"],"config_sha256":job["config_sha256"],"summary_sha256":digest(directory/"summary.csv"),"metadata_sha256":digest(directory/"metadata.json"),"execution_sha256":digest(directory/"execution.json"),"output_path":job["output_path"],"policy_seed_rows":len(rows)})
    return rows,record


def verify_campaign():
    scope=js(STUDY/"execution_scope.json");spec=js(STUDY/"execution_spec.json");lock=js(STUDY/spec["source_lock"])
    check("official manifest hash",digest(source(STUDY/scope["base_manifest"]))==scope["base_manifest_sha256"])
    jobs=read_jobs(STUDY/scope["base_manifest"]);varjobs=js(STUDY/"manifests/dynamic-variants_jobs.json")["jobs"]
    memories=scope["included_total_memories_per_core"]
    check("official job count",len(jobs)==scope["official_job_count"])
    commits,inputs=set(),set()
    for variant,entries in [(False,jobs),(True,varjobs)]:
        for job in entries:
            for path,h in [(STUDY/job["trace_path"],job["trace_sha256"]),(REPO/job["config_path"],job["config_sha256"])]:
                if str(path) not in inputs:check("input hash "+str(path.relative_to(REPO)),digest(source(path))==h);inputs.add(str(path))
            rows,record=metadata_check(job,variant,lock)
            if record["git_sha"] not in commits:
                verify_source_lock(REPO,lock,commit=record["git_sha"]);commits.add(record["git_sha"])
            alias=job if variant else job["trace_aliases"][0]
            for row in rows:
                policy=job["variant"] if variant else policy_label(job["execution_group"],row["strategy"])
                raw={"job_id":job["job_id"],"topology":job["topology"],"route":alias["route_policy"],"trace_sha256":job["trace_sha256"],"M":4 if variant else job["total_memories_per_core"],"C":3 if variant else job["compiler_memories_per_core"],"policy":policy,**row}
                (raw_variants if variant else raw_base).append(raw)
    check("base policy-seed evaluations",len(raw_base)==sum(len(j["runner_strategies"])*len(j["physics_seeds"]) for j in jobs))
    check("no excluded memory",all(int(r["M"]) in memories for r in raw_base))
    write_csv("per_seed_base",raw_base);write_csv("per_seed_variants",raw_variants);write_csv("job_provenance",jobs_ledger)
    # Check all saved aggregate values, including within-trace SD.
    grouped=defaultdict(list)
    for r in raw_base:grouped[r["job_id"],r["policy"]].append(r)
    saved_rows=read_csv(STUDY/"summaries/base-evaluation-progress.csv")
    check("complete saved aggregate row set",len(saved_rows)==len(grouped) and {(r["job_id"],r["policy"]) for r in saved_rows}==set(grouped))
    for saved in saved_rows:
        group=grouped[saved["job_id"],saved["policy"]]
        for metric in ARCHIVED_METRICS:
            values=[float(r[metric]) for r in group if r.get(metric) not in (None,"")]
            expected=(fmean(values),stdev(values) if len(values)>1 else 0.) if values else (None,None)
            for suffix,value in zip(("mean","sd"),expected):
                actual=saved[metric+"_"+suffix]
                if value is None:ok=actual in (None,"")
                else:ok=math.isclose(float(actual),value,rel_tol=1e-11,abs_tol=1e-11)
                if not ok:raise ValueError(f"Aggregate mismatch {saved['job_id']} {metric} {suffix}")
    check("all saved base aggregates independently reproduced",True)
    print(f"validated {len(jobs)} base jobs / {len(raw_base)} evaluations and {len(varjobs)} variant jobs / {len(raw_variants)} evaluations",flush=True)
    return memories


def parse_routes(path,placement):
    initial={};positions={};layers=defaultdict(dict);layer=None;declared=[];seen_order=defaultdict(list)
    for line in source(path).read_text().splitlines():
        line=line.strip()
        if line.lower().startswith("// layer"):
            if layer is not None:check("placement replay "+path.name+str(layer),[positions[q] for q in range(len(initial))]==placement["assignments"][layer])
            layer=int(line.split()[-1]);declared.append(layer)
        elif line.startswith("("):
            v=tuple(map(int,line.strip("()").split(",")))
            if len(v)==2 and layer is None:initial[v[0]]=v[1];positions[v[0]]=v[1]
            elif len(v)==3:
                q,s,t=v
                if positions.get(q)!=s:raise ValueError("invalid source in "+str(path))
                coordinates=[divmod(c,4) for c in (s,t)];d=[abs(a-b) for a,b in zip(*coordinates)]
                if placement["topology"]=="torus":d=[min(v,4-v) for v in d]
                if not (0<=s<16 and 0<=t<16 and sum(d)==1):raise ValueError("invalid topology edge")
                if q not in layers[layer]:layers[layer][q]=[s];seen_order[layer].append(q)
                elif seen_order[layer][-1]!=q:raise ValueError("non-contiguous migration in trace")
                layers[layer][q].append(t);positions[q]=t
    check("initial placement and 766 layers "+str(path),len(initial)==96 and [initial[q] for q in range(96)]==placement["initial_assignment"] and declared==list(range(len(placement["assignments"]))))
    check("final placement replay "+str(path),[positions[q] for q in range(96)]==placement["assignments"][-1])
    route_policy=path.parent.name
    for paths in layers.values():
        for route in paths.values():
            start,end=route[0],route[-1]
            if route_policy in ("xy","yx"):
                coord=list(divmod(start,4));target=divmod(end,4);expected=[start]
                for dim in ((0,1) if route_policy=="xy" else (1,0)):
                    while coord[dim]!=target[dim]:
                        coord[dim]+=1 if target[dim]>coord[dim] else -1;expected.append(coord[0]*4+coord[1])
                if route!=expected:raise ValueError("dimension-order route mismatch: "+str(path))
            elif route_policy in ("shortest_reliable","dijkstra"):
                delta=[abs(a-b) for a,b in zip(divmod(start,4),divmod(end,4))]
                if placement["topology"]=="torus":delta=[min(d,4-d) for d in delta]
                if len(route)-1!=sum(delta):raise ValueError("non-shortest route: "+str(path))
    check("dimension-order / shortest-hop route property "+str(path),True)
    return layers


def verify_congestion(memories):
    audit=read_csv(STUDY/"validation/mapping_audit.csv")
    cores_saved=read_csv(STUDY/"congestion/per_core_congestion.csv")
    summary_saved=read_csv(STUDY/"congestion/trace_congestion_summary.csv")
    core_lookup={(r["topology"],r["route_policy"],int(r["mapping_seed"]),int(r["capacity"]),r["variant"],int(r["core"])):r for r in cores_saved}
    summary_lookup={(r["topology"],r["route_policy"],int(r["mapping_seed"]),int(r["capacity"]),r["variant"]):r for r in summary_saved}
    verified=[];structures=[];atlas=[]
    for alias in audit:
        topology,route,seed=alias["topology"],alias["route_policy"],int(alias["mapping_seed"])
        parent=STUDY/f"traces/placements/{topology}/T-HQA/qft96/seed_{seed}"
        placement=js(parent/"placement.json");path=parent/f"routes/{route}/requests.txt"
        check("trace hash "+str(path),digest(source(path))==alias["request_trace_sha256"])
        layers=parse_routes(path,placement);active=len(layers)
        structures.append({"topology":topology,"route":route,"mapping_seed":seed,"placement_signature":placement["provenance"]["placement_signature"],"trace_sha256":alias["request_trace_sha256"],"active_layers":active,"layers":len(placement["assignments"]),"logical_migrations":sum(len(v) for v in layers.values()),"physical_hops":sum(len(p)-1 for v in layers.values() for p in v.values())})
        for counting in ("route","hop"):
            demands={};endpoints={}
            for l,paths in layers.items():
                d,e=Counter(),Counter()
                for p in paths.values():
                    e[p[0]]+=1;e[p[-1]]+=1
                    if counting=="route":d.update(set(p))
                    else:
                        for a,b in zip(p,p[1:]):d[a]+=1;d[b]+=1
                demands[l]=d;endpoints[l]=e
            for m in memories:
                key=(topology,route,seed,m,counting);saved=summary_lookup[key]
                hot_layers=sum(any(v>m for v in d.values()) for d in demands.values())
                excess=sum(max(0,d[c]-m) for d in demands.values() for c in range(16))
                hot_cells=sum(d[c]>m for d in demands.values() for c in range(16))
                check("congestion totals "+str(key),int(saved["active_layers"])==active and int(saved["overloaded_layers"])==hot_layers and int(saved["excess_demand"])==excess and int(saved["overloaded_core_layers"])==hot_cells)
                image=STUDY/f"congestion/heatmaps/{topology}__{route}__seed{seed}__cap{m}__{counting}.png"
                check("original heatmap exists "+str(key),image.is_file());source(image)
                atlas.append({"topology":topology,"route":route,"seed":seed,"M":m,"counting":counting,"original_image":str(image.relative_to(REPO)),"sha256":digest(image)})
                for c in range(16):
                    total=sum(d[c]>m for d in demands.values());own=sum(e[c]>m for e in endpoints.values())
                    relay=sum(endpoints[l][c]<=m<demands[l][c] for l in layers)
                    row={"topology":topology,"route":route,"seed":seed,"M":m,"counting":counting,"core":c,"active_layers":active,"overloaded_percent":100*total/active,"own_percent":100*own/active,"relay_only_percent":100*relay/active}
                    check("disjoint overload partition "+str(key)+str(c),total==own+relay)
                    savedcore=core_lookup[key+(c,)]
                    check("heatmap values "+str(key)+str(c),all(math.isclose(float(savedcore[k]),row[k],abs_tol=1e-9) for k in ("overloaded_percent","own_percent","relay_only_percent")))
                    verified.append(row)
    check("all 210 heatmap cells",len(atlas)==len(summary_saved)==210 and len(verified)==len(cores_saved)==3360)
    check("common T-HQA placement across mesh and torus",len({r["placement_signature"] for r in structures})==1)
    write_csv("congestion_verified",verified);write_csv("heatmap_inventory",atlas);write_csv("trace_structure",structures)
    print("independently verified every value in 210 heatmaps (3360 core rows)",flush=True)
    return verified,structures


def aggregate(rows,group_keys,metrics):
    groups=defaultdict(list)
    for r in rows:groups[tuple(r[k] for k in group_keys)].append(r)
    result=[]
    for key,group in sorted(groups.items()):
        policy=key[group_keys.index("policy")] if "policy" in group_keys else "variant"
        if policy not in POLICIES:policy="variant"
        row=dict(zip(group_keys,key));row["observations"]=len(group);row["distinct_traces"]=len({r["trace_sha256"] for r in group})
        for metric in metrics:
            s=stats(group,metric,policy)
            row[metric+"_mean"],row[metric+"_sd"],row[metric+"_n"]=(s if s else ("","",0))
        result.append(row)
    return result


def cached(row,metric):
    scale=unit(metric)[1]
    return None if row[metric+"_mean"]=="" else (row[metric+"_mean"]*scale,row[metric+"_sd"]*scale,row[metric+"_n"])


def build_atlas(verified,memories):
    output=[]
    for topology,route in ROUTES:
        output.append(r"\section{"+text(topology.title()+" / "+route)+"}")
        for counting in ("route","hop"):
            for m in memories:
                rows=[r for r in verified if r["topology"]==topology and r["route"]==route and r["M"]==m and r["counting"]==counting]
                seeds=sorted({r["seed"] for r in rows});fields=["overloaded_percent","own_percent","relay_only_percent"]
                fig,axes=plt.subplots(3,3,figsize=(9,7.3),constrained_layout=True)
                for i,seed in enumerate(seeds):
                    for j,field in enumerate(fields):
                        ax=axes[i,j];lookup={r["core"]:r[field] for r in rows if r["seed"]==seed}
                        grid=np.array([lookup[c] for c in range(16)]).reshape(4,4)
                        im=ax.imshow(grid,cmap="YlOrRd",vmin=0,vmax=100)
                        ax.set_title(["Total overload","Source/destination","Relay-only"][j]+f"; seed {seed}",fontsize=9)
                        ax.set_xticks([]);ax.set_yticks([])
                        for c in range(16):
                            value=lookup[c];ax.text(c%4,c//4,f"C{c}\n{value:.1f}%",ha="center",va="center",fontsize=6.5,color="white" if value>60 else "black")
                fig.colorbar(im,ax=axes,shrink=.7,label="% of communication-active layers",pad=.015)
                name=f"atlas/{topology}_{route}_{counting}_m{m}";save(name)
                csvname=f"heatmap_{topology}_{route}_{counting}_m{m}";write_csv(csvname,rows)
                output += [r"\clearpage\subsection*{"+text(f"{topology.title()} {route}; M={m}; {counting} counting")+"}",figure(name,"All three conceptual mapping seeds; common 0--100 percent colour scale.",".48")]
                headers=["Core"]+[f"{s} {p}" for s in seeds for p in ("Tot","Own","Rel")]
                body=[]
                for c in range(16):body.append([c]+[f'{next(r for r in rows if r["seed"]==s and r["core"]==c)[f]:.3f}' for s in seeds for f in fields])
                output.append(table(headers,body,csvname,"Exact heatmap percentages, with Tot = Own + Rel. Unrounded values are in the CSV."))
    (OUT/"generated/congestion.tex").write_text("\n".join(output))


def congestion_overview(memories):
    original=read_csv(STUDY/"congestion/trace_congestion_summary.csv")
    fields=[("overloaded_layer_percent","Overloaded active layers (%)"),("overloaded_core_layers","Overloaded core-layers"),("excess_demand","Excess demand")]
    aggregated=[]
    for topology,route in ROUTES:
        for counting in ("route","hop"):
            for m in memories:
                group=[r for r in original if r["topology"]==topology and r["route_policy"]==route and r["variant"]==counting and int(r["capacity"])==m]
                row={"topology":topology,"route":route,"counting":counting,"M":m,"conceptual_seed_count":len(group)}
                for field,_ in fields:
                    xs=[float(r[field]) for r in group];row[field+"_mean"]=fmean(xs);row[field+"_sd"]=stdev(xs)
                aggregated.append(row)
    write_csv("congestion_overview",aggregated);lines=[]
    for counting in ("route","hop"):
        for field,label in fields:
            fig,ax=plt.subplots(figsize=(8,3.5),constrained_layout=True)
            for top,route in ROUTES:
                group=sorted([r for r in aggregated if r["topology"]==top and r["route"]==route and r["counting"]==counting],key=lambda r:r["M"])
                ax.errorbar([r["M"] for r in group],[r[field+"_mean"] for r in group],yerr=[r[field+"_sd"] for r in group],marker="o",capsize=2,label=top+" / "+route.replace("_"," "))
            ax.set_xticks(memories);ax.set_xlabel("Communication memories per core, M");ax.set_ylabel(label);ax.legend(fontsize=7);ax.grid(alpha=.2)
            name=f"summary/congestion_{counting}_{field}";save(name)
            lines += [r"\clearpage\section*{"+text(counting.title()+" counting: "+label)+"}",figure(name,"Mean and sample SD across three conceptual reliability-seed labels. Identical route aliases are not independent mappings.",".34"),table(["M","XY","YX","Short-rel","Max-rel","Torus Dijk."],[[m]+[fmt((next(v for v in aggregated if (v["topology"],v["route"],v["counting"],v["M"])==(t,r,counting,m))[field+"_mean"],next(v for v in aggregated if (v["topology"],v["route"],v["counting"],v["M"])==(t,r,counting,m))[field+"_sd"],3)) for t,r in ROUTES] for m in memories],"congestion_overview",text(label)+" for "+counting+" counting.")]
    (OUT/"generated/congestion_overview.tex").write_text("\n".join(lines))


def plot_curves(points,metric,name,xkey="M",policies=POLICIES):
    fig,ax=plt.subplots(figsize=(8,3.1),constrained_layout=True)
    any_data=False
    for j,p in enumerate(policies):
        subset=sorted([r for r in points if r["policy"]==p and r[metric+"_n"]],key=lambda r:float(r[xkey]))
        if not subset:continue
        any_data=True
        ax.errorbar([r[xkey] for r in subset],[cached(r,metric)[0] for r in subset],yerr=[cached(r,metric)[1] for r in subset],marker="o",ms=3,lw=1.2,capsize=2,color=COLORS.get(p,plt.get_cmap("tab10")(j)),label=LABELS.get(p,p))
    if not any_data:ax.text(.5,.5,"Metric not recorded for this group",ha="center",transform=ax.transAxes)
    xs=sorted({r[xkey] for r in points});ax.set_xticks(xs if len(xs)<=12 else sorted(set(xs[::4]+[xs[-1]])));ax.set_xlabel("Shared communication memories per core, M" if xkey=="M" else "Cache allowance per core, C")
    u,_=unit(metric);ax.set_ylabel("\n".join(textwrap.wrap(TITLES[metric]+(f" ({u})" if u else ""),35)));ax.grid(alpha=.2)
    if any_data:ax.legend(fontsize=7,ncol=min(len(policies),3))
    save(name)


def main_curves(aggregated):
    for topology in ("mesh","torus"):
        lines=[]
        for top,route in ROUTES:
            if top!=topology:continue
            lines.append(r"\section{"+text({"xy":"XY","yx":"YX"}.get(route,route.replace("_"," ").title()))+"}")
            points=[r for r in aggregated if r["topology"]==top and r["route"]==route and r["C"]==(0 if r["policy"]=="ODG" else r["M"]-1)]
            memories=sorted({r["M"] for r in points})
            for i,metric in enumerate(METRICS):
                if i%2==0:lines.append(r"\clearpage")
                name=f"memory/{top}_{route}_{metric}";plot_curves(points,metric,name)
                data=[]
                for m in memories:
                    record={"M":m,"unit":unit(metric)[0]}
                    for p in POLICIES:
                        value=cached(next(r for r in points if r["M"]==m and r["policy"]==p),metric)
                        record.update({f"{p}_{suffix}":(value[j] if value else (0 if suffix=="n" else "")) for j,suffix in enumerate(("mean","sd","n"))})
                    data.append(record)
                csvname=f"memory_{top}_{route}_{metric}";write_csv(csvname,data)
                lines.extend([r"\subsection*{"+text(TITLES[metric])+"}",figure(name,"Run-level mean and sample SD. Shared trace aliases are counted once."),table(["M"]+[LABELS[p] for p in POLICIES],[[m]+[fmt(cached(next(r for r in points if r["M"]==m and r["policy"]==p),metric)) for p in POLICIES] for m in memories],csvname,"Mean $\\pm$ sample SD; n/a denotes a metric outside that policy's instrumentation.")])
            print("generated complete metric curves:",top,route,flush=True)
        (OUT/f"generated/{topology}_metrics.tex").write_text("\n".join(lines))


def allocation_curves(aggregated):
    lines=[]
    for topology,route in ROUTES:
        lines.append(r"\section{"+text(topology.title()+" / "+route)+"}")
        memories=sorted({r["M"] for r in aggregated if r["topology"]==topology and r["route"]==route})
        for m in memories:
            points=[r for r in aggregated if r["topology"]==topology and r["route"]==route and r["M"]==m]
            odg=next(r for r in points if r["policy"]=="ODG")
            allocations=sorted({r["C"] for r in points});expanded=[r for r in points if r["policy"]!="ODG"]+[dict(odg,C=c) for c in allocations]
            metric="request_latency_mean_ms";name=f"allocation/{topology}_{route}_m{m}";plot_curves(expanded,metric,name,"C")
            csvname=f"allocation_{topology}_{route}_m{m}";write_csv(csvname,points)
            lines += [r"\clearpage\subsection*{"+text(f"M={m}: every cache allowance")+"}",figure(name,"All legal C values; ODG's C=0 result is repeated as a horizontal reference, not rerun at C>0.",".31"),table(["C"]+[LABELS[p] for p in POLICIES],[[c]+[fmt(cached(next(r for r in expanded if r["C"]==c and r["policy"]==p),metric)) for p in POLICIES] for c in allocations],csvname,"Mean hop latency (ms), mean $\\pm$ SD. The linked CSV includes every recorded metric for every allocation.")]
    (OUT/"generated/allocations.tex").write_text("\n".join(lines))


def variant_figures(aggregated):
    lines=[]
    for topology,route in ROUTES:
        lines.append(r"\section{"+text(topology.title()+" / "+route)+"}")
        group=[r for r in aggregated if r["topology"]==topology and r["route"]==route];variants=sorted(r["policy"] for r in group)
        for metric in VARIANT_METRICS:
            fig,ax=plt.subplots(figsize=(8,3.5),constrained_layout=True)
            for i,v in enumerate(variants):
                r=next(r for r in group if r["policy"]==v);s=cached(r,metric)
                if s:ax.errorbar(i,s[0],yerr=s[1],fmt="o",capsize=2,color=plt.get_cmap("tab20")(i))
            ax.set_xticks(range(len(variants)),[v.replace("-", " ") for v in variants],rotation=55,ha="right",fontsize=6.5)
            u,_=unit(metric);ax.set_ylabel(TITLES[metric]+(f" ({u})" if u else ""));ax.grid(alpha=.2)
            name=f"variants/{topology}_{route}_{metric}";save(name)
            csvname=f"variants_{topology}_{route}_{metric}";write_csv(csvname,[{"variant":r["policy"],"unit":unit(metric)[0],"mean":cached(r,metric)[0] if cached(r,metric) else "","sd":cached(r,metric)[1] if cached(r,metric) else "","n":r[metric+"_n"]} for r in group])
            lines.extend([r"\clearpage\subsection*{"+text(TITLES[metric])+"}",figure(name,"Thirteen Dynamic launch variants, M=4 and C=3; zero-delay structural rules and delay sensitivities are distinguished in the definitions.",".31"),table(["Variant","Mean $\\pm$ SD","n"],[[text(v),fmt(cached(next(r for r in group if r["policy"]==v),metric)),next(r for r in group if r["policy"]==v)[metric+"_n"]] for v in variants],csvname,"All thirteen variants; n counts byte-distinct trace/physics runs, not conceptual aliases.")])
        print("generated launch-variant results:",topology,route,flush=True)
    (OUT/"generated/variants.tex").write_text("\n".join(lines))


def build():
    ap=argparse.ArgumentParser();ap.add_argument("--verify-only",action="store_true");args=ap.parse_args()
    for folder in ("data","figures","generated"):(OUT/folder).mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.size":9,"axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42})
    memories=verify_campaign();verified,structure=verify_congestion(memories)
    base=aggregate(raw_base,["topology","route","M","C","policy"],METRICS)
    variants=aggregate(raw_variants,["topology","route","policy"],METRICS)
    expected={(t,r,m,c,p) for t,r in ROUTES for m in memories for p in POLICIES for c in ([0] if p=="ODG" else range(m))}
    check("every legal base route/memory/allocation/policy cell",{(r["topology"],r["route"],r["M"],r["C"],r["policy"]) for r in base}==expected)
    check("every registered launch variant on every route",{(r["topology"],r["route"],r["policy"]) for r in variants}=={(t,r,v) for t,r in ROUTES for v in VARIANTS})
    write_csv("all_allocations_all_metrics",base);write_csv("all_variants_all_metrics",variants)
    write_csv("source_ledger",list(sources.values()))
    status={"schema":"qft96-final-report-audit-v1","source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),"base_jobs":len([r for r in jobs_ledger if r["phase"]=="base"]),"variant_jobs":len([r for r in jobs_ledger if r["phase"]=="variants"]),"base_evaluations":len(raw_base),"variant_evaluations":len(raw_variants),"memories":memories,"base_aggregate_cells":len(base),"variant_aggregate_cells":len(variants),"metric_count":len(METRICS),"checks":len(checks),"all_passed":all(r["passed"] for r in checks),"heatmaps":210,"core_rows":len(verified)}
    (OUT/"data/validation.json").write_text(json.dumps({**status,"details":checks},indent=2)+"\n")
    print(json.dumps(status,indent=2),flush=True)
    if args.verify_only:return
    congestion_overview(memories)
    build_atlas(verified,memories);print("generated 70 readable grouped atlas pages",flush=True)
    main_curves(base);allocation_curves(base);variant_figures(variants)
    # Definitive matched-cell table, using exactly the same primary curve slice.
    rows=[r for r in base if r["M"]==4 and r["C"]==(0 if r["policy"]=="ODG" else 3)]
    write_csv("matched_m4_c3",rows)
    body=[]
    for top,route in ROUTES:
        group=[r for r in rows if r["topology"]==top and r["route"]==route]
        body.append(r"\section*{"+text(top.title()+" / "+route)+"}")
        body.append(table(["Policy","Latency ms","p95 ms","Makespan s","Delivered F"],[[LABELS[r["policy"]]]+[fmt(cached(r,m)) for m in ("request_latency_mean_ms","request_latency_p95_ms","end_to_end_latency_ms","average_delivered_epr_fidelity")] for r in group],"matched_m4_c3","M=4; ODG C=0, cached methods C=3. These are final measured results, not policy-selected optima."))
    (OUT/"generated/matched.tex").write_text("\n".join(body))
    # Exhaustive machine-readable registry makes omissions detectable.
    registry=[]
    for i,m in enumerate(METRICS):registry.append({"field":m,"title":TITLES[m],"native_unit":"ms" if m.endswith("_ms") else unit(m)[0],"display_unit":unit(m)[0],"display_scale":unit(m)[1],"policies":";".join(p for p in POLICIES if applicable(p,m)),"main_route_memory_figures":len(ROUTES),"variant_figures":len(ROUTES) if m in VARIANT_METRICS else 0})
    write_csv("metric_registry",registry)
    print("report assets ready",flush=True)


if __name__=="__main__":build()
