from parallel_core import *

if __name__ == "__main__":
    # Create directories
    os.makedirs('plots', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    os.makedirs('log', exist_ok=True)
    
    # Grid configurations with hard-coded paths: (width, breadth, short_name, config_0, config_3)
    grid_configs = [
        # (1, 2, "1x2", "config/final_config/grid_1x2_ace_0.json", "config/final_config/grid_1x2_ace_3.json"),
        (2, 2, "2x2", "config/final_config/grid_2x2_ace_0.json", "config/final_config/grid_2x2_ace_3.json"),
        # (4, 4, "4x4", "config/final_config/grid_4x4_ace_0.json", "config/final_config/grid_4x4_ace_3.json"),
        # (8, 4, "8x4", "config/final_config/grid_8x4_ace_0.json", "config/final_config/grid_8x4_ace_3.json"),
        # (8, 8, "8x8", "config/final_config/grid_8x8_ace_0.json", "config/final_config/grid_8x8_ace_3.json"),
    ]
    
    # Hard-coded traffic patterns and their files
    benchmarks = [
        "qft",
        # "cuccaro" ,
        # "draper",
        # "mcmtv",
    ]
    
    all_results = {}
    
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
            
            print(f"Loading requests from {traffic_file}...")
            with open(traffic_file, "r") as f:
                file_contents = json.load(f)
            
            if "layers" in file_contents:
                layered_requests = file_contents["layers"]
            else:
                layered_requests = file_contents 
            
            num_layers = len(layered_requests)
            total_requests = sum(len(layer) for layer in layered_requests)
            
            print(f"\nLoaded configuration:")
            print(f"  Total layers: {num_layers}")
            print(f"  Total requests: {total_requests}")
            print(f"  Requests per layer: {[len(layer) for layer in layered_requests]}")
            
            # Configuration
            pregeneration_time_ms = 25
            request_duration_ms = 60
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
                csv_filename = f'data/{grid_name}_{safe_label}_{benchmark}.csv'
                
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

                    # Write average metrics as a summary row
                    avg_fidelity = sum(f[0] for f in fidelity_data.values()) / len(fidelity_data) if fidelity_data else 0
                    avg_latency = sum(latency_data.values()) / len(latency_data) / MILLISECOND if latency_data else 0
                    e2e_latency = result['stats']['end_to_end_latency_ms'] if 'stats' in result and 'end_to_end_latency_ms' in result['stats'] else 0
                    writer.writerow([])  # Blank row
                    writer.writerow(['AVERAGES', '', '', f'{avg_latency:.4f}', f'{avg_fidelity:.6f}'])
                    writer.writerow(['E2E_LATENCY', '', '', f'{e2e_latency:.4f}', ''])
                
                print(f"    Saved {csv_filename}")

    
    # print(f"Loading requests from {request_file}...")
    # with open(request_file, "r") as f:
    #     file_contents = json.load(f)
    
    # if "layers" in file_contents:
    #     layered_requests = file_contents["layers"]
    # else:
    #     layered_requests = file_contents 
    
    # total_requests = sum(len(layer) for layer in layered_requests)
    # num_layers = len(layered_requests)
    
    # print(f"\nLoaded configuration:")
    # print(f"  Total layers: {num_layers}")
    # print(f"  Total requests: {total_requests}")
    # print(f"  Requests per layer: {[len(layer) for layer in layered_requests]}")
    
    # # Configuration
    # pregeneration_time_ms = 20
    # request_duration_ms = 100
    
    # # Store results
    # all_results = []
    
    # # Experiment 1: ACE-0 (on-demand)
    # exp_label = f"real_ACE0"
    # print(f"\n{'='*80}")
    # print(f"Running {exp_label}")
    # print(f"{'='*80}\n")
    # result = run_parallel_experiment(
    #     config_file='config/final_config/grid_4x4_ace_0.json',
    #     update_prob_setting=False,
    #     purify_setting=False,
    #     layered_requests=layered_requests,
    #     pregeneration_time_ms=pregeneration_time_ms,
    #     request_duration_ms=request_duration_ms,
    #     experiment_label=exp_label
    # )
    # result['label'] = exp_label
    # result['config'] = 'On-Demand'
    # result['update_prob'] = None
    # all_results.append(result)
    
    # # Experiments 2-11: CGP-1 through CGP-5 (without update)
    # for ace_num in range(3, 4):
    #     # Without update
    #     exp_label = f"real_CGP{ace_num}_NoUpdate"
    #     print(f"\n{'='*80}")
    #     print(f"Running {exp_label}")
    #     print(f"{'='*80}\n")
    #     result = run_parallel_experiment(
    #         config_file=f'config/final_config/grid_4x4_ace_{ace_num}.json',
    #         update_prob_setting=False,
    #         purify_setting=False,
    #         layered_requests=layered_requests,
    #         pregeneration_time_ms=pregeneration_time_ms,
    #         request_duration_ms=request_duration_ms,
    #         experiment_label=exp_label
    #     )
    #     result['label'] = exp_label
    #     result['config'] = f'CGP-{ace_num} (No Update)'
    #     result['update_prob'] = False
    #     all_results.append(result)

    #     # With update (commented out)
    #     # exp_label = f"real_CGP{ace_num}_WithUpdate"
    #     # print(f"\n{'='*80}")
    #     # print(f"Running {exp_label}")
    #     # print(f"{'='*80}\n")
    #     # result = run_parallel_experiment(
    #     #     config_file=f'config/grid_4x4_ace_{ace_num}.json',
    #     #     update_prob_setting=True,
    #     #     purify_setting=False,
    #     #     layered_requests=layered_requests,
    #     #     pregeneration_time_ms=pregeneration_time_ms,
    #     #     request_duration_ms=request_duration_ms,
    #     #     experiment_label=exp_label
    #     # )
    #     # result['label'] = exp_label
    #     # result['config'] = f'CGP-{ace_num} (With Update)'
    #     # result['update_prob'] = True
    #     # all_results.append(result)

    # # Save CSV data
    # print(f"\n{'='*80}")
    # print("SAVING CSV DATA")
    # print(f"{'='*80}\n")
    
    # # Create request info map
    # request_info_map = {}
    # for layer in layered_requests:
    #     for req in layer:
    #         request_info_map[req[0]] = (req[1], req[2])
    
    # for result in all_results:
    #     csv_filename = f"data/{result['label']}.csv"
    #     with open(csv_filename, 'w', newline='') as csvfile:
    #         writer = csv.writer(csvfile)
    #         writer.writerow(['Request_ID', 'Source', 'Destination', 'Latency_ms', 'Fidelity'])
            
    #         for reservation, latency in sorted(result['latency_dict'].items(), key=lambda x: x[0].identity):
    #             req_id = reservation.identity
    #             src, dst = request_info_map.get(req_id, ('Unknown', 'Unknown'))
    #             fidelity = result['fidelity_dict'][reservation][0] if reservation in result['fidelity_dict'] else 0
    #             latency_ms = latency / MILLISECOND
    #             writer.writerow([req_id, src, dst, f"{latency_ms:.4f}", f"{fidelity:.6f}"])
    #     print(f"Saved {csv_filename}")
    
    # # Create comparison bar chart
    # print(f"\n{'='*80}")
    # print("CREATING COMPARISON PLOT")
    # print(f"{'='*80}\n")
    
    # # Separate On-Demand baseline from CGP experiments
    # ondemand_latency = all_results[0]['stats']['end_to_end_latency_ms']
    # ace_results = all_results[1:]  # CGP-1 through CGP-5
    
    # # Prepare data for grouped bars
    # ace_configs = []
    # no_update_latencies = []
    
    # for i in range(0, len(ace_results)):
    #     no_update = ace_results[i]

    #     ace_num = i + 1
    #     ace_configs.append(f'{ace_num}')
    #     no_update_latencies.append(no_update['stats']['end_to_end_latency_ms'])
    
    # # Create grouped bar chart
    # fig, ax = plt.subplots(figsize=(10, 8))
    
    # x = np.arange(len(ace_configs))
    # width = 0.4
    
    # bars1 = ax.bar(x, no_update_latencies, width, label='No Update', color='#ff7f0e', alpha=0.8)
    
    # # Add On-Demand baseline as horizontal dotted line
    # ax.axhline(y=ondemand_latency, color='#1f77b4', linestyle='--', linewidth=2.5, label='On-Demand Baseline')
    
    # # Add value labels on bars
    # for bar in bars1:
    #     height = bar.get_height()
    #     ax.text(bar.get_x() + bar.get_width()/2., height,
    #            f'{height:.1f}',
    #            ha='center', va='bottom', fontsize=14)
    
    # ax.set_ylabel('End-to-End Latency (ms)', fontsize=14)
    # ax.set_xlabel('Max Pregenerated Pairs per core', fontsize=14)
    # ax.set_title(f'E2E Latency Comparison: CGP(1-5 pregenerations) vs On-Demand Baseline\n({num_layers} layers, {total_requests} requests)', 
    #              fontsize=14, pad=15)
    # ax.set_xticks(x)
    # ax.set_xticklabels(ace_configs)
    # ax.legend(loc='upper right', fontsize=12)
    # ax.grid(True, alpha=0.3, axis='y')
    # ax.set_axisbelow(True)
    
    # plt.tight_layout()
    # plt.savefig('plots/real_comparison.png', dpi=600, bbox_inches='tight')
    # print("Saved plots/real_comparison.png")
    # plt.close()