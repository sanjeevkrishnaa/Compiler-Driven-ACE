from parallel_core import *

if __name__ == "__main__":
    # Create directories
    os.makedirs('plots', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    os.makedirs('log', exist_ok=True)
    os.makedirs('test', exist_ok=True)
    
    # Configuration - Test different layer counts
    layer_scenarios = [25, 50, 75, 100]  # Different numbers of layers to test
    max_requests_per_layer = 6  # Up to 6 parallel requests with disjoint cores
    pregeneration_time_ms = 5.3  # Fixed pre-generation time
    request_duration_ms = 50  # Maximum duration for each request
    seed = 48
    # Store all results organized by layer count
    results_by_layers = {layers: [] for layers in layer_scenarios}
    scenario = "random" # "random", "structured","random_single","structured_single"
    
    # Run experiments for each layer scenario
    for num_layers in layer_scenarios:
        print(f"\n{'#'*80}")
        print(f"TESTING WITH {num_layers} LAYERS")
        print(f"{'#'*80}\n")
        
        # Generate or load layered requests for this scenario

        if scenario == "random":
            request_file = f"test/parallel_layered_random_requests_{num_layers}.json"
            
            if os.path.exists(request_file):
                print(f"Loading layered requests from {request_file}...")
                with open(request_file, "r") as f:
                    layered_requests = json.load(f)
            else:
                print(f"Generating structured layered requests for {num_layers} layers...")
                layered_requests = generate_layered_requests(
                    num_layers=num_layers,
                    max_requests_per_layer=max_requests_per_layer,
                    memo_size=1,
                    fidelity=0.01,
                    entanglement_number=1,
                    seed=seed
                )
                
                # Save for reproducibility
                with open(request_file, "w") as f:
                    json.dump(layered_requests, f, indent=2)
                print(f"Saved layered requests to {request_file}")
        elif scenario == "structured":  # structured
            request_file = f"test/parallel_layered_requests_{num_layers}.json"

            if os.path.exists(request_file):
                print(f"Loading layered requests from {request_file}...")
                with open(request_file, "r") as f:
                    layered_requests = json.load(f)
            else:
                print(f"Generating structured layered requests for {num_layers} layers...")
                layered_requests = generate_structured_layered_requests(
                    num_layers=num_layers,
                    memo_size=1,
                    fidelity=0.01,
                    entanglement_number=1,
                    seed=seed
                )
                
                # Save for reproducibility
                with open(request_file, "w") as f:
                    json.dump(layered_requests, f, indent=2)
                print(f"Saved layered requests to {request_file}")
        elif scenario == "random_single":
            request_file = f"test/parallel_layered_random_single_requests_{num_layers}.json"

            if os.path.exists(request_file):
                print(f"Loading layered requests from {request_file}...")
                with open(request_file, "r") as f:
                    layered_requests = json.load(f)
            else:
                print(f"Generating structured layered requests for {num_layers} layers...")
                layered_requests = generate_layered_requests_sequential(
                    num_layers=num_layers,
                    memo_size=1,
                    fidelity=0.01,
                    entanglement_number=1,
                    seed=seed
                )
                
                # Save for reproducibility
                with open(request_file, "w") as f:
                    json.dump(layered_requests, f, indent=2)
                print(f"Saved layered requests to {request_file}")
        elif scenario == "structured_single":
            request_file = f"test/parallel_layered_structured_single_requests_{num_layers}.json"

            if os.path.exists(request_file):
                print(f"Loading layered requests from {request_file}...")
                with open(request_file, "r") as f:
                    layered_requests = json.load(f)
            else:
                print(f"Generating structured layered requests for {num_layers} layers...")
                layered_requests = generate_structured_layered_requests_sequential(
                    num_layers=num_layers,
                    memo_size=1,
                    fidelity=0.01,
                    entanglement_number=1,
                    seed=seed
                )
                
                # Save for reproducibility
                with open(request_file, "w") as f:
                    json.dump(layered_requests, f, indent=2)
                print(f"Saved layered requests to {request_file}")
        elif scenario == "hotspot":
            request_file = f"test/parallel_layered_hotspot_requests_{num_layers}.json"

            if os.path.exists(request_file):
                print(f"Loading layered requests from {request_file}...")
                with open(request_file, "r") as f:
                    layered_requests = json.load(f)
            else:
                print(f"Generating hotspot layered requests for {num_layers} layers...")
                layered_requests = generate_hotspot_layered_requests(
                    num_layers=num_layers,
                    max_requests_per_layer=max_requests_per_layer,
                    memo_size=1,
                    fidelity=0.01,
                    entanglement_number=1,
                    seed=seed
                )

                # Save for reproducibility
                with open(request_file, "w") as f:
                    json.dump(layered_requests, f, indent=2)
                print(f"Saved layered requests to {request_file}")
        elif scenario == "hotspot_single":
            request_file = f"test/parallel_layered_hotspot_single_requests_{num_layers}.json"

            if os.path.exists(request_file):
                print(f"Loading layered requests from {request_file}...")
                with open(request_file, "r") as f:
                    layered_requests = json.load(f)
            else:
                print(f"Generating hotspot single layered requests for {num_layers} layers...")
                layered_requests = generate_hotspot_layered_requests_sequential(
                    num_layers=num_layers,
                    memo_size=1,
                    fidelity=0.01,
                    entanglement_number=1,
                    seed=seed
                )

                # Save for reproducibility
                with open(request_file, "w") as f:
                    json.dump(layered_requests, f, indent=2)
                print(f"Saved layered requests to {request_file}")
        
        total_requests = sum(len(layer) for layer in layered_requests)
        print(f"\nExperiment configuration:")
        print(f"  Total layers: {len(layered_requests)}")
        print(f"  Total requests: {total_requests}")
        
        # Experiment 1: CGP-0 (on-demand)
        exp_label = f"Parallel_CGP0_{num_layers}layers"
        print(f"\n--- Running {exp_label} ---")
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
        result['num_layers'] = num_layers
        result['config'] = 'On-Demand'
        result['update_prob'] = False
        results_by_layers[num_layers].append(result)

        # Experiment 2: CGP-4 without adaptation
        exp_label = f"Parallel_CGP4_NoUpdate_{num_layers}layers"
        print(f"\n--- Running {exp_label} ---")
        result = run_parallel_experiment(
            config_file='config/grid_4x4_ace_4.json',
            update_prob_setting=False,
            purify_setting=False,
            layered_requests=layered_requests,
            pregeneration_time_ms=pregeneration_time_ms,
            request_duration_ms=request_duration_ms,
            experiment_label=exp_label
        )
        result['label'] = exp_label
        result['num_layers'] = num_layers
        result['config'] = 'CGP (Max 4 qubit)'
        result['update_prob'] = False
        results_by_layers[num_layers].append(result)

        # Save CSV data for this layer scenario
        print(f"\n--- Saving CSV data for {num_layers} layers ---")
        request_info_map = {}
        for layer in layered_requests:
            for req in layer:
                request_info_map[req[0]] = (req[1], req[2])

        for result in results_by_layers[num_layers]:
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

    # Create grouped bar chart
    print(f"\n{'='*80}")
    print("CREATING COMPARISON PLOTS")
    print(f"{'='*80}\n")

    # Prepare data for bar chart
    configs = ['On-Demand', 'CGP (Max 4 qubit)']
    colors = ['#1f77b4', '#ff7f0e']  # Blue, Orange

    # Extract E2E latencies for each configuration and layer count
    data_for_plot = {config: [] for config in configs}

    for num_layers in layer_scenarios:
        for result in results_by_layers[num_layers]:
            config = result['config']
            e2e_latency = result['stats']['end_to_end_latency_ms']
            data_for_plot[config].append(e2e_latency)

    # Create the grouped bar chart
    fig, ax = plt.subplots(figsize=(10, 8))

    x = np.arange(len(layer_scenarios))  # Label locations
    width = 0.4  # Width of bars
    multiplier = 0

    for config, color in zip(configs, colors):
        offset = width * multiplier
        rects = ax.bar(x + offset, data_for_plot[config], width, label=config, color=color, alpha=0.8)

        # Add value labels on top of bars with increased font size
        for rect in rects:
            height = rect.get_height()
            ax.text(rect.get_x() + rect.get_width()/2., height,
                   f'{height:.1f}',
                   ha='center', va='bottom', fontsize=14)

        multiplier += 1

    # Customize the plot
    ax.set_xlabel('Number of Layers', fontsize=14)
    ax.set_ylabel('End-to-End Latency (ms)', fontsize=14)
    ax.set_title(f'End-to-End Latency Comparison Across Layer Scenarios\n(Max {max_requests_per_layer} requests/layer)', 
                 fontsize=15, pad=20)
    ax.set_xticks(x + width / 2)
    ax.set_xticklabels([f'{n} Layers' for n in layer_scenarios], fontsize=12)
    ax.legend(fontsize=12, loc='upper left')
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(f"plots/parallel_e2e_latency_comparison_{scenario}_2pc.png", dpi=600, bbox_inches='tight')
    print(f"Saved plots/parallel_e2e_latency_comparison_{scenario}_2pc.png")
    plt.close()
    
    # Create a summary table
    print(f"\n{'='*80}")
    print("SUMMARY TABLE: END-TO-END LATENCY (ms)")
    print(f"{'='*80}")
    print(f"{'Configuration':<25} {'25 Layers':<15} {'50 Layers':<15} {'75 Layers':<15} {'100 Layers':<15}")
    print("-" * 95)
    
    for config in configs:
        latencies = data_for_plot[config]
        print(f"{config:<25} {latencies[0]:<15.2f} {latencies[1]:<15.2f} {latencies[2]:<15.2f} {latencies[3]:<15.2f}")
    
    print(f"{'='*80}\n")
    
    # Calculate and display performance improvements
    print(f"\n{'='*80}")
    print("PERFORMANCE ANALYSIS")
    print(f"{'='*80}\n")
    
    for idx, num_layers in enumerate(layer_scenarios):
        ondemand_latency = data_for_plot['On-Demand'][idx]
        ace4_no_update = data_for_plot['CGP (Max 4 qubit)'][idx]
        #ace4_with_update = data_for_plot['ACE (Max 4 qubit, With Update)'][idx]

        improvement_no_update = ((ondemand_latency - ace4_no_update) / ondemand_latency) * 100
        #improvement_with_update = ((ondemand_latency - ace4_with_update) / ondemand_latency) * 100

        print(f"{num_layers} Layers:")
        print(f"  On-Demand baseline: {ondemand_latency:.2f} ms")
        print(f"  CGP : {ace4_no_update:.2f} ms ({improvement_no_update:+.1f}%)")
        #print(f"  ACE (With Update): {ace4_with_update:.2f} ms ({improvement_with_update:+.1f}%)")
        print()
    
    print(f"{'='*80}\n")
    print("Experiment complete!")
