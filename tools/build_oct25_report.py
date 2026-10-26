#!/usr/bin/env python3
"""Rebuild the October 25 retrospective from Git-frozen evidence, without simulation.

Run from any directory with the project Python environment. All experimental
inputs are read from the parent of the FIRST golden-study commit, not HEAD.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, stdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr, ttest_ind

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/latex/oct25_pre_golden"
SNAPSHOT = "4aa334542e9b9c8fe7a5f9cc8fe48ee2e4d2fa55"
WEB = "https://github.com/sanjeevkrishnaa/Compiler-Driven-ACE"
ledger = {}
observations = []
checks = []


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def read(path):
    content = git("show", f"{SNAPSHOT}:{path}")
    ledger[path] = {"path": path, "sha256": hashlib.sha256(content).hexdigest(),
                    "git_blob": git("rev-parse", f"{SNAPSHOT}:{path}").decode().strip(),
                    "snapshot": SNAPSHOT, "source_url": f"{WEB}/blob/{SNAPSHOT}/{path}"}
    return content.decode()


def js(path):
    return json.loads(read(path))


def rows(path):
    return list(csv.DictReader(io.StringIO(read(path))))


def write_csv(name, data):
    assert data, name
    path = OUT / "data" / (name + ".csv")
    keys = list(dict.fromkeys(k for r in data for k in r))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)
    return path


def tex(s):
    return str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")


def link(path, label="Frozen source"):
    return r"\href{" + WEB + "/blob/" + SNAPSHOT + "/" + path + "}{" + tex(label) + "}"


def local_link(name):
    return r"\href{" + WEB + "/blob/codex/ace-scheduler-correctness/docs/latex/oct25_pre_golden/data/" + name + ".csv}{Complete CSV: " + tex(name) + "}"


def measure(rs, key):
    vals = [float(r[key]) for r in rs if r.get(key) not in (None, "") and math.isfinite(float(r[key]))]
    return (fmean(vals), stdev(vals) if len(vals) > 1 else 0.0) if vals else (None, None)


def pm(rs, key, scale=1, digits=3):
    mean, sd = measure(rs, key)
    return "--" if mean is None else f"${mean * scale:.{digits}f} \\pm {sd * scale:.{digits}f}$"


def check(name, condition, detail=""):
    checks.append({"check": name, "passed": bool(condition), "detail": detail})
    if not condition:
        raise ValueError(name + ": " + detail)


def load(path, family, label):
    rs = rows(path)
    md_path = str(Path(path).with_name("metadata.json"))
    md = js(md_path)
    combos = [(r["strategy"], int(r["seed"])) for r in rs]
    check("unique policy/seed: " + label, len(combos) == len(set(combos)))
    check("metadata seeds: " + label, set(combos) == {(s, seed) for s in md["strategies"] for seed in md["seeds"]})
    check("complete + metric v3: " + label,
          all(int(r["completed_requests"]) == int(r["requests"]) == md["trace_requests"] and
              float(r["completion_rate"]) == 1 and int(r["metric_version"]) == 3 for r in rs))
    for r in rs:
        observations.append({"family": family, "cell": label, "source_path": path,
                             "source_url": f"{WEB}/blob/{SNAPSHOT}/{path}", **r})
    return rs, md


def table(headers, body, caption, csvname, sources=()):
    result = [r"\begin{center}\small", r"\begin{longtable}{" + "l" + "r" * (len(headers)-1) + "}",
              r"\caption{" + caption + r"}\\", r"\toprule", " & ".join(headers) + r" \\", r"\midrule\endfirsthead",
              r"\toprule", " & ".join(headers) + r" \\", r"\midrule\endhead"]
    result += [" & ".join(str(v) for v in row) + r" \\" for row in body]
    result += [r"\bottomrule\end{longtable}\end{center}", r"{\footnotesize " + local_link(csvname) + ". " + "; ".join(sources) + "}\n"]
    return "\n".join(result)


def fig(name, caption, height="0.37"):
    return r"\begin{center}\includegraphics[width=\linewidth,height=" + height + r"\textheight,keepaspectratio]{figures/" + name + r".pdf}\captionof{figure}{" + caption + "}\\end{center}\n"


def savefig(name):
    plt.savefig(OUT / "figures" / (name + ".pdf"), bbox_inches="tight")
    plt.savefig(OUT / "figures" / (name + ".png"), dpi=180, bbox_inches="tight")
    plt.close()


def summary_record(label, rs, **extra):
    record = {"label": label, "n": len(rs), **extra}
    for key in METRICS:
        record[key + "_mean"], record[key + "_sd"] = measure(rs, key)
    return record


METRICS = ["request_latency_mean_ms", "request_latency_p95_ms", "average_admission_wait_ms",
           "avg_entanglement_generation_time_ms", "end_to_end_latency_ms", "pregenerated_success_rate",
           "intended_request_hit_rate", "on_demand_fallback_rate", "compiler_waste_percentage",
           "compiler_expiry_percentage", "average_delivered_epr_fidelity", "average_fidelity_at_utilization",
           "average_storage_time_ms"]
ROUTES = ["original", "xy", "yx", "shortest_reliable", "max_reliability"]
NAMES = {"original": "Supplied", "xy": "XY", "yx": "YX", "shortest_reliable": "Shortest reliable", "max_reliability": "Max reliability"}
POLICIES = ["ODG", "Full-chain", "First-hop", "Adaptive-25"]
WORKLOADS = ["ghz", "bv", "bmw_quark_cardinality", "vqe_real_amp", "cdkm_ripple_carry_adder", "graphstate", "draper_qft_adder", "qft", "qaoa", "randomcircuit"]
SHORT = {"bmw_quark_cardinality": "BMW", "cdkm_ripple_carry_adder": "CDKM", "draper_qft_adder": "Draper", "vqe_real_amp": "VQE", "randomcircuit": "Random", "graphstate": "Graph", "ghz": "GHZ", "bv": "BV", "qft": "QFT", "qaoa": "QAOA"}


def build():
    for d in [OUT / "data", OUT / "figures", OUT / "generated"]:
        d.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.2, "pdf.fonttype": 42})
    paths = git("ls-tree", "-r", "--name-only", SNAPSHOT, "results").decode().splitlines()
    routing = {}
    for route in ROUTES:
        rs, md = load(f"results/routing_study_2026-10-25/runs/{route}/summary.csv", "routing", route)
        for policy, strategy in [("ODG", "on-demand"), ("Full-chain", "dynamic")]:
            routing[route, policy] = [r for r in rs if r["strategy"] == strategy]
        check("routing seeds 0-29: " + route, md["seeds"] == list(range(30)))
    reference, _ = load("results/qft96_physical_per_qubit_30seed_2026-10-25/summary.csv", "reference", "historical-control")
    for strategy, policy in [("on-demand", "ODG"), ("dynamic", "Full-chain")]:
        ref = {r["seed"]: r for r in reference if r["strategy"] == strategy}
        check("control exact reproduction: " + strategy,
              all(r["request_latency_mean_ms"] == ref[r["seed"]]["request_latency_mean_ms"] and
                  r["end_to_end_latency_ms"] == ref[r["seed"]]["end_to_end_latency_ms"] for r in routing["original", policy]))
    routing_csv = [summary_record(route, rs, route=route, policy=policy) for (route, policy), rs in routing.items()]
    write_csv("routing", routing_csv)
    text = []
    for metric, title, scale in [("request_latency_mean_ms", "Mean request latency (ms)", 1), ("end_to_end_latency_ms", "Communication makespan (s)", .001), ("average_admission_wait_ms", "Admission wait (ms)", 1)]:
        name = "routing_" + metric
        x = np.arange(len(ROUTES)); plt.figure(figsize=(8.2, 3.5))
        for j, policy in enumerate(["ODG", "Full-chain"]):
            ms = [measure(routing[r, policy], metric) for r in ROUTES]
            plt.bar(x + (j-.5)*.35, [m*scale for m,s in ms], .35, yerr=[s*scale for m,s in ms], capsize=3, label=policy)
        plt.xticks(x, ["Supplied", "XY", "YX", "Shortest\nreliable*", "Maximum\nreliability*"])
        plt.ylabel(title); plt.legend(ncol=2); plt.tight_layout(); savefig(name)
        text += [r"\clearpage", fig(name, title + ". Error bars are sample SD across 30 physics seeds; starred routes use a reconstructed reliability map."),
                 table(["Route", "ODG", "Full-chain"], [[tex(NAMES[r]), pm(routing[r,"ODG"],metric,scale),pm(routing[r,"Full-chain"],metric,scale)] for r in ROUTES], title + "; 30 seeds per cell.", "routing")]
    (OUT / "generated/routing.tex").write_text("\n".join(text))

    # Every launch-rule screen, including negative results.
    variants = {}
    variant_paths = sorted(p for p in paths if p.startswith("results/dynamic_design_2026-10-25/") and p.endswith("/summary.csv"))
    for p in variant_paths:
        route, variant = p.split("/")[2:4]
        rs, md = load(p, "launch-screen", route+"/"+variant)
        check("screen ten seeds: " + variant, md["seeds"] == list(range(10)))
        variants[route,variant] = rs
    write_csv("launch_screen", [summary_record(v, rs, route=r) for (r,v),rs in variants.items()])
    text = []
    for route in ["original", "xy"]:
        subset = [(v,rs) for (r,v),rs in variants.items() if r==route]
        subset.sort(key=lambda item: measure(item[1], "request_latency_mean_ms")[0])
        plt.figure(figsize=(9,5.3)); y=np.arange(len(subset))
        plt.barh(y, [measure(rs,"request_latency_mean_ms")[0] for _,rs in subset], xerr=[measure(rs,"request_latency_mean_ms")[1] for _,rs in subset], capsize=2)
        plt.yticks(y,[v.replace("_", " ") for v,_ in subset],fontsize=8)
        plt.axvline(measure(routing[route,"ODG"],"request_latency_mean_ms")[0],color="darkred",linestyle="--",label="30-seed ODG reference")
        plt.xlabel("Mean request latency (ms); 10-seed screen");plt.legend();plt.tight_layout();savefig("launch_"+route)
        text += [r"\clearpage\subsection{"+NAMES[route]+" route}",fig("launch_"+route,"Every launch-policy screen, including unsuccessful delays and predecessor triggers.","0.44"),
                 table(["Variant", "Latency ms", "p95 ms", "Makespan s"],[[tex(v.replace("_"," ")),pm(rs,"request_latency_mean_ms"),pm(rs,"request_latency_p95_ms"),pm(rs,"end_to_end_latency_ms",.001)] for v,rs in subset], "Timing results; mean $\\pm$ SD, 10 seeds.", "launch_screen"),
                 r"\clearpage", table(["Variant", "Ready frac.", "Waste "+r"\%", "Delivered F"],[[tex(v.replace("_"," ")),pm(rs,"pregenerated_success_rate"),pm(rs,"compiler_waste_percentage"),pm(rs,"average_delivered_epr_fidelity",digits=4)] for v,rs in subset], "Readiness, compiler waste and delivered fidelity for the same screen.", "launch_screen")]
    (OUT / "generated/launch.tex").write_text("\n".join(text))

    # Static mechanism and controlled shortest-path interventions.
    static = js("results/why_xy_2026-10-25/static_load_qft96.json")
    static.update(js("results/why_xy_2026-10-25/static_load_all.json"))
    for p in paths:
        if p.startswith("results/why_xy_2026-10-25/runs/") and p.endswith("/summary.csv"):
            arm=p.split("/")[3];rs,md=load(p,"route-intervention",arm)
            for policy,strategy in [("ODG","on-demand"),("Full-chain","dynamic")]:
                routing[arm,policy]=[r for r in rs if r["strategy"]==strategy]
    arms = [r for r in static if (r,"ODG") in routing]
    check("five routes + sixteen interventions", len(arms)==21, str(len(arms)))
    # Independent plain-text parser and mesh geometry, not the mapper adapter.
    def parse_hops(path):
        initial, chains, headers = {}, defaultdict(list), []
        layer = None
        for line in read(path).splitlines():
            line = line.strip()
            if line.startswith("// Layer"):
                layer = int(line.split()[-1]); headers.append(layer)
            elif line.startswith("("):
                values = tuple(int(x) for x in line.strip("()").split(","))
                if len(values) == 2 and layer is None:
                    initial[values[0]] = values[1]
                elif len(values) == 3:
                    chains[layer, values[0]].append(values[1:])
        routes = {}
        for key, hops in chains.items():
            route = [hops[0][0]]
            for source, target in hops:
                if source != route[-1] or not (0 <= source < 16 and 0 <= target < 16) or abs(source//4-target//4)+abs(source%4-target%4) != 1:
                    raise ValueError(f"Invalid frozen hop chain {path}: {key}")
                route.append(target)
            routes[key] = route
        # A placement transition must depart from the qubit's current core.
        placement = dict(initial)
        for (layer, qubit), route in sorted(routes.items()):
            if placement[qubit] != route[0]:
                raise ValueError(f"Invalid placement replay {path}: {layer}, {qubit}")
            placement[qubit] = route[-1]
        return initial, headers, routes

    base_path = "results/qft96_corrected_scheduler_2026-10-25/qft96_requests.txt"
    initial0, headers0, paths0 = parse_hops(base_path)
    endpoints0 = {k:(p[0],p[-1]) for k,p in paths0.items()}
    check("frozen QFT-96 trace dimensions", len(initial0)==96 and len(headers0)==766 and len(paths0)==1770)
    for arm in arms:
        path = base_path if arm=="original" else (f"results/routing_study_2026-10-25/qft96/{arm}/requests.txt" if arm in ROUTES else f"results/why_xy_2026-10-25/interventions/{arm}/requests.txt")
        initial, headers, route_paths = parse_hops(path)
        check("same placement endpoints/layers: "+arm, initial==initial0 and headers==headers0 and {k:(p[0],p[-1]) for k,p in route_paths.items()}==endpoints0)
        check("hop count: "+arm, sum(len(p)-1 for p in route_paths.values()) == (5070 if arm=="max_reliability" else 4954))
        demand=Counter()
        for (layer,qubit),route in route_paths.items():
            for index,core in enumerate(route): demand[layer,core] += 1 if index in (0,len(route)-1) else 2
        for capacity in (2,3,4,6,8):
            check(f"independent excess M={capacity}: {arm}",sum(max(0,d-capacity) for d in demand.values())==static[arm][f"excess_C{capacity}"])
    mechanism = [{"arm":a,"excess_C4":static[a]["excess_C4"],"peak_demand":static[a]["peak_layer_core_demand"],"overloaded_core_layers_C4":static[a]["overloaded_core_layers_C4"],"relay_gini":static[a]["gini_relay_load"],
                  "odg_latency_ms":measure(routing[a,"ODG"],"request_latency_mean_ms")[0],"dynamic_latency_ms":measure(routing[a,"Full-chain"],"request_latency_mean_ms")[0],
                  "dynamic_wait_ms":measure(routing[a,"Full-chain"],"average_admission_wait_ms")[0],"latency_ratio":measure(routing[a,"Full-chain"],"request_latency_mean_ms")[0]/measure(routing[a,"ODG"],"request_latency_mean_ms")[0]} for a in arms]
    write_csv("routing_mechanism",mechanism)
    rho,rho_p=spearmanr([r["excess_C4"] for r in mechanism],[r["dynamic_wait_ms"] for r in mechanism])
    plt.figure(figsize=(8,4.1))
    offsets={"original":(-80,-10),"shortest_reliable":(-95,-25),"max_reliability":(-15,-30),"concentrate":(-50,8),"xy":(-10,8),"yx":(-16,8),"balance":(7,9),"avoid_hot2":(8,-3)}
    for r in mechanism:
        plt.scatter(r["excess_C4"],r["dynamic_wait_ms"],s=35)
        if r["arm"] in ROUTES+["balance","concentrate","avoid_hot2"]:
            plt.annotate(r["arm"].replace("_"," "),(r["excess_C4"],r["dynamic_wait_ms"]),fontsize=7,xytext=offsets[r["arm"]],textcoords="offset points",arrowprops={"arrowstyle":"-","lw":.5,"color":"gray"})
    plt.xlabel("Static excess demand at capacity 4 (hop touches)");plt.ylabel("Dynamic mean admission wait (ms)")
    plt.title(f"21 controlled arms: Spearman rho = {rho:.3f}");plt.tight_layout();savefig("mechanism")
    text=[fig("mechanism","Static layer demand predicts simulated waiting. Arms are controlled route alternatives sharing endpoints, not 21 independent workload samples."),table(["Arm","Excess", "ODG ms","Dynamic ms","Wait ms"],[[tex(r["arm"]),r["excess_C4"],f'{r["odg_latency_ms"]:.4f}',f'{r["dynamic_latency_ms"]:.4f}',f'{r["dynamic_wait_ms"]:.4f}'] for r in mechanism],"All 21 route alternatives, 30 seeds per policy. Values here are seed means; all SD values are in the unified data CSV.","routing_mechanism")]
    (OUT / "generated/mechanism.tex").write_text("\n".join(text))
    # Per-core waits: do not use the known mislabeled occupancy files.
    percore=[]
    fig1, axs=plt.subplots(1,3,figsize=(10,3.3),sharey=True)
    for ax,route in zip(axs,["original","xy","yx"]):
        obj=js(f"results/why_xy_2026-10-25/per_core/{route}_dynamic.json")
        relay=np.mean([r["relay_wait_ms"] for r in obj["per_seed"]],axis=0)
        endpoint=np.mean([r["endpoint_wait_ms"] for r in obj["per_seed"]],axis=0)
        ax.bar(range(16),endpoint,label="Source/destination");ax.bar(range(16),relay,bottom=endpoint,label="Relay touches")
        ax.set_title(NAMES[route]);ax.set_xlabel("Core");ax.set_xticks([0,5,9,15])
        for c in range(16):percore.append({"route":route,"core":c,"physics_seeds":len(obj["per_seed"]),"endpoint_touch_wait_ms":endpoint[c],"relay_touch_wait_ms":relay[c]})
    axs[0].set_ylabel("Summed touch-attributed wait (ms)");axs[0].legend(fontsize=7);fig1.tight_layout();savefig("percore")
    write_csv("per_core_wait",percore)
    text=[fig("percore","Dynamic waiting attributed to endpoint and relay touches, averaged over five physics seeds. A hop touches two cores, so these sums are not wall-clock latency and can count one request twice."),table(["Core","Supplied end/relay","XY end/relay","YX end/relay"],[[c]+[f'{next(r for r in percore if r["route"]==a and r["core"]==c)["endpoint_touch_wait_ms"]:.1f} / {next(r for r in percore if r["route"]==a and r["core"]==c)["relay_touch_wait_ms"]:.1f}' for a in ["original","xy","yx"]] for c in range(16)],"Complete core-wise values underlying the figure, in ms.","per_core_wait")]
    (OUT / "generated/percore.tex").write_text("\n".join(text))

    # Confirmation: same-route ODG is the baseline for each redesigned policy.
    confirmed={}
    for route in ["original","xy","yx"]:
        for policy in ["ODG","Full-chain"]:confirmed[route,policy]=routing[route,policy]
        for policy,path in [("First-hop",f"results/overnight_2026-10-25/P1_confirm/{route}/summary.csv"),("Adaptive-25",f"results/congestion_adaptive_confirm_2026-10-25/{route}/summary.csv")]:
            rs,md=load(path,"confirmation",route+"/"+policy);confirmed[route,policy]=rs
            check("confirmation thirty seeds: "+route+policy,md["seeds"]==list(range(30)))
    write_csv("confirmation",[summary_record(route,rs,route=route,policy=policy) for (route,policy),rs in confirmed.items()])
    text=[]
    for metric,label,scale in [("request_latency_mean_ms","Mean request latency (ms)",1),("request_latency_p95_ms","Per-run p95 request latency (ms)",1),("end_to_end_latency_ms","Communication makespan (s)",.001),("average_admission_wait_ms","Admission wait (ms)",1),("pregenerated_success_rate","Readiness fraction",1),("compiler_waste_percentage","Compiler EPR waste (percent)",1),("average_delivered_epr_fidelity","Delivered EPR fidelity",1),("average_storage_time_ms","Used compiler-pair storage (ms)",1)]:
        x=np.arange(3);plt.figure(figsize=(8.2,3.4))
        for j,policy in enumerate(POLICIES):
            if policy == "ODG" and metric == "compiler_waste_percentage":
                continue  # No compiler-generated denominator under ODG.
            vals=[measure(confirmed[r,policy],metric) for r in ["original","xy","yx"]]
            if all(m is None for m,s in vals):continue
            means=[np.nan if m is None else m*scale for m,s in vals]
            errors=[0 if s is None else s*scale for m,s in vals]
            color=plt.get_cmap("tab10")(j)
            if metric == "average_delivered_epr_fidelity":
                plt.errorbar(x+(j-1.5)*.19,means,yerr=errors,fmt="o",capsize=3,label=policy,color=color)
            else:
                plt.bar(x+(j-1.5)*.19,means,.19,yerr=errors,capsize=2,label=policy,color=color)
        plt.xticks(x,["Supplied","XY","YX"]);plt.ylabel(label);plt.legend(ncol=4,fontsize=8);plt.tight_layout();name="confirmation_"+metric;savefig(name)
        body=[]
        for r in ["original","xy","yx"]:
            body.append([NAMES[r]]+["n/a" if p=="ODG" and metric in ["compiler_waste_percentage","average_storage_time_ms"] else pm(confirmed[r,p],metric,scale,4 if "fidelity" in metric else 3) for p in POLICIES])
        note = " ODG has no compiler cache; its zero compiler-waste counter is not an efficiency ratio." if metric=="compiler_waste_percentage" else ""
        text += [r"\clearpage\subsection{"+tex(label)+"}",fig(name,label+" for the 30-seed confirmation. Error bars show sample SD."),table(["Route"]+POLICIES,body,label+"; mean $\\pm$ SD."+note,"confirmation")]
    (OUT / "generated/confirmation.tex").write_text("\n".join(text))
    # Threshold selection and memory/allocation screen.
    sweep=[]
    for p in paths:
        if p.startswith("results/congestion_threshold_sweep_2026-10-25/") and p.endswith("/summary.csv"):
            n=int(p.split("/")[2][1:]);rs,md=load(p,"threshold-screen",str(n));sweep.append((n,rs))
    sweep.sort();write_csv("threshold",[summary_record(n,rs,threshold=n) for n,rs in sweep])
    fig1,axs=plt.subplots(1,2,figsize=(9,3.5))
    for ax,key,scale,label in [(axs[0],"request_latency_mean_ms",1,"Latency (ms)"),(axs[1],"end_to_end_latency_ms",.001,"Makespan (s)")]:
        ms=[measure(rs,key) for _,rs in sweep];ax.errorbar(range(len(sweep)),[m*scale for m,s in ms],yerr=[s*scale for m,s in ms],marker="o",capsize=2)
        ax.set_xticks(range(len(sweep)),["full" if n==999999 else str(n) for n,_ in sweep],fontsize=8);ax.set_xlabel("Activity threshold (categorical spacing)");ax.set_ylabel(label)
    fig1.tight_layout();savefig("threshold")
    text=[fig("threshold","Ten-seed threshold screen on XY. Zero is first-hop-only; the large sentinel is full-chain. The threshold was selected on this same workload."),table(["Threshold","Latency ms","p95 ms","Makespan s"],[["Full" if n==999999 else n,pm(rs,"request_latency_mean_ms"),pm(rs,"request_latency_p95_ms"),pm(rs,"end_to_end_latency_ms",.001)] for n,rs in sweep],"Complete threshold screen, 10 seeds per point.","threshold")]
    (OUT / "generated/threshold.tex").write_text("\n".join(text))
    grid=[]
    for p in paths:
        if p.startswith("results/overnight_2026-10-25/P2_grid/") and p.endswith("/summary.csv"):
            label=p.split("/")[3];rs,md=load(p,"parameter-screen",label);grid.append((label,rs,md))
    write_csv("parameter_grid",[summary_record(label,rs,total_memories=md["parameters"]["total_memories"],compiler_memories=md["parameters"]["compiler_memories"],admission=md["parameters"]["admission"]) for label,rs,md in grid])
    text=[table(["Point","M/C","Latency ms","Wait ms","Makespan s"],[[tex(label.replace("P2_","")),f'{md["parameters"]["total_memories"]}/{md["parameters"]["compiler_memories"]}',pm(rs,"request_latency_mean_ms"),"n/a" if md["parameters"]["admission"]=="poll" else pm(rs,"average_admission_wait_ms"),pm(rs,"end_to_end_latency_ms",.001)] for label,rs,md in grid],"All 11 XY first-hop parameter screens, 10 seeds per point. Polling wait is not comparable.","parameter_grid")]
    (OUT / "generated/grid.tex").write_text("\n".join(text))
    # Full ten-workload generalisation: do not relabel the 48-qubit QFT as QFT-96.
    general={}
    for w in WORKLOADS:
        for route in ["original","xy"]:
            for policy,suffix in [("ODG","on-demand"),("Full-chain","dynamic"),("First-hop","dynamic-first-hop")]:
                rs,md=load(f"results/overnight_2026-10-25/P3_generalisation/{w}/{route}_{suffix}/summary.csv","generalisation",w+"/"+route+"/"+policy)
                check("generalisation three seeds: "+w+route+policy,md["seeds"]==[0,1,2]);general[w,route,policy]=rs
        for threshold in [25,30]:
            rs,md=load(f"results/congestion_adaptive_generalisation_2026-10-25/{w}_t{threshold}/summary.csv","generalisation-adaptive",w+"/"+str(threshold));general[w,"xy","Adaptive-"+str(threshold)]=rs
    write_csv("generalisation",[summary_record(w,rs,workload=w,route=r,policy=p) for (w,r,p),rs in general.items()])
    text=[]
    for route in ["original","xy"]:
        policies=POLICIES[:3]+(["Adaptive-25","Adaptive-30"] if route=="xy" else [])
        plt.figure(figsize=(9,3.9));x=np.arange(10)
        for p in policies[1:]:
            plt.plot(x,[measure(general[w,route,p],"request_latency_mean_ms")[0]/measure(general[w,route,"ODG"],"request_latency_mean_ms")[0] for w in WORKLOADS],"o-",label=p)
        plt.axhline(1,color="black",ls="--",label="ODG");plt.xticks(x,[SHORT[w] for w in WORKLOADS],rotation=25);plt.ylabel("Ratio of mean latencies to same-route ODG");plt.legend(ncol=3,fontsize=8);plt.tight_layout();savefig("generalisation_"+route)
        text += [r"\section{"+NAMES[route]+" routing: ten 48-qubit workloads}",fig("generalisation_"+route,"Ratios of seed means, three physics seeds per policy. Workload categories have no continuous order. Ratios have no confidence intervals here."),table(["Workload"]+[tex(p) for p in policies[1:]],[[SHORT[w]]+[f'{measure(general[w,route,p],"request_latency_mean_ms")[0]/measure(general[w,route,"ODG"],"request_latency_mean_ms")[0]:.4f}' for p in policies[1:]] for w in WORKLOADS],"Exact latency ratios plotted above; values below one favour the listed Dynamic policy.","generalisation")]
        for metric,label,scale in [("request_latency_mean_ms","Latency (ms)",1),("end_to_end_latency_ms","Makespan (s)",.001),("average_delivered_epr_fidelity","Delivered fidelity",1),("pregenerated_success_rate","Readiness fraction",1),("compiler_waste_percentage","Compiler waste (percent)",1)]:
            text.append(table(["Workload"]+policies,[[SHORT[w]]+["n/a" if p=="ODG" and "waste" in metric else pm(general[w,route,p],metric,scale,4 if "fidelity" in metric else 3) for p in policies] for w in WORKLOADS],label+", mean $\\pm$ SD across three seeds.","generalisation"))
    (OUT / "generated/generalisation.tex").write_text("\n".join(text))
    # HQA/T-HQA was a separate mapper comparison, not the placement in the route screen.
    mapper=[]
    for prefix in ["", "seed_43/", "seed_44/"]:
        p="results/hqa-vs-thqa-qft96-2026-10-25/"+prefix+"qft96.csv"
        seed=42 if not prefix else int(prefix[5:7])
        mapper.extend({"reliability_seed":seed,**r} for r in rows(p))
    write_csv("mapper",mapper)
    text=[table(["Seed","Placer","Migrations","Hops","Mapper cost","Residual"],[[r["reliability_seed"],r["placer"],r["migrations"],int(float(r["hops"])),f'{float(r["cost"]):.2f}',r["residual_operations"]] for r in mapper],"Mapper-only HQA/T-HQA comparison. Reliability seeds are not independent placement samples.","mapper")]
    (OUT / "generated/mapper.tex").write_text("\n".join(text))
    # Raw observations and complete metric aggregates form a reusable, auditable evidence pack.
    write_csv("per_seed_results",observations)
    all_aggregate=[]
    groups=defaultdict(list)
    for r in observations:groups[r["family"],r["cell"],r["strategy"]].append(r)
    for (family,cell,strategy),rs in groups.items():
        all_aggregate.append(summary_record(cell,rs,family=family,cell=cell,strategy=strategy,source_path=rs[0]["source_path"],source_url=rs[0]["source_url"]))
    write_csv("all_metrics",all_aggregate)
    for p in ["docs/reports/qft96-timing-model-matrix-2026-10-25.md","docs/reports/mqt-congestion-study.md","docs/worklog/README.md","docs/plans/why-xy-wins-test-design.md","compiler_scheduler.py","compiler_trace.py","parallel_core.py","request_scheduler.py","run_trace_comparison.py","mapper/qmap/metrics/distance.py","tools/mapper_ace/route_load.py","tools/mapper_ace/route_interventions.py"]:
        read(p)
    history=git("log","--reverse","--format=%H%x09%s","1cc7eb6.."+SNAPSHOT).decode().splitlines()
    histrows=[{"commit":line.split("\t",1)[0],"subject":line.split("\t",1)[1]} for line in history]
    write_csv("commits",histrows)
    lines=[r"\begin{longtable}{p{.15\linewidth}p{.77\linewidth}}\toprule Commit & Recorded change\\\midrule\endhead"]
    for r in histrows:lines.append(r"\href{"+WEB+"/commit/"+r["commit"]+"}{"+r["commit"][:7]+"} & "+tex(r["subject"])+r" \\")
    lines += [r"\bottomrule\end{longtable}"]
    (OUT/"generated/commits.tex").write_text("\n".join(lines))
    write_csv("source_ledger",list(ledger.values()))
    # Tests are recomputed on stored observations; no claim of rerunning ACE.
    comparisons=[]
    for route in ["original","xy","yx"]:
        for p in ["Full-chain","First-hop","Adaptive-25"]:
            a=np.array([float(r["request_latency_mean_ms"]) for r in confirmed[route,p]])
            b=np.array([float(r["request_latency_mean_ms"]) for r in confirmed[route,"ODG"]])
            test=ttest_ind(a,b,equal_var=False)
            comparisons.append({"route":route,"policy":p,"latency_difference_ms":a.mean()-b.mean(),"welch_p_exploratory_unadjusted":test.pvalue,"latency_ratio":a.mean()/b.mean(),"makespan_ratio":measure(confirmed[route,p],"end_to_end_latency_ms")[0]/measure(confirmed[route,"ODG"],"end_to_end_latency_ms")[0]})
    write_csv("confirmation_comparisons",comparisons)
    audit={"snapshot":SNAPSHOT,"first_excluded_commit":"44fa139","source_files":len(ledger),"summary_files":sum(p.endswith("summary.csv") for p in ledger),"per_seed_rows":len(observations),"aggregate_cells":len(groups),"validation_checks":len(checks),"all_passed":all(r["passed"] for r in checks),"spearman_excess_dynamic_wait":{"rho":float(rho),"p_exploratory":float(rho_p)},"checks":checks}
    (OUT/"data/validation.json").write_text(json.dumps(audit,indent=2)+"\n")
    counts=defaultdict(lambda:[0,0])
    for (family,cell,strategy),rs in groups.items():counts[family][0]+=1;counts[family][1]+=len(rs)
    (OUT/"generated/inventory.tex").write_text(table(["Family","Policy cells","Seed rows"],[[tex(k),v[0],v[1]] for k,v in counts.items()],"Evidence inventory. The reference family deliberately duplicates the supplied-route control for regression validation.","all_metrics"))
    print(json.dumps({k:v for k,v in audit.items() if k!="checks"},indent=2))


if __name__ == "__main__":
    build()
