from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt

from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
import sequence.utils.log as log
from request_app import RequestAppTimeToServe
from router_net_topo_adaptive import RouterNetTopoAdaptive
from traffic import TrafficMatrix

import random
from itertools import accumulate
from bisect import bisect_left

# Assuming SECOND is a constant, e.g., SECOND = 1_000_000_000_000
SECOND = 10**12

def get_request_queue_mesh(request_time: float, total_time: float, delta: float, memo_size: int, fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    '''
    Generates a queue of requests for a 4x4 mesh network.

    Args:
        request_time (float): The time duration for each request (in seconds).
        total_time (float): The total simulation time for all requests (in seconds).
        delta (float): Small offset to start the first request (in seconds).
        memo_size (int): The memory size for each request.
        fidelity (float): The fidelity requirement for each request.
        entanglement_number (int): The number of entanglements needed.
        seed (int): The random seed for reproducibility.
        
    Return:
        list: A list of requests, where each request is a tuple:
              (id, src_name, dst_name, start_time_ps, end_time_ps, memo_size, fidelity, entanglement_number)
    '''
    nodes = [(i, j) for i in range(4) for j in range(4)]
    random.seed(seed)
    
    request_id = 0
    request_queue = []
    num_requests = int(total_time // request_time)

    for i in range(num_requests):
        src_coord, dst_coord = random.sample(nodes, 2)
        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'

        start_time = i * request_time + delta
        end_time = (i + 1) * request_time

        request = (
            request_id, 
            src_name, 
            dst_name, 
            round(start_time * SECOND), 
            round(end_time * SECOND), 
            memo_size, 
            fidelity, 
            entanglement_number
        )
        request_queue.append(request)
        request_id += 1
        
    return request_queue

def run_experiment(config_file: str, update_prob_setting: bool, request_queue: list, experiment_label: str):
    """
    Runs a single simulation experiment with a given configuration.
    
    Args:
        config_file (str): Path to the network configuration JSON file.
        update_prob_setting (bool): The value for router.adaptive_continuous.update_prob.
        request_queue (list): The list of requests to schedule.
        experiment_label (str): A label for the log file.

    Returns:
        tuple: A tuple containing two dictionaries: (time_to_serve_dict, fidelity_dict).
    """
    log_filename = f'log/log_{experiment_label.replace(" ", "_")}'

    network_topo = RouterNetTopoAdaptive(config_file)
    tl = network_topo.get_timeline()
    tl.seed(0)

    # Set up logging for the experiment
    log.set_logger(__name__, tl, log_filename)
    log.set_logger_level('INFO')
    modules = ['adaptive_continuous', 'request_app', 'swapping', 'network_manager', 'resource_manager', 'main', 'rule_manager', 'generation', 'swapping', 'purification','reservation']
    for module in modules:
        log.track_module(module)

    # Configure routers and applications
    name_to_apps = {}
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        app = RequestAppTimeToServe(router)
        name_to_apps[router.name] = app
        # Configure adaptive protocol if it exists on the router
        if hasattr(router, 'adaptive_continuous') and update_prob_setting is not None:
            router.adaptive_continuous.update_prob = update_prob_setting

    # Schedule all requests
    for request in request_queue:
        id, src_name, dst_name, start_time, end_time, memo_size, fidelity, entanglement_number = request
        app = name_to_apps[src_name]
        app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, id)

    # Run the simulation
    tl.init()
    tl.run()

    # Collect results
    time_to_serve_dict = defaultdict(float)
    fidelity_dict = defaultdict(list)
    for _, app in name_to_apps.items():
        time_to_serve_dict.update(app.time_to_serve)
        fidelity_dict.update(app.entanglement_fidelities)

    # Print summary for the experiment
    print(f"--- Results for {experiment_label} ---")
    for reservation, time_to_serve in sorted(time_to_serve_dict.items(), key=lambda item: item[0].id):
        fidelity = fidelity_dict[reservation][0]
        print(f'Req ID={reservation.id}, TTS={time_to_serve / MILLISECOND:.2f} ms, Fidelity={fidelity:.4f}')
    
    return time_to_serve_dict, fidelity_dict


if __name__ == '__main__':
    # 1. Create a single request series to be used for all experiments
    print("Generating a shared request queue for all experiments...")
    shared_requests = get_request_queue_mesh(
        request_time=0.1, total_time=200, delta=0.01, 
        memo_size=1, fidelity=0.01, entanglement_number=1, seed=42
    )
    print(f"Generated {len(shared_requests)} requests.")

    # 2. Define the three experiments
    experiments = [
        {
            "label": "ACE=0 (No Proactive Entanglement)",
            "config": "config/grid_4x4_ace_0.json",
            "update_prob": None  # Not applicable
        },
        {
            "label": "ACE=5 (No Adaptation)",
            "config": "config/grid_4x4_ace_5.json",
            "update_prob": False
        },
        {
            "label": "ACE=5 (With Adaptation)",
            "config": "config/grid_4x4_ace_5.json",
            "update_prob": True
        }
    ]

    all_results = {}
    # 3. Run all experiments
    for exp in experiments:
        print(f"\nRunning Experiment: {exp['label']}")
        tts, fidelity = run_experiment(exp['config'], exp['update_prob'], shared_requests, exp['label'])
        all_results[exp['label']] = {'tts': tts, 'fidelity': fidelity}

    # 4. Plot the results
    print("\nPlotting results...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 12), sharex=True)
    
    # Plot Time-to-Serve (TTS)
    for label, results in all_results.items():
        tts_data = results['tts']
        if not tts_data: continue
        # Sort data by request ID to ensure correct plotting order
        sorted_reservations = sorted(tts_data.keys(), key=lambda r: r.id)
        x_values = [r.id for r in sorted_reservations]
        y_values = [tts_data[r] / MILLISECOND for r in sorted_reservations]
        ax1.plot(x_values, y_values, marker='o', linestyle='--', markersize=4, label=label)

    ax1.set_title('Time to Serve (TTS) per Request')
    ax1.set_ylabel('Time to Serve (ms)')
    ax1.legend()
    ax1.grid(True)

    # Plot Fidelity
    for label, results in all_results.items():
        fidelity_data = results['fidelity']
        if not fidelity_data: continue
        # Sort data by request ID
        sorted_reservations = sorted(fidelity_data.keys(), key=lambda r: r.id)
        x_values = [r.id for r in sorted_reservations]
        y_values = [fidelity_data[r][0] for r in sorted_reservations] # Fidelity is stored in a list
        ax2.plot(x_values, y_values, marker='x', linestyle=':', markersize=5, label=label)
    
    ax2.set_title('Entanglement Fidelity per Successful Request')
    ax2.set_xlabel('Request ID')
    ax2.set_ylabel('Fidelity')
    ax2.legend()
    ax2.grid(True)
    
    plt.tight_layout()
    plt.show()