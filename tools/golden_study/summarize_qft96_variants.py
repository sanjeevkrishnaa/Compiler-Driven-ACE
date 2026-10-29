#!/usr/bin/env python3
"""Aggregate validated QFT-96 Dynamic-policy variant jobs and draw metrics."""
from __future__ import annotations

import argparse, csv, json, math
from collections import defaultdict
from pathlib import Path
from statistics import fmean, stdev

METRICS = (
    ("average_request_latency_ms", "Mean latency", "ms"),
    ("request_latency_p95_ms", "p95 latency", "ms"),
    ("end_to_end_latency_ms", "Makespan", "s"),
    ("average_admission_wait_ms", "Admission wait", "ms"),
    ("average_delivered_epr_fidelity", "Delivered fidelity", ""),
    ("protocol_waste_percentage", "Protocol waste", "%"),
    ("compiler_waste_percentage", "Compiler waste", "%"),
    ("intended_request_hit_rate", "Compiler hit rate", "%"),
    ("on_demand_fallback_rate", "Fallback rate", "%"),
    ("compiler_not_ready_requests", "Not-ready requests", "count"),
    ("total_retries", "Retries", "count"),
)

def val(raw: str, name: str) -> float:
    if raw in (None, ""): return math.nan
    x = float(raw); return x / 1000 if name == "end_to_end_latency_ms" else x

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, required=True); ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(); manifest = json.load((a.root/"manifests/dynamic-variants_jobs.json").open()); groups=defaultdict(list); completed=0
    for job in manifest["jobs"]:
        out=a.root/job["output_path"]; summary=out/"summary.csv"
        if not summary.is_file(): continue
        completed += 1
        for row in csv.DictReader(summary.open(newline="",encoding="utf-8")):
            if float(row["completion_rate"]) != 1.0: continue
            key=(job["variant"],job["topology"],job["route_policy"]); groups[key].append(row)
    rows=[]
    for key, rawrows in sorted(groups.items()):
        variant,topology,route=key; out={"variant":variant,"topology":topology,"route_policy":route,"observations":len(rawrows)}
        for name,_,_ in METRICS:
            xs=[val(r.get(name,""),name) for r in rawrows]; xs=[x for x in xs if not math.isnan(x)]
            out[name+"_mean"]=fmean(xs) if xs else ""; out[name+"_sd"]=stdev(xs) if len(xs)>1 else 0.0
        rows.append(out)
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/"dynamic_variants_metrics.csv").open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]) if rows else ["variant","topology","route_policy"]); w.writeheader(); w.writerows(rows)
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    variants=sorted({r["variant"] for r in rows}); cells=sorted({(r["topology"],r["route_policy"]) for r in rows})
    colors=plt.get_cmap("tab20")(range(max(1,len(variants))))
    for name,label,unit in METRICS:
        fig,axes=plt.subplots(2,3,figsize=(16,9),constrained_layout=True)
        for ax,cell in zip(axes.flat,cells[:6]):
            subset=[r for r in rows if (r["topology"],r["route_policy"])==cell]
            for i,v in enumerate(variants):
                hit=[r for r in subset if r["variant"]==v]
                if not hit: continue
                r=hit[0]; y=float(r[name+"_mean"]); e=float(r[name+"_sd"]); ax.errorbar(i,y,yerr=e,fmt="o",color=colors[i],capsize=2)
            ax.set_title(" / ".join(cell)); ax.set_xticks(range(len(variants)),variants,rotation=75,ha="right"); ax.set_ylabel(f"{label} ({unit})" if unit else label); ax.grid(alpha=.25)
        for ax in axes.flat[len(cells[:6]):]: ax.axis("off")
        fig.suptitle(f"QFT-96 Dynamic policy variants: {label}"); fig.savefig(a.output/f"variants_{name}.png",dpi=160); fig.savefig(a.output/f"variants_{name}.pdf"); plt.close(fig)
    (a.output/"README.md").write_text(f"Validated variant jobs: {completed}/{len(manifest['jobs'])}. This is an incremental view and is regenerated as jobs complete.\n",encoding="utf-8")
    print(json.dumps({"completed_jobs":completed,"planned_jobs":len(manifest["jobs"]),"aggregate_rows":len(rows)},indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
