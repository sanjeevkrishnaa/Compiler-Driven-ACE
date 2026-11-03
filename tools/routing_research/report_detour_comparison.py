"""Compare Detour2 against matched XY and Greedy physical trials."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
from statistics import mean, stdev
from heavy_routing import ro, write_csv, migration_latencies


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    workloads = ("qft", "qaoa", "bv"); routes = ("xy", "greedy", "detour2")
    trials = []; audits = []; hashes = None
    for w in workloads:
        for route in routes:
            folder = a.study / "simulation" / w / "seed_42" / route
            metadata = json.loads((folder / "metadata.json").read_text())
            if hashes is None: hashes = metadata["source_sha256"]
            assert metadata["source_sha256"] == hashes
            assert metadata["parameters"]["compiler_reservation_ms"] == 50
            trace = ro.read_trace(a.study / "traces" / w / "seed_42" / route / "requests.txt", 4, 4)
            chains = defaultdict(list)
            for h in trace.hops: chains[h.layer, h.qubit].append(h.request_id)
            rs = list(csv.DictReader((folder / "summary.csv").open()))
            assert len(rs) == 8 and {int(r["seed"]) for r in rs} == {60,61,62,63}
            for r in rs:
                strategy, seed = r["strategy"], r["seed"]
                audit = json.loads((folder / f"audit_{strategy}_{seed}.json").read_text())
                assert float(r["completion_rate"]) == 1 and not audit["violations"] and audit["completed_requests"] == len(trace.hops)
                audits.append(dict(workload=w, algorithm=route, strategy=strategy, seed=seed, **audit))
                parts = {int(t["request_id"]):t for t in csv.DictReader((folder / f"timing_{strategy}_{seed}.csv").open())}
                assert set(parts) == {h.request_id for h in trace.hops}
                migration_mean = mean(migration_latencies(chains, parts))
                trials.append(dict(workload=w, algorithm=route, migration_latency_mean_ms=migration_mean, **r))
    assert len(trials) == 72
    fields = ("request_latency_mean_ms", "migration_latency_mean_ms", "end_to_end_latency_ms", "average_delivered_epr_fidelity", "pregenerated_success_rate", "average_admission_wait_ms", "compiler_waste_percentage")
    aggregate = []
    for w in workloads:
        for route in routes:
            for strategy in ("dynamic", "on-demand"):
                rs = [r for r in trials if r["workload"]==w and r["algorithm"]==route and r["strategy"]==strategy]
                d = dict(workload=w, algorithm=route, strategy=strategy, seeds=len(rs))
                for field in fields:
                    values = [float(r[field]) for r in rs]
                    d[field] = mean(values); d[field+"_sd"] = stdev(values)
                aggregate.append(d)
    write_csv(a.output / "all_seeds.csv", trials); write_csv(a.output / "aggregate.csv", aggregate)
    (a.output / "audits.json").write_text(json.dumps(audits, indent=2))
    structural = [r for r in csv.DictReader((a.study / "structural.csv").open()) if r["workload"] in workloads and r["algorithm"] in routes]
    write_csv(a.output / "structural.csv", structural)
    text = """# Detour2 versus Greedy and XY, 2026-10-30

Complete 96-qubit QFT, QAOA and BV; T-HQA/OEE mapping seed 42, circuit seed 42,
4x4 mesh, four communication memories/core. All routes preserve identical
migration endpoints and layer placements. Physics seeds 60-63. Compiler C=4,
all-chain preparation, two-layer lead, ready-first event admission, native
handoff, 50 ms compiler reservation cap, zero artificial preparation buffer.
SeQUeNCe 0.8.1 at cf5283cdfd6692a82a090d15fb09fbc01bd322fc.
24 new Detour2 trials plus 48 previously measured matched XY/Greedy trials;
all 72 completed and passed audits, with identical engine-facing source hashes.

Readiness is the fraction of hop requests consuming a compiler pair physically
generated strictly before the request's first application submission. This is
not necessarily readiness at initial eligibility: admission waiting may precede
submission. Unused, expired and late-used preparations are not counted as hits.
ODG has no compiler prefetch, so its readiness metric is zero by definition.

## Compiler C=4

Means across four seeds; sample SDs are retained in aggregate.csv. Fidelity is
mean delivered EPR fidelity. Migration latency sums the sequential hop service
intervals (including admission once) for each logical migration. It accounts for
Detour2's additional hops; it is not a data-teleportation circuit simulation.

| Workload | Route | Hop latency (ms) | Migration latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
"""
    for r in aggregate:
        if r['strategy'] != 'dynamic': continue
        text += f"| {r['workload']} | {r['algorithm']} | {r['request_latency_mean_ms']:.4f} | {r['migration_latency_mean_ms']:.4f} | {r['end_to_end_latency_ms']/1000:.4f} | {100*r['average_delivered_epr_fidelity']:.3f} | {100*r['pregenerated_success_rate']:.2f} |\n"
    text += "\n## Static demand and route length\n\n| Workload | Route | Hops | Excess demand above four slots | Overloaded core-layers |\n| --- | --- | ---: | ---: | ---: |\n"
    for w in workloads:
        for route in routes:
            r = next(r for r in structural if r['workload']==w and r['algorithm']==route)
            text += f"| {w} | {route} | {r['hops']} | {float(r['excess']):g} | {r['overloaded_core_layers']} |\n"
    text += "\n## ODG on identical routes\n\n| Workload | Route | Hop latency (ms) | Migration latency (ms) | Makespan (s) | EPR fidelity (%) |\n| --- | --- | ---: | ---: | ---: | ---: |\n"
    for r in aggregate:
        if r['strategy'] != 'on-demand': continue
        text += f"| {r['workload']} | {r['algorithm']} | {r['request_latency_mean_ms']:.4f} | {r['migration_latency_mean_ms']:.4f} | {r['end_to_end_latency_ms']/1000:.4f} | {100*r['average_delivered_epr_fidelity']:.3f} |\n"
    text += """
## Interpretation and limits

"""
    for w in workloads:
        d = next(r for r in aggregate if r['workload']==w and r['algorithm']=='detour2' and r['strategy']=='dynamic')
        for route in ('xy', 'greedy'):
            b = next(r for r in aggregate if r['workload']==w and r['algorithm']==route and r['strategy']=='dynamic')
            text += f"- {w}, Detour2 vs {route}: hop latency {100*(d['request_latency_mean_ms']/b['request_latency_mean_ms']-1):+.2f}%, migration latency {100*(d['migration_latency_mean_ms']/b['migration_latency_mean_ms']-1):+.2f}%, makespan {100*(d['end_to_end_latency_ms']/b['end_to_end_latency_ms']-1):+.2f}%, readiness {100*(d['pregenerated_success_rate']-b['pregenerated_success_rate']):+.2f} percentage points.\n"
    text += """
Static overload reduction is not a runtime guarantee; detours add EPR-service
hops and can shift preparation/storage timing. Fidelity measures delivered EPR
pairs, not full circuit output fidelity. BV has no static overload and all
routes keep 24 hops. Its 316 empty layers contribute roughly 1.58 seconds through
the existing 5 ms empty-layer gap, dominating its simulated makespan. Absolute
latencies retain the configured 100 us classical-message overhead. No latency
window is subtracted. One fixed mapping per workload and four physics seeds do
not establish universal routing superiority. Detour optimization uses a two-second
per-layer solver limit; structural.csv records any layers without an optimality
proof. Unchanged total migration count makes migration latency a fairer routing
comparison than per-hop latency alone when routes have different lengths.

Reproduce with the commands in the dated evidence archive; generate Detour2 from
the same input mappings and simulate seeds 60,61,62,63 at 50 ms. Derived tables
and audits accompany this report; the prior XY/Greedy report retains its sources.
"""
    (a.output / "README.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
