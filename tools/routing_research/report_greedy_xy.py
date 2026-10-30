"""Report a matched XY/Greedy study on QFT, QAOA and BV."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean, stdev
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    workloads = ("qft", "qaoa", "bv"); routes = ("xy", "greedy")
    rows = list(csv.DictReader((a.study / "runtime.csv").open()))
    assert len(rows) == 48, "expected four seeds, two routes, two strategies, three workloads"
    audits = []
    for path in a.study.glob("simulation/*/seed_42/*/audit*.json"):
        d = json.loads(path.read_text())
        assert not d["violations"] and d["completed_requests"] == d["total_requests"]
        audits.append(dict(path=str(path.relative_to(a.study)), **d))
    assert len(audits) == 48
    aggregate = []
    for w in workloads:
        for route in routes:
            for strategy in ("dynamic", "on-demand"):
                rs = [r for r in rows if r["workload"] == w and r["algorithm"] == route and r["strategy"] == strategy]
                assert len(rs) == 4 and all(float(r["completion_rate"]) == 1 for r in rs)
                d = dict(workload=w, algorithm=route, strategy=strategy, seeds=4)
                for field in ("request_latency_mean_ms", "request_latency_p95_ms", "end_to_end_latency_ms", "average_delivered_epr_fidelity", "average_admission_wait_ms"):
                    vs = [float(r[field]) for r in rs]
                    d[field] = mean(vs); d[field + "_sd"] = stdev(vs)
                aggregate.append(d)
    structural = list(csv.DictReader((a.study / "structural.csv").open()))
    heat = {}; congestion = []
    for w in workloads:
        for route in routes:
            core = np.load(a.study / "traces" / w / "seed_42" / route / "core_demand.npy")
            active = core.sum(axis=1) > 0
            heat[w, route] = 100 * (core[active] > 4).mean(axis=0)
            d = next(dict(r) for r in structural if r["workload"] == w and r["algorithm"] == route)
            d["any_core_congested_active_layer_percent"] = 100 * (core[active] > 4).any(axis=1).mean()
            d["mean_core_congested_active_layer_percent"] = float(heat[w, route].mean())
            congestion.append(d)
    write(a.output / "aggregate.csv", aggregate); write(a.output / "congestion.csv", congestion)
    write(a.output / "all_seeds.csv", rows)
    (a.output / "audits.json").write_text(json.dumps(audits, indent=2))
    fig, axes = plt.subplots(3, 2, figsize=(9, 12), layout="constrained")
    for i, w in enumerate(workloads):
        for j, route in enumerate(routes):
            ax = axes[i, j]; values = heat[w, route].reshape(4, 4)
            im = ax.imshow(values, vmin=0, vmax=100, cmap="YlOrRd")
            ax.set_title(w.upper() + " / " + route)
            for r in range(4):
                for c in range(4):
                    ax.text(c, r, f"C{4*r+c}\n{values[r,c]:.1f}%", ha="center", va="center", fontsize=9)
            ax.set_xticks(range(4)); ax.set_yticks(range(4))
    fig.suptitle("Congested layers per core: Greedy vs XY\n96 qubits; demand > 4 routes/core; denominator = communication-active layers")
    fig.colorbar(im, ax=axes.ravel().tolist(), label="Congested / communication-active layers (%)", shrink=.7)
    fig.savefig(a.output / "congestion.png", dpi=160); plt.close(fig)
    def metric_table(strategy):
        lines = ["| Workload | Route | Mean hop latency (ms) | Makespan (s) | Delivered EPR fidelity |", "| --- | --- | ---: | ---: | ---: |"]
        for d in aggregate:
            if d["strategy"] == strategy:
                lines.append(f"| {d['workload']} | {d['algorithm']} | {d['request_latency_mean_ms']:.4f} ± {d['request_latency_mean_ms_sd']:.4f} | {d['end_to_end_latency_ms']/1000:.4f} ± {d['end_to_end_latency_ms_sd']/1000:.4f} | {d['average_delivered_epr_fidelity']:.5f} |")
        return "\n".join(lines)
    text = """# Greedy versus XY: QFT, QAOA and BV, 2026-10-30

Fresh 96-qubit MQT Bench circuits, T-HQA/OEE mapping seed 42, circuit seed 42,
4x4 mesh, eight data slots and four communication memories/core. Each workload
is generated and mapped once; both routes preserve the same migrations and
placements. Both use shortest paths. Physics seeds 60–63, compiler C=4,
all-chain preparation, two-layer lead, ready-first admission, native handoff,
50 ms compiler reservation cap and zero artificial pregeneration buffer.
SeQUeNCe 0.8.1 is pinned to cf5283cdfd6692a82a090d15fb09fbc01bd322fc.
All 48 trials completed every request and passed runtime audits.

BV uses the linked MQT benchmark's default static layout and alternating hidden
string, with 96 total qubits including its flag. Final measurements are removed
and circuits normalized to rz/sx/x/cx before mapping; normalized circuit and
factory source hashes are retained. QAOA parameters follow the factory defaults
and parameter binding seed recorded in its input manifest.

## Compiler-driven C=4

Values are mean ± sample standard deviation across four physics seeds; fidelity
is the mean delivered EPR fidelity, not a circuit success probability.

""" + metric_table("dynamic") + "\n\n## ODG on the same routes\n\n" + metric_table("on-demand")
    text += "\n\n## Static congestion\n\n| Workload | Route | Hops | Excess demand above 4 | Overloaded core-layers | Layers with any overloaded core (%) |\n| --- | --- | ---: | ---: | ---: | ---: |\n"
    for d in congestion:
        text += f"| {d['workload']} | {d['algorithm']} | {d['hops']} | {float(d['excess']):g} | {d['overloaded_core_layers']} | {d['any_core_congested_active_layer_percent']:.2f} |\n"
    text += """
![Congestion heatmaps](congestion.png)

Each heatmap cell divides that core's overloaded layers by all network
communication-active layers. This is static route demand, not measured queue
occupancy. A relay counts once per route here. Zero overload does not mean zero
traffic. See aggregate.csv for measured admission waiting and p95 hop latency.

## Interpretation

"""
    for w in workloads:
        xy = next(d for d in aggregate if d['workload']==w and d['algorithm']=='xy' and d['strategy']=='dynamic')
        g = next(d for d in aggregate if d['workload']==w and d['algorithm']=='greedy' and d['strategy']=='dynamic')
        text += f"- {w}: Greedy changes compiler mean hop latency by {100*(g['request_latency_mean_ms']/xy['request_latency_mean_ms']-1):+.2f}% and makespan by {100*(g['end_to_end_latency_ms']/xy['end_to_end_latency_ms']-1):+.2f}% relative to XY.\n"
    text += """
Fewer static overloads need not produce proportional runtime gains. BV has sparse
communication and no overload under either route, so there is no congestion
bottleneck for Greedy to remove. Makespan is the simulator's workload completion
clock, including a 5 ms gap per empty logical layer. BV has 316 empty layers,
so roughly 1.58 seconds of its makespan comes from this fixed gap. It is not a hardware circuit
execution prediction. Latency is eligibility to EPR delivery, including admission,
control and retries. No preparation window is subtracted; data teleportation,
local gate execution and data-memory occupancy are not modeled. One mapping per
workload and four physics seeds do not establish mapping-independent superiority.
These are fresh inputs, not the frozen inputs in the previous routing report.

## Evidence

`all_seeds.csv`, `aggregate.csv`, `congestion.csv` and `audits.json` retain derived
measurements. The dated evidence archive retains input circuits/mappings, source
hashes, routed traces, exact simulation commands, timing records and all audits.
The BV source is https://github.com/munich-quantum-toolkit/bench/blob/main/src/mqt/bench/benchmarks/bv.py.
"""
    (a.output / "README.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
