"""Full results table of the wall-clock study: every strategy, workload and route, with the metrics that matter.

Means over the evaluation seeds, with 95% Student-t intervals where a spread is shown.  Gain is computed per seed against
ODG on the same seed and then averaged.

Metric definitions (hop = one request from a core to its neighbour; chain = all hops one qubit makes inside one layer,
i.e. one source-to-destination move)
  latency      mean time per hop from eligibility to EPR delivery (ms); p95 is the 95th percentile of the same
  makespan     time to finish the whole workload (s), including the 5 ms charged per empty layer
  fidelity     mean fidelity of the delivered pairs (not a circuit success probability)
  ready        HIT coverage per hop: share of hops that found a pair already made (generation phase under 0.35 ms: only
               the 2-3 message reservation handshake of 0.2-0.3 ms is paid).  Measured from the timing records, so it is
               identical in definition for every strategy.  Its complement is the MISS share: no pair was there and the
               hop fell back to on-demand generation.
  chain full / partial / miss
               chain coverage: all hops of the chain ready / some ready / none ready.
  hits         Dynamic's own counter of compiler pairs consumed before the request started (cross-check of ready)
  fallback     Dynamic: share of hops the planner never prepared a pair for
  use %        pre-generation utilisation = pairs used / pairs generated (100 % = every pair that was made was consumed)
  waste %      100 - use %: pairs that expired or were left over, over pairs generated
  pairs/req    pairs generated per hop (the protocol counters count both endpoints, so they are halved here)
  adm.wait     mean wait for a free memory before the hop could start (ms); waited is the share of hops that waited
  storage      Dynamic: mean time a pair sat in memory between creation and use (ms)

    python tools/wallclock_study/report.py [--csv results/wallclock_2026-11-03/results.csv]
"""
from __future__ import annotations

import argparse
import sys
import csv
import math
from pathlib import Path
import statistics as st

from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUNS = ROOT / "output" / "wallclock_study" / "runs"
READY_BELOW_MS = 0.35

STRATEGIES = (               # label, folder, strategy name inside the folder
    ("ODG", "v0_layer", "on-demand"),
    ("CGP", "v3_cgp", "continuous"),
    ("ACGP", "v3_cgp", "adaptive-continuous"),
    ("Dyn-layer", "v0_layer", "dynamic"),
    ("Dyn-time", "v2_time", "dynamic"),
)
WORKLOADS = ("qft", "qpeexact", "qaoa", "draper_qft_adder")
ROUTES = ("xy", "history")


def number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def interval(values):
    values = [v for v in values if not math.isnan(v)]
    if len(values) < 2:
        return math.nan
    return float(stats.t.ppf(0.975, len(values) - 1) * st.stdev(values) / math.sqrt(len(values)))


def chains(workload, route):
    """request_id -> chain key (layer, qubit), from the frozen trace the runs used."""
    from ace.compiler.compiler_trace import parse_compiler_trace
    trace = parse_compiler_trace(ROOT / "results" / "wallclock_2026-11-03" / "traces" / workload / route / "requests.txt")
    return {r.request_id: (r.layer, r.qubit) for r in trace.requests}


def chain_coverage(ready_flags, key_of):
    """Share of chains that are fully / partly / not at all covered."""
    groups = {}
    for request_id, flag in ready_flags.items():
        groups.setdefault(key_of[request_id], []).append(flag)
    n = len(groups)
    full = sum(all(g) for g in groups.values())
    miss = sum(not any(g) for g in groups.values())
    return 100 * full / n, 100 * (n - full - miss) / n, 100 * miss / n


def load(folder, workload, route, strategy):
    base = RUNS / folder / f"{workload}_{route}_{strategy}"
    if not (base / "summary.csv").exists():
        return None
    rows = {int(r["seed"]): r for r in csv.DictReader((base / "summary.csv").open())}
    ready, coverage = {}, {}
    key_of = chains(workload, route)
    for seed in rows:
        timing = base / f"timing_{strategy}_{seed}.csv"
        if timing.exists():
            flags = {int(r["request_id"]): number(r["entanglement_generation_time_ms"]) < READY_BELOW_MS
                     for r in csv.DictReader(timing.open())}
            ready[seed] = sum(flags.values()) / len(flags)
            coverage[seed] = chain_coverage(flags, key_of)
    return rows, (ready, coverage)


def per_seed(rows, fn):
    return {seed: fn(row) for seed, row in rows.items()}


def mean(values):
    values = [v for v in values if not math.isnan(v)]
    return st.fmean(values) if values else math.nan


def metrics(rows, ready, strategy):
    n = {seed: number(r["requests"]) for seed, r in rows.items()}
    get = lambda key: per_seed(rows, lambda r: number(r.get(key)))
    out = {
        "latency_ms": get("request_latency_mean_ms"), "p95_ms": get("request_latency_p95_ms"),
        "makespan_s": per_seed(rows, lambda r: number(r["end_to_end_latency_ms"]) / 1000),
        "fidelity": get("average_delivered_epr_fidelity"),
        "ready_pct": {s: 100 * v for s, v in ready.items()},
        "adm_wait_ms": get("average_admission_wait_ms"),
        "waited_pct": per_seed(rows, lambda r: 100 * number(r["requests_that_waited_fraction"])),
        "retries": get("total_retries"),
    }
    if strategy == "dynamic":
        out["hits_pct"] = {s: 100 * number(rows[s]["pregenerated_hits"]) / n[s] for s in rows}
        out["fallback_pct"] = {s: 100 * number(rows[s]["on_demand_fallbacks"]) / n[s] for s in rows}
        out["waste_pct"] = get("compiler_waste_percentage")
        out["use_pct"] = {s: 100 - out["waste_pct"][s] for s in rows}
        out["storage_ms"] = get("average_storage_time_ms")
        out["pairs_per_req"] = {s: number(rows[s]["protocol_generated_pairs"]) / 2 / n[s] for s in rows}
        out["expired"] = get("expired_compiler_pairs")
    elif strategy in ("continuous", "adaptive-continuous"):
        out["waste_pct"] = get("protocol_waste_percentage")
        out["use_pct"] = {s: 100 - out["waste_pct"][s] for s in rows}
        out["pairs_per_req"] = {s: number(rows[s]["protocol_generated_pairs"]) / 2 / n[s] for s in rows}
    return out


def collect():
    table = {}
    for workload in WORKLOADS:
        for route in ROUTES:
            odg = load("v0_layer", workload, route, "on-demand")
            for label, folder, strategy in STRATEGIES:
                loaded = load(folder, workload, route, strategy)
                if loaded is None:
                    continue
                rows, (ready, coverage) = loaded
                m = metrics(rows, ready, strategy)
                for i, name in enumerate(("chain_full_pct", "chain_partial_pct", "chain_miss_pct")):
                    m[name] = {sd: c[i] for sd, c in coverage.items()}
                if odg:
                    base = {s: number(r["request_latency_mean_ms"]) for s, r in odg[0].items()}
                    m["gain_pct"] = {s: 100 * (1 - m["latency_ms"][s] / base[s]) for s in m["latency_ms"] if s in base}
                table[(workload, route, label)] = m
    return table


def cell(m, key, digits=2, with_ci=False):
    values = list((m.get(key) or {}).values())
    if not values or all(math.isnan(v) for v in values):
        return "-"
    text = f"{mean(values):.{digits}f}"
    return text + (f"±{interval(values):.{digits}f}" if with_ci else "")


def show(table):
    blocks = (
        ("LATENCY AND SPEED", (("lat ms", "latency_ms", 3, False), ("p95 ms", "p95_ms", 2, False), ("makesp s", "makespan_s", 2, False), ("gain %", "gain_pct", 1, True))),
        ("QUALITY", (("fidelity", "fidelity", 4, False), ("storage ms", "storage_ms", 2, False))),
        ("READINESS AND WASTE", (("ready %", "ready_pct", 1, False), ("hits %", "hits_pct", 1, False), ("fallbk %", "fallback_pct", 1, False),
                                  ("chain full", "chain_full_pct", 1, False), ("chn partial", "chain_partial_pct", 1, False), ("chain miss", "chain_miss_pct", 1, False))),
        ("PRE-GENERATION USE", (("use %", "use_pct", 1, False), ("waste %", "waste_pct", 2, False), ("pairs/req", "pairs_per_req", 2, False), ("expired", "expired", 0, False))),
        ("CONTENTION", (("adm.wait ms", "adm_wait_ms", 3, False), ("waited %", "waited_pct", 1, False), ("retries", "retries", 0, False))),
    )
    for title, columns in blocks:
        print(f"\n=== {title}")
        print(f"{'workload':17s} {'route':7s} {'strategy':9s} | " + " ".join(f"{name:>11s}" for name, *_ in columns))
        for workload in WORKLOADS:
            for route in ROUTES:
                for label, *_ in STRATEGIES:
                    m = table.get((workload, route, label))
                    if not m:
                        continue
                    print(f"{workload:17s} {route:7s} {label:9s} | " + " ".join(f"{cell(m, key, d, ci):>11s}" for _, key, d, ci in columns))


def write_csv(table, path):
    keys = ("latency_ms", "p95_ms", "makespan_s", "gain_pct", "fidelity", "storage_ms", "ready_pct", "hits_pct", "fallback_pct", "chain_full_pct", "chain_partial_pct", "chain_miss_pct", "use_pct",
            "waste_pct", "pairs_per_req", "expired", "adm_wait_ms", "waited_pct", "retries")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["workload", "route", "strategy", "seeds"] + [f"{k}{suffix}" for k in keys for suffix in ("", "_ci95")])
        for (workload, route, label), m in sorted(table.items()):
            row = [workload, route, label, len(m["latency_ms"])]
            for key in keys:
                values = list((m.get(key) or {}).values())
                row += [f"{mean(values):.6g}" if values else "", f"{interval(values):.6g}" if len(values) > 1 else ""]
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    table = collect()
    show(table)
    if args.csv:
        write_csv(table, args.csv)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
