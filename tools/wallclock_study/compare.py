"""Side-by-side table of study folders: latency, hit rate and makespan per strategy, workload and route."""
import csv, os, statistics as st, sys
RUNS = "output/wallclock_study/runs"
def load(folder, strategy, w, r):
    f = f"{RUNS}/{folder}/{w}_{r}_{strategy}/summary.csv"
    return list(csv.DictReader(open(f))) if os.path.exists(f) else None
def mean(rows, key): return st.mean(float(x[key]) for x in rows)
def main(columns, workloads, routes, baseline=("v0_layer", "on-demand")):
    head = f"{'workload':18s} {'route':8s} | {'ODG':>6s} |" + "".join(f" {name:>12s} {'hit%':>5s} {'gain%':>6s} {'mk s':>6s} |" for name, _, _ in columns)
    print(head)
    for w in workloads:
        for r in routes:
            odg = load(*baseline, w, r)
            if not odg: print(w, r, "no ODG"); continue
            line = f"{w:18s} {r:8s} | {mean(odg, 'request_latency_mean_ms'):6.3f} |"
            for name, folder, strategy in columns:
                rows = load(folder, strategy, w, r)
                if not rows: line += f" {'-':>12s} {'':5s} {'':6s} {'':6s} |"; continue
                n = float(rows[0]["requests"]); lat = mean(rows, "request_latency_mean_ms")
                hits = 100 * mean(rows, "pregenerated_hits") / n if rows[0].get("pregenerated_hits") not in (None, "") else float("nan")
                line += f" {lat:12.3f} {hits:5.1f} {100*(1-lat/mean(odg,'request_latency_mean_ms')):6.1f} {mean(rows,'end_to_end_latency_ms')/1000:6.2f} |"
            print(line)
if __name__ == "__main__":
    main([("layer-Dyn", "v0_layer", "dynamic"), ("time-Dyn", "v1_time", "dynamic")], ("qft", "draper_qft_adder"), ("xy", "history"))
