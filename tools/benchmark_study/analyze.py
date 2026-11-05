"""Build the Excel workbook and the per-hop generation tables of the benchmark study (2026-11-04).

    <venv with pandas+openpyxl>/bin/python tools/benchmark_study/analyze.py

Reads output/benchmark_study/runs/*, writes to results/benchmark_study_2026-11-04/:
  benchmark_study.xlsx       README, Summary (mean of seeds), PerSeed, one pivot per metric, Lead_active, Lead_logical, Checks
  per_seed.csv, summary.csv  the same numbers as CSV
  per_hop/<benchmark>_<route>_K<k>_seed<s>.csv   every hop of every Dynamic run: the layer its pair was generated in,
                             how many layers before its own layer that was (active and logical), and what happened

Metric definitions (hop = one request between neighbouring cores; chain = all hops of one qubit in one layer)
  latency        mean time per hop from eligibility to EPR delivery (ms); p95 likewise; makespan = whole workload (s)
  gain           100 (1 - latency / ODG latency), same benchmark, route, K and seed, then averaged over seeds
  fidelity       mean fidelity of delivered pairs
  hop coverage   share of hops that found a pair already made: generation phase under 0.35 ms (handshake only).
                 Same definition for every strategy.  Its complement is the on-demand share.
  chain full / partial / miss   all / some / none of a chain's hops ready
  utilisation    pairs used / pairs generated (Dynamic: pair records; CGP/ACGP: the protocol's generated and used
                 counters; its "unused" counter is not used, because it also counts reservations that never held a pair)
  wastage        100 - utilisation: pairs generated but never used (expired, or left in a cache at the end)
  pairs per hop  pairs generated per hop (CGP/ACGP protocol counters count both endpoints, so they are halved)
  lead (Dynamic) target layer L minus the layer the pair was launched in: "L-2" means two layers before.  Active lead
                 counts only layers with requests (what the planner uses); logical lead counts every trace layer.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ace.compiler.compiler_trace import parse_compiler_trace  # noqa: E402
from run_matrix import BENCHMARKS, EXTRA_K, INFINITE, K_VALUES, ROUTES, RUNS, STRATEGIES, TRACES, memories  # noqa: E402

OUT = ROOT / "results" / "benchmark_study_2026-11-04"
READY_BELOW_MS = 0.35
LABEL = {"on-demand": "ODG", "continuous": "CGP", "adaptive-continuous": "ACGP", "dynamic": "Dynamic"}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


class TraceInfo:
    def __init__(self, benchmark, route):
        trace = parse_compiler_trace(TRACES / benchmark / route / "requests.txt")
        self.requests = {r.request_id: r for r in trace.requests}
        self.active = sorted({r.layer for r in trace.requests})
        self.chain = {r.request_id: (r.layer, r.qubit) for r in trace.requests}
        self.position, self.length = {}, {}
        for r in sorted(trace.requests, key=lambda r: (r.layer, r.qubit, r.order)):
            key = (r.layer, r.qubit)
            self.position[r.request_id] = self.length.get(key, 0)      # 0 for the first hop of the chain
            self.length[key] = self.length.get(key, 0) + 1

    def active_index(self, layer):
        """Index of the last active layer at or before ``layer``."""
        return bisect.bisect_right(self.active, layer) - 1


def chain_shares(ready, info):
    groups = {}
    for rid, flag in ready.items():
        groups.setdefault(info.chain[rid], []).append(flag)
    n = len(groups)
    full = sum(all(g) for g in groups.values())
    miss = sum(not any(g) for g in groups.values())
    return 100 * full / n, 100 * (n - full - miss) / n, 100 * miss / n


def lead_table(benchmark, route, k, seed, info, folder, timing):
    """One row per hop of a Dynamic run."""
    records = list(csv.DictReader((folder / f"pairs_dynamic_{seed}.csv").open()))
    by_target = {}
    for rec in records:
        by_target.setdefault(int(rec["target_request_id"]), []).append(rec)
    rows = []
    for rid, req in sorted(info.requests.items()):
        pairs = by_target.get(rid, [])
        used = [p for p in pairs if p["status"] == "used" and p["actual_request_id"] not in ("", None)
                and int(float(p["actual_request_id"])) == rid]
        pick = used[0] if used else (pairs[-1] if pairs else None)
        if pick is None:
            outcome, g = "on demand (no pair generated)", None
        elif used and pick["prepared_before_request"] == "True":
            outcome, g = "ready (pre-generated)", int(pick["generation_layer"])
        elif used:
            outcome, g = "late pair (generated after the hop started)", int(pick["generation_layer"])
        else:
            outcome, g = f"pair {pick['status']}, hop ran on demand", int(pick["generation_layer"])
        t = timing.get(rid, {})
        rows.append(dict(
            benchmark=benchmark, route=route, K=k, seed=seed, request_id=rid, target_layer=req.layer, qubit=req.qubit,
            hop_in_chain=info.position[rid] + 1, chain_hops=info.length[info.chain[rid]], source_core=req.source_core,
            destination_core=req.destination_core, generation_layer=g,
            lead_active=None if g is None else info.active_index(req.layer) - info.active_index(g),
            lead_logical=None if g is None else req.layer - g, outcome=outcome,
            pair_generated_at_ms=None if pick is None else num(pick["generated_at_ps"]) / 1e9,
            hop_start_ms=None if pick is None or pick.get("target_request_start_ps") in ("", None)
            else num(pick["target_request_start_ps"]) / 1e9,
            fidelity_at_use=None if not used else num(pick["fidelity_at_utilization"]),
            hop_latency_ms=num(t.get("total_time_ms")), generation_phase_ms=num(t.get("entanglement_generation_time_ms"))))
    return rows


def peak_booked(folder, strategy, seed):
    path = folder / f"capacity_{strategy}_{seed}.json"
    if not path.exists():
        return math.nan
    data = json.loads(path.read_text())
    return max(data.get("peak_booked_slots_per_node", {}).values(), default=math.nan)


def main() -> None:
    per_seed, hops, missing, expected_runs = [], [], [], 0
    (OUT / "per_hop").mkdir(parents=True, exist_ok=True)
    done = sorted({(b, r) for b in BENCHMARKS for r in ROUTES if any(RUNS.glob(f"{b}_{r}_K*_*/summary.csv"))},
                  key=lambda item: (BENCHMARKS.index(item[0]), ROUTES.index(item[1])))
    for benchmark, route in done:
            info = TraceInfo(benchmark, route)
            extra = [k for k in EXTRA_K if any(RUNS.glob(f"{benchmark}_{route}_K{k}_*/summary.csv"))]
            for k in list(K_VALUES) + extra:
                expected_runs += len(STRATEGIES)
                for strategy in STRATEGIES:
                    folder = RUNS / f"{benchmark}_{route}_K{k}_{strategy}"
                    if not (folder / "summary.csv").exists():
                        missing.append(folder.name)
                        continue
                    total, share = memories(k, strategy)
                    for row in csv.DictReader((folder / "summary.csv").open()):
                        seed = int(row["seed"])
                        n = num(row["requests"])
                        timing = {int(t["request_id"]): t for t in csv.DictReader((folder / f"timing_{strategy}_{seed}.csv").open())}
                        ready = {rid: num(t["entanglement_generation_time_ms"]) < READY_BELOW_MS for rid, t in timing.items()}
                        full, partial, miss = chain_shares(ready, info)
                        audit = json.loads((folder / f"audit_{strategy}_{seed}.json").read_text())
                        entry = dict(benchmark=benchmark, route=route, K=k, strategy=LABEL[strategy], seed=seed,
                                     memories_per_core=total, pregeneration_share=share if strategy != "on-demand" else 0,
                                     hops=int(n), completion=num(row["completion_rate"]), audit_violations=len(audit["violations"]),
                                     latency_ms=num(row["request_latency_mean_ms"]), p95_ms=num(row["request_latency_p95_ms"]),
                                     makespan_s=num(row["end_to_end_latency_ms"]) / 1000,
                                     fidelity=num(row["average_delivered_epr_fidelity"]),
                                     hop_coverage_pct=100 * sum(ready.values()) / len(ready),
                                     chain_full_pct=full, chain_partial_pct=partial, chain_miss_pct=miss,
                                     admission_wait_ms=num(row["average_admission_wait_ms"]),
                                     waited_pct=100 * num(row["requests_that_waited_fraction"]),
                                     retries=num(row["total_retries"]), peak_booked_memories=peak_booked(folder, strategy, seed))
                        if strategy == "dynamic":
                            generated = num(row["generated_compiler_pairs"])
                            entry.update(utilisation_pct=100 - num(row["compiler_waste_percentage"]),
                                         wastage_pct=num(row["compiler_waste_percentage"]), pairs_generated=generated,
                                         pairs_per_hop=generated / n, expired_pairs=num(row["expired_compiler_pairs"]),
                                         hits_pct=100 * num(row["pregenerated_hits"]) / n,
                                         planner_blocked_pct=100 * num(row["planner_blocked_preparations"]) / n,
                                         storage_ms=num(row["average_storage_time_ms"]))
                            rows = lead_table(benchmark, route, k, seed, info, folder, timing)
                            pd.DataFrame(rows).to_csv(OUT / "per_hop" / f"{benchmark}_{route}_K{k}_seed{seed}.csv", index=False)
                            hops += rows
                        elif strategy in ("continuous", "adaptive-continuous"):
                            # The protocol's "unused" counter also counts released cache reservations that never held a
                            # pair (Sanjeev, docs/research/compiler-pregeneration/qft-three-strategies-10ns-2026-11-03), so
                            # it is not used.  Generated (pair entangled) and used (pair consumed by a request) are sound;
                            # both count each endpoint, so their ratio is a pair ratio.
                            generated = num(row["protocol_generated_pairs"]) / 2
                            used = num(row["protocol_used_pairs"]) / 2
                            utilisation = 100 * used / generated if generated else math.nan
                            entry.update(utilisation_pct=utilisation, wastage_pct=100 - utilisation, pairs_generated=generated,
                                         pairs_used=used, pairs_per_hop=generated / n)
                        per_seed.append(entry)
    frame = pd.DataFrame(per_seed)
    odg = frame[frame.strategy == "ODG"].set_index(["benchmark", "route", "K", "seed"])["latency_ms"]
    frame["gain_vs_odg_pct"] = [100 * (1 - r.latency_ms / odg.get((r.benchmark, r.route, r.K, r.seed), math.nan))
                                for r in frame.itertuples()]
    keys = ["benchmark", "route", "K", "strategy"]
    metrics = [c for c in frame.columns if c not in keys + ["seed"]]
    summary = frame.groupby(keys, sort=False)[metrics].mean(numeric_only=True).reset_index()
    summary.insert(4, "seeds", frame.groupby(keys, sort=False)["seed"].count().values)
    frame.to_csv(OUT / "per_seed.csv", index=False)
    summary.to_csv(OUT / "summary.csv", index=False)

    lead = pd.DataFrame(hops)
    sheets = {}
    if not lead.empty:
        for basis in ("lead_active", "lead_logical"):
            label = lead[basis].map(lambda v: "on demand" if pd.isna(v) else f"L-{int(v)}")
            table = (lead.assign(lead=label).groupby(["benchmark", "route", "K", "seed", "lead"]).size()
                     .unstack("lead", fill_value=0))
            order = sorted([c for c in table.columns if c != "on demand"], key=lambda c: int(c[2:])) + \
                    [c for c in table.columns if c == "on demand"]
            table = table[order]
            share = 100 * table.div(table.sum(axis=1), axis=0)
            sheets[basis] = share.groupby(["benchmark", "route", "K"], sort=False).mean().round(2).reset_index()
        outcome = (lead.groupby(["benchmark", "route", "K", "seed", "outcome"]).size().unstack("outcome", fill_value=0))
        sheets["outcome"] = (100 * outcome.div(outcome.sum(axis=1), axis=0)).groupby(
            ["benchmark", "route", "K"], sort=False).mean().round(2).reset_index()

    checks = pd.DataFrame([
        dict(check="benchmark-route pairs analysed", value=", ".join(f"{b} {r}" for b, r in done)),
        dict(check="runs expected for them", value=expected_runs),
        dict(check="runs found", value=len(frame.groupby(keys))),
        dict(check="runs missing", value=len(missing)),
        dict(check="seeds with completion < 1", value=int((frame.completion < 1).sum())),
        dict(check="seeds with audit violations", value=int((frame.audit_violations > 0).sum())),
        dict(check=f"largest peak booked memories per core at K=inf (limit {INFINITE})",
             value=frame.loc[frame.K == "inf", "peak_booked_memories"].max()),
    ])
    readme = pd.DataFrame({"README": (__doc__ + "\nSetup: see tools/benchmark_study/run_matrix.py.").splitlines()})
    with pd.ExcelWriter(OUT / "benchmark_study.xlsx") as xl:
        readme.to_excel(xl, sheet_name="README", index=False)
        summary.round(4).to_excel(xl, sheet_name="Summary", index=False)
        frame.round(4).to_excel(xl, sheet_name="PerSeed", index=False)
        for metric, title in (("latency_ms", "Latency"), ("gain_vs_odg_pct", "Gain_vs_ODG"), ("fidelity", "Fidelity"),
                              ("hop_coverage_pct", "Coverage_hop"), ("chain_full_pct", "Coverage_chain_full"),
                              ("utilisation_pct", "Utilisation"), ("wastage_pct", "Wastage"),
                              ("admission_wait_ms", "Admission_wait"), ("makespan_s", "Makespan")):
            pivot = summary.pivot_table(index=["benchmark", "route", "strategy"], columns="K", values=metric, sort=False)
            pivot = pivot[[k for k in list(K_VALUES) + list(EXTRA_K) if k in pivot.columns]]
            pivot.round(4).to_excel(xl, sheet_name=title)
        for name, title in (("lead_active", "Lead_active"), ("lead_logical", "Lead_logical"), ("outcome", "Hop_outcome")):
            if name in sheets:
                sheets[name].to_excel(xl, sheet_name=title, index=False)
        for (b, r), part in summary.groupby(["benchmark", "route"], sort=False):
            part.round(4).to_excel(xl, sheet_name=f"{b[:18]}_{r}"[:31], index=False)   # one tab per benchmark and route
        checks.to_excel(xl, sheet_name="Checks", index=False)
    print(checks.to_string(index=False))
    print("missing:", missing[:10], "..." if len(missing) > 10 else "")
    print("wrote", OUT / "benchmark_study.xlsx")


if __name__ == "__main__":
    main()
