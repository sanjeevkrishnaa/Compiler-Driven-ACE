from collections import defaultdict
import numpy as np
from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
import sequence.utils.log as log
from request_app_dynamic import RequestAppLatencyDynamic
from router_net_topo_adaptive import RouterNetTopoAdaptive
import random
import json
import os
import csv
import matplotlib.pyplot as plt

SECOND = int(1e12)

def get_dynamic_request_queue_mesh(num_requests: int, memo_size: int, fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    '''
    Generates a queue of requests for a 4x4 mesh network with dynamic timing.
    Start and end times are NOT specified - they will be determined dynamically during simulation.

    Args:
        num_requests (int): Total number of requests to generate
        memo_size (int): The memory size for each request.
        fidelity (float): The fidelity requirement for each request.
        entanglement_number (int): The number of entanglements needed.
        seed (int): The random seed for reproducibility.
        
    Return:
        list: A list of requests, where each request is a tuple:
              (id, src_name, dst_name, memo_size, fidelity, entanglement_number)
              Note: start_time and end_time are NOT included - they're determined dynamically
    '''
    # Define the 4x4 grid of nodes
    nodes = [(i, j) for i in range(4) for j in range(4)]
    
    random.seed(seed)
    
    request_id = 0
    request_queue = []

    for i in range(num_requests):
        src_coord, dst_coord = random.sample(nodes, 2)
        
        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'

        request = (
            request_id, 
            src_name, 
            dst_name, 
            memo_size, 
            fidelity, 
            entanglement_number
        )
        request_queue.append(request)
        request_id += 1
        
    return request_queue


def get_dynamic_request_queue_mesh_first_last(num_requests: int, memo_size: int, fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    '''
    Generates requests between first (column 0) and last (column 3) columns with dynamic timing.
    '''
    first_col_nodes = [(i, 0) for i in range(4)]
    last_col_nodes = [(i, 3) for i in range(4)]
    
    random.seed(seed)
    
    request_id = 0
    request_queue = []

    for i in range(num_requests):
        # Randomly decide direction: first->last or last->first
        if random.random() < 0.5:
            src_coord = random.choice(first_col_nodes)
            dst_coord = random.choice(last_col_nodes)
        else:
            src_coord = random.choice(last_col_nodes)
            dst_coord = random.choice(first_col_nodes)
        
        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'

        request = (
            request_id, 
            src_name, 
            dst_name, 
            memo_size, 
            fidelity, 
            entanglement_number
        )
        request_queue.append(request)
        request_id += 1
        
    return request_queue


class DynamicRequestManager:
    """
    Manages dynamic sequential requests with configurable pre-generation time.
    Sends next request immediately after previous one completes + pre-gen buffer.
    """
    
    def __init__(self, timeline, name_to_apps: dict, request_queue: list, pregeneration_time_ms: float, request_duration_ms: float):
        """
        Args:
            timeline: The simulation timeline
            name_to_apps: Dictionary mapping node names to their RequestApp instances
            request_queue: List of requests (without timing info)
            pregeneration_time_ms: Time in milliseconds to allow for pre-generation before each request
            request_duration_ms: Maximum duration in milliseconds for each request window
        """
        self.timeline = timeline
        self.name_to_apps = name_to_apps
        self.request_queue = request_queue
        self.pregeneration_time = int(pregeneration_time_ms * MILLISECOND)  # Convert to picoseconds
        self.request_duration = int(request_duration_ms * MILLISECOND)  # Convert to picoseconds
        
        self.current_request_index = 0
        self.request_start_times = {}  # Maps request_id to actual start time
        self.request_end_times = {}    # Maps request_id to actual completion time
        self.series_start_time = None
        self.series_end_time = None
        
    def start(self):
        """Start the dynamic request series"""
        self.series_start_time = self.timeline.now()
        print(f"DynamicRequestManager: Starting request series at time {self.series_start_time}")
        self._send_next_request()
    
    def _send_next_request(self):
        """Send the next request in the queue"""
        if self.current_request_index >= len(self.request_queue):
            # All requests sent
            print("All requests have been sent.")
            return
        
        request = self.request_queue[self.current_request_index]
        request_id, src_name, dst_name, memo_size, fidelity, entanglement_number = request
        
        # Calculate timing for this request
        current_time = self.timeline.now()
        print(f"DynamicRequestManager: Preparing to send request {request_id} at time {current_time}")

        start_time = current_time + self.pregeneration_time
        end_time = start_time + self.request_duration
        
        # Store the actual start time
        self.request_start_times[request_id] = start_time
        
        # Get the app and start the request
        app = self.name_to_apps[src_name]
        app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, request_id)
        
        # Register callback for when this request completes
        app.set_completion_callback(self._on_request_completed, request_id)
        
        print(f"DynamicRequestManager: Sent request {request_id} at time {current_time/MILLISECOND:.2f}ms, "
                       f"start_time={start_time/MILLISECOND:.2f}ms, end_time={end_time/MILLISECOND:.2f}ms")
        
        self.current_request_index += 1
    
    def _on_request_completed(self, request_id: int, completion_time: int):
        """
        Callback when a request completes successfully.
        
        Args:
            request_id: ID of the completed request
            completion_time: Simulation time when request completed
        """
        self.request_end_times[request_id] = completion_time
        
        print(f"DynamicRequestManager: Request {request_id} completed at {completion_time/MILLISECOND:.2f}ms")
        
        # Schedule the next request immediately (it will start after pre-generation time)
        if self.current_request_index < len(self.request_queue):
            from sequence.kernel.process import Process
            from sequence.kernel.event import Event
            process = Process(self, "_send_next_request", [])
            event = Event(completion_time, process)
            self.timeline.schedule(event)
        else:
            # All requests completed
            self.series_end_time = completion_time
            print(f"DynamicRequestManager: All requests completed at {completion_time/MILLISECOND:.2f}ms")
    
    def get_end_to_end_latency(self) -> float:
        """Returns the total time taken to complete all requests in milliseconds"""
        if self.series_start_time is None or self.series_end_time is None:
            return 0.0
        return (self.series_end_time - self.series_start_time) / MILLISECOND
    
    def get_individual_latencies(self) -> dict:
        """Returns latency for each request in milliseconds"""
        latencies = {}
        for req_id in self.request_start_times:
            if req_id in self.request_end_times:
                start = self.request_start_times[req_id]
                end = self.request_end_times[req_id]
                latencies[req_id] = (end - start) / MILLISECOND
        return latencies


def run_dynamic_experiment(config_file: str, update_prob_setting: bool, purify_setting: bool, 
                          request_queue: list, pregeneration_time_ms: float, 
                          request_duration_ms: float, experiment_label: str):
    """
    Run an experiment with dynamic sequential requests.
    
    Args:
        config_file: Path to network configuration JSON
        update_prob_setting: Whether to enable adaptive probability updates
        purify_setting: Whether to enable purification
        request_queue: List of requests (without timing)
        pregeneration_time_ms: Pre-generation buffer time in milliseconds
        request_duration_ms: Maximum request duration in milliseconds
        experiment_label: Label for this experiment
    
    Returns:
        Tuple of (end_to_end_latency, individual_latencies, latency_dict, fidelity_dict)
    """
    log_filename = f'log/log_{experiment_label.replace(" ", "_")}'

    network_topo = RouterNetTopoAdaptive(config_file)
    tl = network_topo.get_timeline()
    tl.seed(0)

    # Set up logging
    log.set_logger(__name__, tl, log_filename)
    log.set_logger_level('INFO')
    modules = ['adaptive_continuous', 'request_app', 'swapping', 'network_manager', 
               'resource_manager', 'main', 'rule_manager', 'generation', 'purification', 'reservation']
    for module in modules:
        log.track_module(module)

    # Configure routers and applications
    name_to_apps = {}
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        app = RequestAppLatencyDynamic(router)
        name_to_apps[router.name] = app
        router.adaptive_continuous.has_empty_neighbor = True
        router.adaptive_continuous.update_prob = update_prob_setting
        router.adaptive_continuous.purify = purify_setting

    # Create dynamic request manager
    request_manager = DynamicRequestManager(
        tl, name_to_apps, request_queue, 
        pregeneration_time_ms, request_duration_ms
    )
    
    # Schedule the start of the request series
    from sequence.kernel.process import Process
    from sequence.kernel.event import Event
    process = Process(request_manager, "start", [])
    event = Event(0, process)
    tl.schedule(event)

    # Run the simulation
    tl.init()
    tl.run()

    # Collect results
    latency_dict = defaultdict(float)
    fidelity_dict = defaultdict(list)
    for _, app in name_to_apps.items():
        latency_dict |= app.latency
        fidelity_dict |= app.entanglement_fidelities

    # Get end-to-end metrics
    end_to_end_latency = request_manager.get_end_to_end_latency()
    individual_latencies = request_manager.get_individual_latencies()

    # Print summary
    print(f"\n--- Results for {experiment_label} ---")
    print(f"Pre-generation time: {pregeneration_time_ms:.2f} ms")
    print(f"End-to-end latency: {end_to_end_latency:.2f} ms")
    print(f"Number of completed requests: {len(individual_latencies)}/{len(request_queue)}")
    
    if individual_latencies:
        avg_individual = np.mean(list(individual_latencies.values()))
        print(f"Average individual request latency: {avg_individual:.2f} ms")
    
    for reservation, latency in sorted(latency_dict.items()):
        fidelity = fidelity_dict[reservation][0]
        print(f'Req ID={reservation.identity}, Latency={latency / MILLISECOND:.2f} ms, Fidelity={fidelity:.4f}')
    
    return end_to_end_latency, individual_latencies, latency_dict, fidelity_dict


if __name__ == "__main__":
    # Create directories if they don't exist
    os.makedirs('plots', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    os.makedirs('log', exist_ok=True)
    os.makedirs('test', exist_ok=True)

    # Configuration
    num_requests = 100  # Number of sequential requests
    pregeneration_times = [1.3]  # Different pre-generation times to test (in milliseconds)
    request_duration_ms = 30  # Maximum duration for each request
    
    # Generate request series
    request_type = "first_last"  # or "random"
    request_file = f"test/dynamic_request_queue_{request_type}.txt"
    
    if os.path.exists(request_file):
        print(f"Loading shared request queue from {request_file}...")
        with open(request_file, "r") as f:
            shared_requests = json.load(f)
    else:
        print(f"Generating new request queue...")
        if request_type == "first_last":
            shared_requests = get_dynamic_request_queue_mesh_first_last(
                num_requests=num_requests, 
                memo_size=1, 
                fidelity=0.01, 
                entanglement_number=1, 
                seed=0
            )
        else:
            shared_requests = get_dynamic_request_queue_mesh(
                num_requests=num_requests, 
                memo_size=1, 
                fidelity=0.01, 
                entanglement_number=1, 
                seed=0
            )
        

        with open(request_file, "w") as f:
            json.dump(shared_requests, f, indent=2)
        print(f"Saved request queue to {request_file}")

    print(f"\nRunning experiments with {len(shared_requests)} requests...")
    print(f"Request type: {request_type}")
    print(f"Request duration: {request_duration_ms} ms")

    # Store results for all experiments
    all_results = []
    
    # Run experiments with different pre-generation times
    for pregen_time in pregeneration_times:
        print(f"\n{'='*80}")
        print(f"Testing with pre-generation time: {pregen_time} ms")
        print(f"{'='*80}")
        
        # Experiment 1: ACE-0 (no proactive entanglement)
        exp_label = f"ACE0_PreGen{pregen_time}ms"
        e2e_latency, indiv_latencies, latency_dict, fidelity_dict = run_dynamic_experiment(
            config_file='config/grid_4x4_ace_0.json',
            update_prob_setting=False,
            purify_setting=False,
            request_queue=shared_requests,
            pregeneration_time_ms=pregen_time,
            request_duration_ms=request_duration_ms,
            experiment_label=exp_label
        )
        all_results.append({
            'label': exp_label,
            'pregen_time': pregen_time,
            'config': 'ACE-0',
            'update_prob': False,
            'e2e_latency': e2e_latency,
            'individual_latencies': indiv_latencies,
            'latency_dict': latency_dict,
            'fidelity_dict': fidelity_dict
        })
        
        # Experiment 2: ACE-5 without probability updates
        # exp_label = f"ACE5_NoUpdate_PreGen{pregen_time}ms"
        # e2e_latency, indiv_latencies, latency_dict, fidelity_dict = run_dynamic_experiment(
        #     config_file='config/grid_4x4_ace_5.json',
        #     update_prob_setting=False,
        #     purify_setting=False,
        #     request_queue=shared_requests,
        #     pregeneration_time_ms=pregen_time,
        #     request_duration_ms=request_duration_ms,
        #     experiment_label=exp_label
        # )
        # all_results.append({
        #     'label': exp_label,
        #     'pregen_time': pregen_time,
        #     'config': 'ACE-5',
        #     'update_prob': False,
        #     'e2e_latency': e2e_latency,
        #     'individual_latencies': indiv_latencies,
        #     'latency_dict': latency_dict,
        #     'fidelity_dict': fidelity_dict
        # })
        
        # Experiment 3: ACE-5 with probability updates
        # exp_label = f"ACE5_WithUpdate_PreGen{pregen_time}ms"
        # e2e_latency, indiv_latencies, latency_dict, fidelity_dict = run_dynamic_experiment(
        #     config_file='config/grid_4x4_ace_5.json',
        #     update_prob_setting=True,
        #     purify_setting=False,
        #     request_queue=shared_requests,
        #     pregeneration_time_ms=pregen_time,
        #     request_duration_ms=request_duration_ms,
        #     experiment_label=exp_label
        # )
        # all_results.append({
        #     'label': exp_label,
        #     'pregen_time': pregen_time,
        #     'config': 'ACE-5',
        #     'update_prob': True,
        #     'e2e_latency': e2e_latency,
        #     'individual_latencies': indiv_latencies,
        #     'latency_dict': latency_dict,
        #     'fidelity_dict': fidelity_dict
        # })

    # Save CSV data for each experiment
    print(f"\n{'='*80}")
    print("Saving CSV data...")
    print(f"{'='*80}")
    
    request_info_map = {req[0]: (req[1], req[2]) for req in shared_requests}
    
    for result in all_results:
        csv_filename = f"data/{result['label']}.csv"
        with open(csv_filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Request_ID', 'Source', 'Destination', 'Latency_ms', 'Fidelity'])
            
            for reservation, latency in sorted(result['latency_dict'].items(), key=lambda x: x[0].identity):
                req_id = reservation.identity
                src, dst = request_info_map.get(req_id, ('Unknown', 'Unknown'))
                fidelity = result['fidelity_dict'][reservation][0]
                latency_ms = latency / MILLISECOND
                writer.writerow([req_id, src, dst, f"{latency_ms:.4f}", f"{fidelity:.6f}"])
        print(f"Saved {csv_filename}")

    # Create comparison plots
    print(f"\n{'='*80}")
    print("Creating plots...")
    print(f"{'='*80}")
    
    # Plot 1: End-to-end latency comparison
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for config_type in ['ACE-0', 'ACE-5 (No Update)', 'ACE-5 (With Update)']:
        if config_type == 'ACE-0':
            results_subset = [r for r in all_results if r['config'] == 'ACE-0']
        elif config_type == 'ACE-5 (No Update)':
            results_subset = [r for r in all_results if r['config'] == 'ACE-5' and not r['update_prob']]
        else:
            results_subset = [r for r in all_results if r['config'] == 'ACE-5' and r['update_prob']]
        
        pregen_times_plot = [r['pregen_time'] for r in results_subset]
        e2e_latencies = [r['e2e_latency'] for r in results_subset]
        ax.plot(pregen_times_plot, e2e_latencies, marker='o', linewidth=2, markersize=8, label=config_type)
    
    ax.set_xlabel('Pre-generation Time (ms)', fontsize=12)
    ax.set_ylabel('End-to-End Latency (ms)', fontsize=12)
    ax.set_title(f'End-to-End Latency vs Pre-generation Time\n({num_requests} sequential requests)', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('plots/dynamic_e2e_latency_comparison.png', dpi=300)
    print("Saved plots/dynamic_e2e_latency_comparison.png")
    plt.close()
    
    # Plot 2: Individual request latencies for each pre-generation time
    for pregen_time in pregeneration_times:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        results_at_pregen = [r for r in all_results if r['pregen_time'] == pregen_time]
        
        # Individual latencies
        for result in results_at_pregen:
            latency_dict = result['latency_dict']
            if latency_dict:
                req_ids = [res.identity for res in sorted(latency_dict.keys(), key=lambda x: x.identity)]
                latencies = [latency_dict[res] / MILLISECOND for res in sorted(latency_dict.keys(), key=lambda x: x.identity)]
                ax1.plot(req_ids, latencies, marker='o', linewidth=1.5, markersize=4, label=result['label'], alpha=0.7)
        
        ax1.set_xlabel('Request ID', fontsize=11)
        ax1.set_ylabel('Latency (ms)', fontsize=11)
        ax1.set_title(f'Individual Request Latencies (Pre-gen: {pregen_time}ms)', fontsize=12)
        ax1.legend(fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        # Fidelities
        for result in results_at_pregen:
            fidelity_dict = result['fidelity_dict']
            if fidelity_dict:
                req_ids = [res.identity for res in sorted(fidelity_dict.keys(), key=lambda x: x.identity)]
                fidelities = [fidelity_dict[res][0] for res in sorted(fidelity_dict.keys(), key=lambda x: x.identity)]
                ax2.plot(req_ids, fidelities, marker='o', linewidth=1.5, markersize=4, label=result['label'], alpha=0.7)
        
        ax2.set_xlabel('Request ID', fontsize=11)
        ax2.set_ylabel('Fidelity', fontsize=11)
        ax2.set_title(f'Fidelity per Request (Pre-gen: {pregen_time}ms)', fontsize=12)
        ax2.legend(fontsize=9)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'plots/dynamic_details_pregen{pregen_time}ms.png', dpi=300)
        print(f"Saved plots/dynamic_details_pregen{pregen_time}ms.png")
        plt.close()

    # Summary table
    print(f"\n{'='*80}")
    print("SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'Experiment':<40} {'PreGen(ms)':<12} {'E2E Latency(ms)':<18} {'Avg Req Latency(ms)':<20}")
    print("-" * 90)
    
    for result in all_results:
        avg_req_latency = np.mean(list(result['individual_latencies'].values())) if result['individual_latencies'] else 0
        print(f"{result['label']:<40} {result['pregen_time']:<12} {result['e2e_latency']:<18.2f} {avg_req_latency:<20.2f}")
    
    print(f"{'='*80}\n")