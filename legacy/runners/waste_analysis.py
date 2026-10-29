import os
import sys
import json
from parallel_core import run_parallel_experiment , generate_hotspot_layered_requests

def run_cgp_waste_analysis():

    configurations = [
        # {"label": "CGP-0", "config": "config/grid_4x4_ace_0.json", "update": False},
        {"label": "CGP-1", "config": "config/grid_4x4_ace_1.json", "update": False},
        {"label": "CGP-2", "config": "config/grid_4x4_ace_2.json", "update": False},
        {"label": "CGP-3", "config": "config/grid_4x4_ace_3.json", "update": False},
        {"label": "CGP-4", "config": "config/grid_4x4_ace_4.json", "update": False},
        {"label": "CGP-5", "config": "config/grid_4x4_ace_5.json", "update": False},
        {"label": "CGP-1a", "config": "config/grid_4x4_ace_1.json", "update": True},
        {"label": "CGP-2a", "config": "config/grid_4x4_ace_2.json", "update": True},
        {"label": "CGP-3a", "config": "config/grid_4x4_ace_3.json", "update": True},
        {"label": "CGP-4a", "config": "config/grid_4x4_ace_4.json", "update": True},
        {"label": "CGP-5a", "config": "config/grid_4x4_ace_5.json", "update": True},
    ]
    
    # request_file = "test/fixed_qubit_displacement_1.json"
    
    # if not os.path.exists(request_file):
    #     print(f"ERROR: {request_file} not found!")
    #     sys.exit(1)
    
    # print(f"Loading requests from {request_file}...")
    # with open(request_file, "r") as f:
        # layered_requests = json.load(f)

    # Generate hotspot traffic pattern instead of loading from file
    num_layers = 150
    max_requests_per_layer = 2  # Maximum disjoint requests per layer
    memo_size = 1
    fidelity = 0.01
    entanglement_number = 1
    seed = 42
    
    print("Generating hotspot layered request pattern...")
    layered_requests = generate_hotspot_layered_requests(
        num_layers=num_layers,
        max_requests_per_layer=max_requests_per_layer,
        memo_size=memo_size,
        fidelity=fidelity,
        entanglement_number=entanglement_number,
        seed=seed
    )
    
    total_requests = sum(len(layer) for layer in layered_requests)
    num_layers = len(layered_requests)
    
    pregeneration_time_ms = 10 # 5.3
    request_duration_ms = 100
    update_prob_setting = True
    purify_setting = False
    
    print("="*80)
    print("EPR WASTE ANALYSIS - CGP CONFIGURATIONS 0-5 WITH LEARNING")
    print("="*80)
    # print(f"Request file: {request_file}")
    print(f"Total layers: {num_layers}")
    print(f"Total requests: {total_requests}")
    print(f"Pre-generation time: {pregeneration_time_ms} ms")
    print(f"Request duration: {request_duration_ms} ms") 
    print(f"Learning enabled: {update_prob_setting}")
    print(f"Purification: {purify_setting}")
    print("="*80)
    
    # Storage for all results
    all_epr_data = {}
    
    # Run experiments for each configuration
    for config in configurations:
        print(f"\n{'='*60}")
        print(f"RUNNING EXPERIMENT: {config['label']}")
        print(f"Configuration: {config['config']}")
        print(f"{'='*60}")
        
        # Run the experiment
        results = run_parallel_experiment(
            config_file=config['config'],
            update_prob_setting=config['update'],
            purify_setting=purify_setting,
            layered_requests=layered_requests,
            pregeneration_time_ms=pregeneration_time_ms,
            request_duration_ms=request_duration_ms,
            experiment_label=config['label']
        )
        
        # Extract EPR data from each node using the request_manager's name_to_apps
        name_to_apps = results['request_manager'].name_to_apps
        
        # Collect EPR usage data like in main4.py
        epr_data = {}
        total_generated = 0
        total_used = 0 
        total_unused = 0
        
        print(f"\n--- EPR Usage Data for {config['label']} ---")
        for router_name, app in name_to_apps.items():
            generated = app.node.adaptive_continuous.num_generated_entanglement_pairs
            used = app.node.adaptive_continuous.num_used_entanglement_pairs
            unused = app.node.adaptive_continuous.num_unused_entanglement_pairs
            
            utilization = (used / generated * 100) if generated > 0 else 0
            waste = (unused / generated * 100) if generated > 0 else 0
            
            epr_data[router_name] = {
                'generated': generated,
                'used': used,
                'unused': unused,
                'utilization_percent': utilization,
                'waste_percent': waste
            }
            
            total_generated += generated
            total_used += used
            total_unused += unused
            
            print(f"{router_name}: Generated={generated}, Used={used}, Unused={unused}, "
                  f"Utilization={utilization:.1f}%, Waste={waste:.1f}%")
        
        # Calculate totals
        total_utilization = (total_used / total_generated * 100) if total_generated > 0 else 0
        total_waste = (total_unused / total_generated * 100) if total_generated > 0 else 0
        
        print(f"\nTOTAL: Generated={total_generated}, Used={total_used}, Unused={total_unused}")
        print(f"OVERALL: Utilization={total_utilization:.1f}%, Waste={total_waste:.1f}%")
        
        # Store results
        all_epr_data[config['label']] = {
            'per_node': epr_data,
            'totals': {
                'generated': total_generated,
                'used': total_used,
                'unused': total_unused,
                'utilization_percent': total_utilization,
                'waste_percent': total_waste
            }
        }
    
    # Print final summary
    print(f"\n{'='*80}")
    print("FINAL WASTE ANALYSIS SUMMARY")
    print(f"{'='*80}")
    for config_label, data in all_epr_data.items():
        totals = data['totals']
        print(f"{config_label:10s}: Utilization={totals['utilization_percent']:5.1f}%, "
              f"Waste={totals['waste_percent']:5.1f}%")
    print(f"{'='*80}")
    
    return all_epr_data

if __name__ == "__main__":
    try:
        epr_data = run_cgp_waste_analysis()
        print("\nWaste analysis completed successfully!")
    except Exception as e:
        print(f"Error during waste analysis: {e}")
        sys.exit(1)
