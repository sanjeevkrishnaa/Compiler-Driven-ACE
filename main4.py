from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
import matplotlib.pyplot as plt
import numpy as np
import csv
import os
import json
import random
from parallel_core import run_parallel_experiment, generate_layered_requests_sequential, generate_structured_layered_requests_sequential
from pathlib import Path

SECOND = int(1e12)

def convert_to_layered_requests(num_requests: int, memo_size: int, fidelity: float, 
                                entanglement_number: int, seed: int = 0, 
                                pattern: str = 'random') -> list:
    '''
    Converts sequential requests to layered format (one request per layer).
    
    Args:
        num_requests: Number of requests to generate
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility
        pattern: 'random' for random pairs or 'first_last' for column 0 to column 3
        
    Return:
        list of layers, where each layer is a list with one request:
        [
            [(id, src, dst, memo_size, fidelity, entanglement_number)],  # Layer 0
            [(id, src, dst, memo_size, fidelity, entanglement_number)],  # Layer 1
            ...
        ]
    '''
    if pattern == 'first_last':
        return generate_structured_layered_requests_sequential(
            num_layers=num_requests,
            memo_size=memo_size,
            fidelity=fidelity,
            entanglement_number=entanglement_number,
            seed=seed
        )
    else:  # random
        return generate_layered_requests_sequential(
            num_layers=num_requests,
            memo_size=memo_size,
            fidelity=fidelity,
            entanglement_number=entanglement_number,
            seed=seed
        )

def load_traffic_from_file(traffic_file: str) -> list:
    """
    Load traffic pattern from JSON file.
    Expected format: list of requests
    """
    try:
        with open(traffic_file, 'r') as f:
            traffic = json.load(f)
        if "layers" in traffic:
            return traffic["layers"]
        else:
            return traffic
    except Exception as e:
        print(f"Error loading traffic file {traffic_file}: {e}")
        return None

if __name__ == "__main__":
    # Create directories
    os.makedirs('plots', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    os.makedirs('log', exist_ok=True)
    os.makedirs('test', exist_ok=True)
    
    # Configuration
    num_requests = 1000  # Total number of requests
    pregeneration_time_ms = 5.3  # Pre-generation buffer time
    request_duration_ms = 50  # Maximum duration for each request
    seed = 42    
    
    # Grid configurations with hard-coded paths: (width, breadth, short_name, config_0, config_3)
    grid_configs = [
        (1, 2, "1x2", "config/final_config/grid_1x2_ace_0.json", "config/final_config/grid_1x2_ace_3.json"),
        # (2, 2, "2x2", "config/final_config/grid_2x2_ace_0.json", "config/final_config/grid_2x2_ace_3.json"),
        # (4, 4, "4x4", "config/final_config/grid_4x4_ace_0.json", "config/final_config/grid_4x4_ace_3.json"),
        # (4, 8, "4x8", "config/final_config/grid_4x8_ace_0.json", "config/final_config/grid_4x8_ace_3.json"),
        # (8, 8, "8x8", "config/final_config/grid_8x8_ace_0.json", "config/final_config/grid_8x8_ace_3.json"),
    ]
    
    # Hard-coded traffic patterns and their files
    benchmarks = [
        "cuccaro" #,"draper","mcmtv","qft"
    ]
    
    # Experiments configuration
    all_results = {}
    
    # Iterate through each grid configuration
    for grid_width, grid_breadth, grid_name, config_ace_0, config_ace_3 in grid_configs:
        print(f"\n{'='*100}")
        print(f"GRID CONFIGURATION: {grid_name} ({grid_width}x{grid_breadth})")
        print(f"{'='*100}\n")
        
        # Iterate through each benchmark
        for benchmark in benchmarks:
            print(f"\n{'-'*100}")
            print(f"TRAFFIC PATTERN: {benchmark}")
            print(f"{'-'*100}\n")
            
            traffic_file = f"real_benchmarks/traffic_files/{benchmark}_fixed_{grid_name}_q8_s1_traffic.json"
            # traffic_file = f"real_benchmarks/traffic_files/{benchmark}_fixed_{grid_name}_q8_s2_traffic.json"
            
            if not os.path.exists(traffic_file):
                print(f"Traffic file not found: {traffic_file}, skipping...")
                continue
            
            print(f"Using traffic file: {traffic_file}")
            
            layered_requests = load_traffic_from_file(traffic_file)
            
            print(f"Total requests: {len(layered_requests)}")
            print(layered_requests[1])
            
            # Define experiments for this grid and traffic pattern
            experiments = [
                {
                    "label": "ODG",
                    "config": config_ace_0,
                    "update_prob": False,
                    "purify_setting": False
                },
                {
                    "label": "ODGwP",
                    "config": config_ace_0,
                    "update_prob": False,
                    "purify_setting": True
                },
                {
                    "label": "CGP",
                    "config": config_ace_3,
                    "update_prob": False,
                    "purify_setting": False
                },
                {
                    "label": "ACGP",
                    "config": config_ace_3,
                    "update_prob": True,
                    "purify_setting": False
                },
                {
                    "label": "CGPwP",
                    "config": config_ace_3,
                    "update_prob": False,
                    "purify_setting": True
                },
                {
                    "label": "ACGPwP",
                    "config": config_ace_3,
                    "update_prob": True,
                    "purify_setting": True
                }
            ]
            
            # Run all experiments for this grid and traffic pattern
            pattern_results = {}
            for exp in experiments:
                print(f"\n  Running: {exp['label']}")
                
                # Check if config file exists
                if not os.path.exists(exp['config']):
                    print(f"  Config file not found: {exp['config']}, skipping...")
                    continue
                
                result = run_parallel_experiment(
                    config_file=exp['config'],
                    update_prob_setting=exp['update_prob'],
                    purify_setting=exp['purify_setting'],
                    layered_requests=layered_requests,
                    pregeneration_time_ms=pregeneration_time_ms,
                    request_duration_ms=request_duration_ms,
                    experiment_label=exp['label']
                )
                
                pattern_results[exp['label']] = result
            
            # Store results with composite key
            composite_key = f"{grid_name}_{benchmark}"
            all_results[composite_key] = pattern_results
            
            # Print average results for this pattern
            print(f"\n{'  '}{'-'*80}")
            print(f"  AVERAGE RESULTS FOR {benchmark}")
            print(f"{'  '}{'-'*80}")
            for label, result in pattern_results.items():
                fidelity_data = result['fidelity_dict']
                avg_fidelity = sum(f[0] for f in fidelity_data.values()) / len(fidelity_data) if fidelity_data else 0
                
                latency_data = result['latency_dict']
                avg_latency = sum(latency_data.values()) / len(latency_data) / MILLISECOND if latency_data else 0
                
                print(f"\n  {label}:")
                print(f"    Average Fidelity: {avg_fidelity:.4f}")
                print(f"    Average Latency: {avg_latency:.2f} ms")
                print(f"    E2E Latency: {result['stats']['end_to_end_latency_ms']:.2f} ms")
            
            # Save data to CSV files for this pattern
            print(f"\n  Saving CSV data for {benchmark}...")
            
            # Create a mapping from request ID to source and destination
            request_info_map = {}
            for layer in layered_requests:
                for req in layer:
                    req_id, src_name, dst_name, memo_size, fidelity, entanglement_number = req
                    request_info_map[req_id] = {'src': src_name, 'dst': dst_name}
            
            for label, result in pattern_results.items():
                latency_data = result['latency_dict']
                fidelity_data = result['fidelity_dict']
                
                # Create a safe filename
                safe_label = label.replace(" ", "_").replace("(", "").replace(")", "")
                csv_filename = f'data/{safe_label}_{benchmark}.csv'
                
                with open(csv_filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Request_ID', 'Source', 'Destination', 'Latency_ms', 'Fidelity'])
                    
                    # Sort by request ID
                    sorted_reservations = sorted(fidelity_data.keys(), key=lambda r: r.identity)
                    for reservation in sorted_reservations:
                        req_id = reservation.identity
                        src_name = request_info_map[req_id]['src'] if req_id in request_info_map else 'N/A'
                        dst_name = request_info_map[req_id]['dst'] if req_id in request_info_map else 'N/A'
                        fidelity = fidelity_data[reservation][0] if reservation in fidelity_data else 0
                        latency_ms = latency_data[reservation] / MILLISECOND if reservation in latency_data else 0
                        writer.writerow([req_id, src_name, dst_name, f'{latency_ms:.4f}', f'{fidelity:.6f}'])
                
                print(f"    Saved {csv_filename}")

    # Generate comparative plots across all configurations and patterns
    print(f"\n{'='*100}")
    print("CREATING COMPARATIVE PLOTS")
    print(f"{'='*100}\n")
    
    # Create summary plot for each grid configuration
    for grid_width, grid_breadth, grid_name in grid_configs:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        all_patterns_for_grid = [key for key in all_results.keys() if key.startswith(grid_name)]
        
        if not all_patterns_for_grid:
            print(f"No results found for grid {grid_name}, skipping plot...")
            continue
        
        # Collect data for all patterns and experiments
        all_latencies = []
        all_fidelities = []
        all_labels = []
        
        for composite_key in sorted(all_patterns_for_grid):
            pattern_results = all_results[composite_key]
            for exp_label in sorted(pattern_results.keys()):
                result = pattern_results[exp_label]
                
                latency_data = result['latency_dict']
                fidelity_data = result['fidelity_dict']
                
                if latency_data:
                    latency_values = [latency / MILLISECOND for latency in latency_data.values()]
                    all_latencies.append(latency_values)
                    
                fidelity_values = [f[0] for f in fidelity_data.values()]
                all_fidelities.append(fidelity_values)
                
                # Create label with pattern info
                benchmark = composite_key.split('_')[1]
                all_labels.append(f"{exp_label.split('_')[1]}_{benchmark}")
        
        if all_latencies:
            # Create boxplot for latency
            boxprops = dict(facecolor="lightcoral", color="black")
            medianprops = dict(color="black", linewidth=2)
            whiskerprops = dict(color="black")
            capprops = dict(color="black")
            
            ax1.boxplot(all_latencies, labels=all_labels, patch_artist=True, 
                        showmeans=False, showfliers=False,
                        boxprops=boxprops, medianprops=medianprops, 
                        whiskerprops=whiskerprops, capprops=capprops, widths=0.6)
            ax1.set_title(f'{grid_name} - Request Latency Distribution', fontsize=14, fontweight='bold')
            ax1.set_ylabel('Latency (ms)', fontsize=12)
            ax1.set_xticklabels(all_labels, fontsize=9, rotation=45, ha='right')
            ax1.grid(True, alpha=0.3, axis='y')
        
        if all_fidelities:
            # Create boxplot for fidelity
            boxprops = dict(facecolor="lightblue", color="black")
            medianprops = dict(color="black", linewidth=2)
            
            ax2.boxplot(all_fidelities, labels=all_labels, patch_artist=True, 
                        showmeans=False, showfliers=False,
                        boxprops=boxprops, medianprops=medianprops, 
                        whiskerprops=whiskerprops, capprops=capprops, widths=0.6)
            ax2.set_title(f'{grid_name} - Entanglement Fidelity Distribution', fontsize=14, fontweight='bold')
            ax2.set_ylabel('Fidelity', fontsize=12)
            ax2.set_xticklabels(all_labels, fontsize=9, rotation=45, ha='right')
            ax2.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        plot_filename = f"plots/experiment_results_{grid_name}.png"
        plt.savefig(plot_filename, dpi=300, bbox_inches='tight')
        print(f"Saved {plot_filename}")
        plt.close()
    
    print(f"\n{'='*100}")
    print("ALL EXPERIMENTS COMPLETE!")
    print(f"{'='*100}\n")