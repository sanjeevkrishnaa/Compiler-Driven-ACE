from collections import defaultdict
from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
import sequence.utils.log as log
from request_app import RequestAppLatency
from router_net_topo_adaptive import RouterNetTopoAdaptive
import matplotlib.pyplot as plt
import numpy as np
import csv
import os
import json
import random

SECOND = int(1e12)

def get_request_queue_mesh(request_time: int, total_time: int, delta: int, memo_size: int, fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    '''
    Generates a queue of requests for a 4x4 mesh network.

    Args:
        request_time (int): The time period for each request (in seconds).
        total_time (int): The total simulation time for all requests (in seconds).
        memo_size (int): The memory size for each request.
        fidelity (float): The fidelity requirement for each request.
        entanglement_number (int): The number of entanglements needed.
        seed (int): The random seed for reproducibility.
        
    Return:
        list: A list of requests, where each request is a tuple:
              (id, src_name, dst_name, start_time_ps, end_time_ps, memo_size, fidelity, entanglement_number)
    '''
    # Define the 4x4 grid of nodes
    nodes = [(i, j) for i in range(4) for j in range(4)]
    
    random.seed(seed)
    
    request_id = 0
    request_queue = []

    num_pairs = int(total_time // request_time)

    for i in range(num_pairs):
        src_coord, dst_coord = random.sample(nodes, 2)
        src_coord, dst_coord = random.sample(nodes, 2)

        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'
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

def get_request_queue_mesh_first_last(request_time: int, total_time: int, delta: int, memo_size: int, fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    '''
    Generates a queue of requests for a 4x4 mesh network.

    Args:
        request_time (int): The time period for each request (in seconds).
        total_time (int): The total simulation time for all requests (in seconds).
        memo_size (int): The memory size for each request.
        fidelity (float): The fidelity requirement for each request.
        entanglement_number (int): The number of entanglements needed.
        seed (int): The random seed for reproducibility.
        
    Return:
        list: A list of requests, where each request is a tuple:
              (id, src_name, dst_name, start_time_ps, end_time_ps, memo_size, fidelity, entanglement_number)
    '''
    first_col_nodes = [(i, 0) for i in range(4)]
    last_col_nodes = [(i, 3) for i in range(4)]
    
    random.seed(seed)
    
    request_id = 0
    request_queue = []

    num_pairs = int(total_time // request_time)

    for i in range(num_pairs):
        if random.randint(0, 1) == 0:
            # Case 1: First column to Last column
            src_coord = random.choice(first_col_nodes)
            dst_coord = random.choice(last_col_nodes)
        else:
            # Case 2: Last column to First column (vice versa)
            src_coord = random.choice(last_col_nodes)
            dst_coord = random.choice(first_col_nodes)

        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'

        start_time = i*request_time + delta
        end_time =  (i+1) * request_time

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

def run_experiment(config_file: str, update_prob_setting: bool, purify_setting: bool, request_queue: list, experiment_label: str):
    """
    Runs a single simulation experiment with a given configuration.
    
    Args:
        config_file (str): Path to the network configuration JSON file.
        update_prob_setting (bool): Whether to enable adaptive demand bonus (sets demand_bonus to 3.0 if True, 0.0 if False).
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
    # log.set_logger(__name__, tl, log_filename)
    # log.set_logger_level('INFO')
    # modules = ['adaptive_continuous', 'request_app', 'swapping', 'network_manager', 'resource_manager', 'main', 'rule_manager', 'generation', 'swapping', 'purification','reservation']
    # for module in modules:
    #     log.track_module(module)

    # Configure routers and applications
    name_to_apps = {}
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        app = RequestAppLatency(router)
        name_to_apps[router.name] = app
        router.adaptive_continuous.has_empty_neighbour = True
        router.adaptive_continuous.demand_driven = update_prob_setting
        router.adaptive_continuous.strategy = "freshest"
        router.resource_manager.purify = purify_setting
    
    # Schedule all requests
    for request in request_queue:
        id, src_name, dst_name, start_time, end_time, memo_size, fidelity, entanglement_number = request
        app = name_to_apps[src_name]
        app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, id)

    # Run the simulation
    tl.init()
    tl.run()

    # Collect results
    latency_dict = defaultdict(float)
    fidelity_dict = defaultdict(list)
    for _, app in name_to_apps.items():
        latency_dict |= app.latency
        fidelity_dict |= app.entanglement_fidelities
        print(f"{app.node.name} generated: {app.node.adaptive_continuous.num_generated_entanglement_pairs}, used: {app.node.adaptive_continuous.num_used_entanglement_pairs}, unused: {app.node.adaptive_continuous.num_unused_entanglement_pairs}")

    # Print summary for the experiment
    print(f"--- Results for {experiment_label} ---")
    for reservation, latency in sorted(latency_dict.items()):
        fidelity = fidelity_dict[reservation][0]
        print(f'Req ID={reservation.identity}, Latency={latency / MILLISECOND:.2f} ms, Fidelity={fidelity:.4f}')
    
    return latency_dict, fidelity_dict



if __name__ == "__main__":
    # 1. Create a single request series to be used for all experiments

    # check if test/request_queue_first_last.txt exists
    shared_requests = None
    type = "first_last"
    
    if type == "first_last":
        if os.path.exists("test/request_queue_first_last.txt"):
            print("Loading shared request queue from file...")
            with open("test/request_queue_first_last.txt", "r") as f:
                shared_requests = json.load(f)
        else:
            print("Generating a shared request queue for all experiments...")
            shared_requests = get_request_queue_mesh_first_last(
                request_time=0.05, total_time=50, delta=0.01,
                memo_size=1, fidelity=0.01, entanglement_number=1, seed=42
            )
            # Save to file for future use
            with open("test/request_queue_first_last.txt", "w") as f:
                json.dump(shared_requests, f)
    else:  # creates random stuff
        if os.path.exists("test/request_queue.txt"):
            print("Loading shared request queue from file...")
            with open("test/request_queue.txt", "r") as f:
                shared_requests = json.load(f)
        else:
            print("Generating a shared request queue for all experiments...")
            shared_requests = get_request_queue_mesh(
                request_time=0.05, total_time=50, delta=0.01,
                memo_size=1, fidelity=0.01, entanglement_number=1, seed=42
            )
            # Save to file for future use
            with open("test/request_queue.txt", "w") as f:
                json.dump(shared_requests, f)
    

    
    print(f"Generated {len(shared_requests)} requests.")



    # 2. Define the three experiments
    experiments = [
        {
            "label": "On Demand",
            "config": "config/grid_4x4_ace_0.json",
            "update_prob": False,  # Not applicable, protocol doesn't run
            "purify_setting": False
        },
        # {
        #     "label": "CGP",
        #     "config": "config/grid_4x4_ace_4.json",
        #     "update_prob": False,
        #     "purify_setting": False
        # },
        # {
        #     "label": "CGP (with Learning)",
        #     "config": "config/grid_4x4_ace_4.json",
        #     "update_prob": True,
        #     "purify_setting": False
        # } 
    ]

    all_results = {}

    # 3. Run all experiments
    for exp in experiments:
        print(f"\nRunning Experiment: {exp['label']}")
        latency, fidelity = run_experiment(exp['config'], exp['update_prob'], exp['purify_setting'], shared_requests, exp['label'])
        all_results[exp['label']] = {'latency': latency, 'fidelity': fidelity}

    # print avg results
    for label, results in all_results.items():
        fidelity_data = results['fidelity']
        avg_fidelity = sum(f[0] for f in fidelity_data.values()) / len(fidelity_data) if fidelity_data else 0
        print(f"\n--- Average Results for {label} ---")
        print(f"Average Fidelity: {avg_fidelity:.4f}")

    # Save data to CSV files
    print("\nSaving data to CSV files...")
    os.makedirs('data', exist_ok=True)

    # Create a mapping from request ID to source and destination
    # request_info_map = {}
    # for request in shared_requests:
    #     req_id, src_name, dst_name, start_time, end_time, memo_size, fidelity, entanglement_number = request
    #     request_info_map[req_id] = {'src': src_name, 'dst': dst_name}

    # for label, results in all_results.items():
    #     fidelity_data = results['fidelity']

    #     # Create a safe filename from the label
    #     safe_label = label.replace(" ", "_").replace("(", "").replace(")", "").replace("=", "")
    #     csv_filename = f'data/{safe_label}.csv'

    #     with open(csv_filename, 'w', newline='') as csvfile:
    #         writer = csv.writer(csvfile)
    #         writer.writerow(['Request_ID', 'Source', 'Destination', 'Fidelity'])

    #         # Sort by request ID
    #         sorted_reservations = sorted(fidelity_data.keys(), key=lambda r: r.identity)
    #         for reservation in sorted_reservations:
    #             req_id = reservation.identity
    #             src_name = request_info_map[req_id]['src'] if req_id in request_info_map else 'N/A'
    #             dst_name = request_info_map[req_id]['dst'] if req_id in request_info_map else 'N/A'
    #             fidelity = fidelity_data[reservation][0] if reservation in fidelity_data else 0
    #             writer.writerow([req_id, src_name, dst_name, f'{fidelity:.6f}'])

    #     print(f"Saved data to {csv_filename}")

    # # 4. Plot the results
    # print("\nPlotting results...")

    # # Commented out the old code for subplots
    # # fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5))
    # #
    # # === LATENCY DISTRIBUTION ===
    # # Collect latency values for each experiment
    # # latency_data_by_experiment = []
    # # labels = []
    # # for label, results in all_results.items():
    # #     latency_data = results['latency']
    # #     if latency_data:
    # #         latency_values = [latency / MILLISECOND for latency in latency_data.values()]
    # #         latency_data_by_experiment.append(latency_values)
    # #         labels.append(label)
    # #
    # # Create boxplot for latency
    # # boxprops = dict(facecolor="lightblue", color="black")
    # # medianprops = dict(color="black", linewidth=2)
    # # whiskerprops = dict(color="black")
    # # capprops = dict(color="black")
    # #
    # # ax1.boxplot(latency_data_by_experiment, labels=labels, patch_artist=True, showmeans=False, showfliers=False,
    # #             boxprops=boxprops, medianprops=medianprops, whiskerprops=whiskerprops, capprops=capprops, widths=0.5)
    # # ax1.set_title('Latency Distribution')
    # # ax1.set_ylabel('Latency (ms)')
    # # ax1.grid(True, alpha=0.3)
    # #
    # # === FIDELITY DISTRIBUTION ===
    # plt.figure(figsize=(7, 5))

    # # Collect fidelity values for each experiment
    # fidelity_data_by_experiment = []
    # labels = []
    # for label, results in all_results.items():
    #     fidelity_data = results['fidelity']
    #     if fidelity_data:
    #         fidelity_values = [f[0] for f in fidelity_data.values()]
    #         fidelity_data_by_experiment.append(fidelity_values)
    #         labels.append(label)

    # # Create boxplot for fidelity
    # boxprops = dict(facecolor="lightblue", color="black")
    # medianprops = dict(color="black", linewidth=2)
    # whiskerprops = dict(color="black")
    # capprops = dict(color="black")

    # plt.boxplot(fidelity_data_by_experiment, labels=labels, patch_artist=True, showmeans=False, showfliers=False,
    #             boxprops=boxprops, medianprops=medianprops, whiskerprops=whiskerprops, capprops=capprops, widths=0.5)
    # plt.title('Entanglement Fidelity Distribution', fontsize=14)
    # plt.ylabel('Fidelity', fontsize=12)
    # plt.xticks(fontsize=12)
    # plt.yticks(fontsize=12)
    # plt.grid(True, alpha=0.3)

    # plt.tight_layout()

    # plt.savefig("plots/experiment_results.png")
    # plt.show()