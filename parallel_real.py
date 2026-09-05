from parallel_core import *


if __name__ == "__main__":
    # Create directories
    os.makedirs('plots', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    os.makedirs('log', exist_ok=True)
    
    # Load requests from file
    request_file = "/home/btp_comm/qnoc-stress-testing/ACE/real_benchmarks/traffic_files/cuccaro_fixed_1x2_q8_s1_traffic.json"
    
    if not os.path.exists(request_file):
        print(f"ERROR: {request_file} not found!")
        exit(1)
    
    print(f"Loading requests from {request_file}...")
    with open(request_file, "r") as f:
        layered_requests = json.load(f)["layers"]
    
    for i in range(min(8, len(layered_requests))):
        print(layered_requests[i])
        
    total_requests = sum(len(layer) for layer in layered_requests)
    num_layers = len(layered_requests)
    
    print(f"\nLoaded configuration:")
    print(f"  Total layers: {num_layers}")
    print(f"  Total requests: {total_requests}")
    print(f"  Requests per layer: {[len(layer) for layer in layered_requests]}")
    
    # Configuration
    pregeneration_time_ms = 5.3
    request_duration_ms = 100
    
    # Store results
    all_results = []
    
    # Experiment 1: ACE-0 (on-demand)
    exp_label = f"real_ACE0"
    print(f"\n{'='*80}")
    print(f"Running {exp_label}")
    print(f"{'='*80}\n")
    result = run_parallel_experiment(
        config_file='config/grid_4x4_ace_0.json',
        update_prob_setting=False,
        purify_setting=False,
        layered_requests=layered_requests,
        pregeneration_time_ms=pregeneration_time_ms,
        request_duration_ms=request_duration_ms,
        experiment_label=exp_label
    )
    result['label'] = exp_label
    result['config'] = 'On-Demand'
    result['update_prob'] = None
    all_results.append(result)
    
    # Experiments 2-11: CGP-1 through CGP-5 (without update)
    for ace_num in range(1, 6):
        # Without update
        exp_label = f"real_CGP{ace_num}_NoUpdate"
        print(f"\n{'='*80}")
        print(f"Running {exp_label}")
        print(f"{'='*80}\n")
        result = run_parallel_experiment(
            config_file=f'config/grid_4x4_ace_{ace_num}.json',
            update_prob_setting=False,
            purify_setting=False,
            layered_requests=layered_requests,
            pregeneration_time_ms=pregeneration_time_ms,
            request_duration_ms=request_duration_ms,
            experiment_label=exp_label
        )
        result['label'] = exp_label
        result['config'] = f'CGP-{ace_num} (No Update)'
        result['update_prob'] = False
        all_results.append(result)

        # With update (commented out)
        # exp_label = f"real_CGP{ace_num}_WithUpdate"
        # print(f"\n{'='*80}")
        # print(f"Running {exp_label}")
        # print(f"{'='*80}\n")
        # result = run_parallel_experiment(
        #     config_file=f'config/grid_4x4_ace_{ace_num}.json',
        #     update_prob_setting=True,
        #     purify_setting=False,
        #     layered_requests=layered_requests,
        #     pregeneration_time_ms=pregeneration_time_ms,
        #     request_duration_ms=request_duration_ms,
        #     experiment_label=exp_label
        # )
        # result['label'] = exp_label
        # result['config'] = f'CGP-{ace_num} (With Update)'
        # result['update_prob'] = True
        # all_results.append(result)

    # Save CSV data
    print(f"\n{'='*80}")
    print("SAVING CSV DATA")
    print(f"{'='*80}\n")
    
    # Create request info map
    request_info_map = {}
    for layer in layered_requests:
        for req in layer:
            request_info_map[req[0]] = (req[1], req[2])
    
    for result in all_results:
        csv_filename = f"data/{result['label']}.csv"
        with open(csv_filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Request_ID', 'Source', 'Destination', 'Latency_ms', 'Fidelity'])
            
            for reservation, latency in sorted(result['latency_dict'].items(), key=lambda x: x[0].identity):
                req_id = reservation.identity
                src, dst = request_info_map.get(req_id, ('Unknown', 'Unknown'))
                fidelity = result['fidelity_dict'][reservation][0] if reservation in result['fidelity_dict'] else 0
                latency_ms = latency / MILLISECOND
                writer.writerow([req_id, src, dst, f"{latency_ms:.4f}", f"{fidelity:.6f}"])
        print(f"Saved {csv_filename}")
    
    # Create comparison bar chart
    print(f"\n{'='*80}")
    print("CREATING COMPARISON PLOT")
    print(f"{'='*80}\n")
    
    # Separate On-Demand baseline from CGP experiments
    ondemand_latency = all_results[0]['stats']['end_to_end_latency_ms']
    ace_results = all_results[1:]  # CGP-1 through CGP-5
    
    # Prepare data for grouped bars
    ace_configs = []
    no_update_latencies = []
    
    for i in range(0, len(ace_results)):
        no_update = ace_results[i]

        ace_num = i + 1
        ace_configs.append(f'{ace_num}')
        no_update_latencies.append(no_update['stats']['end_to_end_latency_ms'])
    
    # Create grouped bar chart
    fig, ax = plt.subplots(figsize=(10, 8))
    
    x = np.arange(len(ace_configs))
    width = 0.4
    
    bars1 = ax.bar(x, no_update_latencies, width, label='No Update', color='#ff7f0e', alpha=0.8)
    
    # Add On-Demand baseline as horizontal dotted line
    ax.axhline(y=ondemand_latency, color='#1f77b4', linestyle='--', linewidth=2.5, label='On-Demand Baseline')
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:.1f}',
               ha='center', va='bottom', fontsize=14)
    
    ax.set_ylabel('End-to-End Latency (ms)', fontsize=14)
    ax.set_xlabel('Max Pregenerated Pairs per core', fontsize=14)
    ax.set_title(f'E2E Latency Comparison: CGP(1-5 pregenerations) vs On-Demand Baseline\n({num_layers} layers, {total_requests} requests)', 
                 fontsize=14, pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(ace_configs)
    ax.legend(loc='upper right', fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_axisbelow(True)
    
    plt.tight_layout()
    plt.savefig('plots/real_comparison.png', dpi=600, bbox_inches='tight')
    print("Saved plots/real_comparison.png")
    plt.close()