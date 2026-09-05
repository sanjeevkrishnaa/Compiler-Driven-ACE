"""
Run PIR-based experiments on a 4x4 mesh for three configurations:
  1. On-Demand (ODG)        ace_0 config, no proactive entanglement
  2. CGP (no adaptation)    ace_3 config, update_prob=False
  3. ACGP (with adaptation) ace_3 config, update_prob=True

For each PIR value and traffic pattern (random / hotspot):
  - Generate or load the traffic
  - Run all three experiments with the SAME request queue
  - Compute average latency and fidelity
  - Draw whisker (box) plots

Uses RequestAppLatency which stops on first successful entanglement.
"""

from collections import defaultdict
import os
import json
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")          # non-interactive backend for saving plots
import matplotlib.pyplot as plt

from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
import sequence.utils.log as log

from request_app import RequestAppLatency
from router_net_topo_adaptive import RouterNetTopoAdaptive
from generate_pir_traffic import (
    generate_random_traffic,
    generate_hotspot_traffic,
    save_traffic,
    load_traffic,
)

SECOND = int(1e12)


# ───────────────────────────────────────────────────────────────────────
# Experiment runner (same style as main5.py)
# ───────────────────────────────────────────────────────────────────────

def run_experiment(config_file: str,
                   update_prob_setting,   # None | bool
                   request_queue: list,
                   experiment_label: str):
    """
    Run a single simulation experiment.

    All requests are submitted via app.start() before tl.run(),
    exactly like main5.py.

    Args:
        config_file: path to the network JSON config
        update_prob_setting: None (on-demand, ignored), False (CGP), True (ACGP)
        request_queue: list of 8-tuples from generate_pir_traffic
        experiment_label: human-readable label

    Returns:
        (latency_dict, fidelity_dict)
    """
    network_topo = RouterNetTopoAdaptive(config_file)
    tl = network_topo.get_timeline()
    tl.seed(0)

    # Configure routers and apps
    name_to_apps = {}
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        app = RequestAppLatency(router)
        name_to_apps[router.name] = app
        if hasattr(router, "adaptive_continuous") and update_prob_setting is not None:
            router.adaptive_continuous.update_prob = update_prob_setting
            router.adaptive_continuous.has_empty_neighbor = True
            router.adaptive_continuous.strategy = "freshest"

    # Schedule all requests upfront (before tl.run)
    for req in request_queue:
        rid, src, dst, start_time, end_time, memo_size, fidelity, entanglement_number = req
        app = name_to_apps[src]
        app.start(dst, start_time, end_time, memo_size, fidelity, entanglement_number, rid)

    # Run
    tl.init()
    tl.run()

    # Collect results
    latency_dict = defaultdict(float)
    fidelity_dict = defaultdict(list)
    for _, app in name_to_apps.items():
        latency_dict |= app.latency
        fidelity_dict |= app.entanglement_fidelities

    # Summary
    total = len(request_queue)
    served = len(latency_dict)
    avg_lat = (np.mean(list(latency_dict.values())) / MILLISECOND) if latency_dict else 0
    avg_fid = (np.mean([f[0] for f in fidelity_dict.values()])) if fidelity_dict else 0

    print(f"  [{experiment_label}]  served={served}/{total}  "
          f"avg_latency={avg_lat:.2f} ms  avg_fidelity={avg_fid:.4f}")

    return latency_dict, fidelity_dict


# ───────────────────────────────────────────────────────────────────────
# Plotting helpers
# ───────────────────────────────────────────────────────────────────────

def whisker_plot(all_data: dict, ylabel: str, title: str, filename: str):
    """
    Draw a box-and-whisker plot.

    Args:
        all_data: {label: [values]} – one entry per experiment
        ylabel: y-axis label
        title: plot title
        filename: output file path
    """
    labels = list(all_data.keys())
    data = [all_data[l] for l in labels]

    fig, ax = plt.subplots(figsize=(10, 6))

    bp = ax.boxplot(data, labels=labels, patch_artist=True,
                    showmeans=True, showfliers=False, widths=0.5,
                    meanprops=dict(marker="D", markerfacecolor="red", markersize=6),
                    medianprops=dict(color="black", linewidth=2),
                    whiskerprops=dict(color="black"),
                    capprops=dict(color="black"))

    colors = ["#AEC6CF", "#FFD1DC", "#B5EAD7", "#FFDAC1", "#C3B1E1", "#F0E68C"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    ax.set_ylabel(ylabel, fontsize=13)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")
    plt.xticks(fontsize=11, rotation=20, ha="right")
    plt.yticks(fontsize=11)
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved plot → {filename}")


# ───────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("plots/pir", exist_ok=True)
    os.makedirs("data/pir", exist_ok=True)
    os.makedirs("test/pir_traffic", exist_ok=True)

    # ─── Experiment parameters ────────────────────────────────────────
    pir_values = [0.1, 0.2]               # packets per core per ms
    total_time_ms = 100.0                   # traffic generation window (ms)
    window_ms = 20.0        # window size for traffic generation (ms)
    seed = 42
    patterns = ["random", "hotspot"]       # traffic patterns

    # Config files (on the 4x4 mesh)
    config_ace_0 = "config/final_config/grid_4x4_ace_0.json"
    config_ace_3 = "config/final_config/grid_4x4_ace_3.json"

    experiments_spec = [
        {
            "label": "On-Demand (ODG)",
            "config": config_ace_0,
            "update_prob": None,          # ACP disabled (ace=0)
        },
        {
            "label": "CGP",
            "config": config_ace_3,
            "update_prob": False,
        },
        {
            "label": "ACGP",
            "config": config_ace_3,
            "update_prob": True,
        },
    ]

    # ─── Run all combinations ─────────────────────────────────────────
    # Stores: {(pattern, pir): {exp_label: {latency: [...], fidelity: [...]}}}
    master_results = {}

    for pattern in patterns:
        for pir in pir_values:
            combo_key = (pattern, pir)
            print(f"\n{'='*80}")
            print(f"  Pattern={pattern}  PIR={pir}  total_time={total_time_ms} ms")
            print(f"{'='*80}")

            # Generate / load traffic
            traffic_file = f"test/pir_traffic/{pattern}_pir_{pir}_t{int(total_time_ms)}ms.json"
            print(f"  Generating traffic → {traffic_file}")
            if pattern == "random":
                request_queue = generate_random_traffic(
                    pir=pir, total_time_ms=total_time_ms, window_ms=window_ms, seed=seed)
            else:
                request_queue = generate_hotspot_traffic(
                    pir=pir, total_time_ms=total_time_ms, window_ms=window_ms, seed=seed,
                    hotspot_nodes=[(1, 1), (2, 2)], hotspot_probability=0.8)
            save_traffic(request_queue, traffic_file)
            print(f"  Total requests: {len(request_queue)}")

            combo_results = {}
            for exp in experiments_spec:
                label = exp["label"]
                print(f"\n  Running: {label}")
                lat_dict, fid_dict = run_experiment(
                    config_file=exp["config"],
                    update_prob_setting=exp["update_prob"],
                    request_queue=request_queue,
                    experiment_label=f"{pattern}_pir{pir}_{label}",
                )
                combo_results[label] = {
                    "latency_dict": lat_dict,
                    "fidelity_dict": fid_dict,
                }

            master_results[combo_key] = combo_results

            # ── Print averages ────────────────────────────────────────
            print(f"\n  {'─'*60}")
            print(f"  Summary for {pattern} PIR={pir}")
            print(f"  {'─'*60}")
            for label, res in combo_results.items():
                lat_vals = [v / MILLISECOND for v in res["latency_dict"].values()]
                fid_vals = [f[0] for f in res["fidelity_dict"].values()]
                avg_l = np.mean(lat_vals) if lat_vals else 0
                avg_f = np.mean(fid_vals) if fid_vals else 0
                print(f"    {label:25s}  avg_latency={avg_l:8.2f} ms  "
                      f"avg_fidelity={avg_f:.4f}  served={len(lat_vals)}")

            # ── Save CSV ──────────────────────────────────────────────
            for label, res in combo_results.items():
                safe = label.replace(" ", "_").replace("(", "").replace(")", "")
                csv_path = f"data/pir/{pattern}_pir{pir}_{safe}.csv"
                with open(csv_path, "w", newline="") as cf:
                    w = csv.writer(cf)
                    w.writerow(["Request_ID", "Latency_ms", "Fidelity"])
                    for reservation in sorted(res["fidelity_dict"].keys(),
                                              key=lambda r: r.identity):
                        rid = reservation.identity
                        lat = res["latency_dict"].get(reservation, 0) / MILLISECOND
                        fid = res["fidelity_dict"][reservation][0]
                        w.writerow([rid, f"{lat:.4f}", f"{fid:.6f}"])
                print(f"  Saved CSV → {csv_path}")

    # ─── Create whisker plots ─────────────────────────────────────────
    print(f"\n{'='*80}")
    print("Creating whisker plots …")
    print(f"{'='*80}\n")

    for (pattern, pir), combo_results in master_results.items():
        tag = f"{pattern}_pir{pir}"

        # --- latency whisker plot ---
        lat_data = {}
        for label, res in combo_results.items():
            vals = [v / MILLISECOND for v in res["latency_dict"].values()]
            if vals:
                lat_data[label] = vals
        if lat_data:
            whisker_plot(
                lat_data,
                ylabel="Latency (ms)",
                title=f"Latency Distribution  –  {pattern.title()}  PIR={pir}",
                filename=f"plots/pir/{tag}_latency_whisker.png",
            )

        # --- fidelity whisker plot ---
        fid_data = {}
        for label, res in combo_results.items():
            vals = [f[0] for f in res["fidelity_dict"].values()]
            if vals:
                fid_data[label] = vals
        if fid_data:
            whisker_plot(
                fid_data,
                ylabel="Fidelity",
                title=f"Fidelity Distribution  –  {pattern.title()}  PIR={pir}",
                filename=f"plots/pir/{tag}_fidelity_whisker.png",
            )

    # ─── Combined whisker plot across PIR values ──────────────────────
    for pattern in patterns:
        lat_data_combined = {}
        fid_data_combined = {}
        for pir in pir_values:
            combo_results = master_results.get((pattern, pir), {})
            for label, res in combo_results.items():
                key = f"{label}\nPIR={pir}"
                lat_vals = [v / MILLISECOND for v in res["latency_dict"].values()]
                fid_vals = [f[0] for f in res["fidelity_dict"].values()]
                if lat_vals:
                    lat_data_combined[key] = lat_vals
                if fid_vals:
                    fid_data_combined[key] = fid_vals

        if lat_data_combined:
            whisker_plot(
                lat_data_combined,
                ylabel="Latency (ms)",
                title=f"Latency Distribution  –  {pattern.title()}  (all PIR values)",
                filename=f"plots/pir/{pattern}_all_pir_latency_whisker.png",
            )
        if fid_data_combined:
            whisker_plot(
                fid_data_combined,
                ylabel="Fidelity",
                title=f"Fidelity Distribution  –  {pattern.title()}  (all PIR values)",
                filename=f"plots/pir/{pattern}_all_pir_fidelity_whisker.png",
            )

    print(f"\n{'='*80}")
    print("ALL EXPERIMENTS COMPLETE!")
    print(f"{'='*80}")
