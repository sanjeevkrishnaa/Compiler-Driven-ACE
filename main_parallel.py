from collections import defaultdict
import numpy as np
from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
from sequence.kernel.process import Process
from sequence.kernel.event import Event
import sequence.utils.log as log
from request_app_parallel import RequestAppLatencyParallel
from router_net_topo_adaptive import RouterNetTopoAdaptive
import random
import json
import os
import csv
import matplotlib.pyplot as plt

SECOND = int(1e12)


def generate_layered_requests(num_layers: int, max_requests_per_layer: int, memo_size: int, 
                              fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    """
    Generates layered requests for a 4x4 mesh network.
    Each layer contains requests with disjoint source-destination cores.
    
    Args:
        num_layers: Number of layers to generate
        requests_per_layer: Maximum number of requests per layer (up to 3 for disjoint cores)
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility
        
    Return:
        list of layers, where each layer is a list of requests:
        [
            [(id, src, dst, memo_size, fidelity, entanglement_number), ...],  # Layer 0
            [(id, src, dst, memo_size, fidelity, entanglement_number), ...],  # Layer 1
            ...
        ]
    """
    random.seed(seed)
    
    # Define all nodes in 4x4 grid
    all_nodes = [(i, j) for i in range(4) for j in range(4)]
    
    layers = []
    request_id = 0
    
    for layer_idx in range(num_layers):
        layer_requests = []
        used_cores = set()  # Track cores used in this layer
        
        # Try to create up to requests_per_layer requests with disjoint cores
        attempts = 0
        max_attempts = 100  # Prevent infinite loops
        requests_per_layer = random.randint(1, max_requests_per_layer)
        while len(layer_requests) < requests_per_layer and attempts < max_attempts:
            # Randomly select source and destination
            src_coord = random.choice(all_nodes)
            dst_coord = random.choice(all_nodes)
            
            # Ensure source != destination and cores are not already used
            if (src_coord != dst_coord and 
                src_coord not in used_cores and 
                dst_coord not in used_cores):
                
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
                
                layer_requests.append(request)
                used_cores.add(src_coord)
                used_cores.add(dst_coord)
                request_id += 1
            
            attempts += 1
        
        if layer_requests:
            layers.append(layer_requests)
            print(f"Layer {layer_idx}: Generated {len(layer_requests)} requests with disjoint cores")
    
    return layers

def generate_layered_requests_sequential(num_layers: int, memo_size: int,
                                          fidelity: float, entanglement_number: int,
                                          seed: int = 0) -> list:
    return generate_layered_requests(num_layers, 1, memo_size, fidelity, entanglement_number, seed)


def generate_structured_layered_requests_sequential(num_layers: int, memo_size: int,
                                                    fidelity: float, entanglement_number: int,
                                                    seed: int = 0) -> list:
    """
    Generates sequential layered requests (1 request per layer).
    Each request goes from a random node in column 0 to a random node in column 3.
    
    Args:
        num_layers: Number of layers to generate
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility
        
    Return:
        list of layers, where each layer has exactly 1 request from col0 to col3
    """
    random.seed(seed)
    
    # Column 0 nodes: (0,0), (1,0), (2,0), (3,0)
    # Column 3 nodes: (0,3), (1,3), (2,3), (3,3)
    col0_nodes = [(i, 0) for i in range(4)]
    col3_nodes = [(i, 3) for i in range(4)]
    
    layers = []
    request_id = 0
    
    for layer_idx in range(num_layers):
        # Pick random source from column 0 and destination from column 3
        src_coord = random.choice(col0_nodes)
        dst_coord = random.choice(col3_nodes)
        
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
        
        layers.append([request])  # Single request per layer
        print(f"Layer {layer_idx}: {src_name} -> {dst_name}")
        request_id += 1
    
    return layers



def generate_structured_layered_requests(num_layers: int, memo_size: int, 
                                        fidelity: float, entanglement_number: int, 
                                        seed: int = 0) -> list:
    """
    Generates structured layered requests ensuring exactly 3 disjoint request pairs per layer.
    Uses a more deterministic approach to maximize parallelism.
    
    Strategy: Partition the 4x4 grid into regions and create requests between regions.
    """
    random.seed(seed)
    
    # Define specific non-overlapping pairs for maximum parallelism
    # These are manually crafted to ensure disjoint cores
    pair_templates = [
        # Template 1: Corners
        [
            ((0, 0), (3, 3)),  # Top-left to bottom-right
            ((0, 3), (3, 0)),  # Top-right to bottom-left
            ((1, 1), (2, 2)),  # Middle diagonal
        ],
        # Template 2: Edges to opposite edges
        [
            ((0, 1), (3, 2)),
            ((1, 0), (2, 3)),
            ((0, 2), (3, 1)),
        ],
        # Template 3: Cross patterns
        [
            ((0, 0), (2, 3)),
            ((1, 1), (3, 2)),
            ((2, 0), (0, 3)),
        ],
        # Template 4: Different corners
        [
            ((0, 1), (3, 3)),
            ((1, 0), (2, 3)),
            ((3, 0), (0, 2)),
        ],
        # Template 5: Mixed patterns
        [
            ((0, 0), (3, 2)),
            ((0, 3), (2, 1)),
            ((1, 0), (3, 3)),
        ],
        # Template 6: Vertical spreads
        [
            ((0, 0), (3, 1)),
            ((1, 2), (2, 3)),
            ((0, 3), (3, 0)),
        ],
    ]
    
    layers = []
    request_id = 0
    
    for layer_idx in range(num_layers):
        # Select a template (cycle through them)
        template = pair_templates[layer_idx % len(pair_templates)]
        
        # Optionally shuffle pairs within template for variety
        template_copy = template.copy()
        random.shuffle(template_copy)
        
        layer_requests = []
        for src_coord, dst_coord in template_copy:
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
            
            layer_requests.append(request)
            request_id += 1
        
        layers.append(layer_requests)
        print(f"Layer {layer_idx}: {len(layer_requests)} requests - "
              f"{[(r[1], r[2]) for r in layer_requests]}")
    
    return layers


class ParallelLayerRequestManager:
    """
    Manages layered parallel requests where:
    - All requests in a layer are submitted simultaneously
    - Wait for ALL requests in current layer to complete before starting next layer
    - Pre-generation time applied before each layer
    - Failed requests are retried in a new layer (treated as congestion)
    """
    
    def __init__(self, timeline, name_to_apps: dict, layered_requests: list, 
                 pregeneration_time_ms: float, request_duration_ms: float):
        """
        Args:
            timeline: The simulation timeline
            name_to_apps: Dictionary mapping node names to RequestApp instances
            layered_requests: List of layers, each layer is a list of requests
            pregeneration_time_ms: Pre-generation buffer time in milliseconds
            request_duration_ms: Maximum duration for each request window in milliseconds
        """
        self.timeline = timeline
        self.name_to_apps = name_to_apps
        self.original_layered_requests = layered_requests  # Keep original for reporting
        self.layered_requests = layered_requests.copy()  # Working copy that includes retries
        self.pregeneration_time = int(pregeneration_time_ms * MILLISECOND)
        self.request_duration = int(request_duration_ms * MILLISECOND)
        
        self.current_layer_index = 0
        self.pending_requests = set()  # Tracks requests in current layer not yet completed
        self.pending_request_data = {}  # Maps request_id to full request tuple
        
        # Track original layer count
        self.original_layer_count = len(layered_requests)
        self.retry_layer_count = 0  # Number of retry layers added
        
        # Tracking metrics
        self.layer_start_times = {}    # Maps layer_index to when reservation requests are submitted
        self.layer_end_times = {}      # Maps layer_index to end time (when last request completes)
        self.request_submission_times = {}  # Maps request_id to when reservation request is submitted
        self.request_approval_times = {}  # Maps request_id to when reservation is approved
        self.request_generation_start_times = {}  # Maps request_id to when entanglement generation starts
        self.request_end_times = {}    # Maps request_id to completion time
        self.request_retry_count = {}  # Maps request_id to number of retries
        
        self.series_start_time = None
        self.series_end_time = None
        
    def start(self):
        """Start the layered request series"""
        self.series_start_time = self.timeline.now()
        print(f"\n{'='*80}")
        print(f"ParallelLayerRequestManager: Starting layered request series")
        print(f"Total layers: {len(self.original_layered_requests)}")
        print(f"Series start time SET TO: {self.series_start_time / MILLISECOND:.2f} ms")
        print(f"{'='*80}\n")
        self._send_layer()
    
    def _send_layer(self):
        """Send all requests in the current layer simultaneously"""
        if self.current_layer_index >= len(self.layered_requests):
            # All layers processed - this should not happen here anymore
            print(f"\nWARNING: _send_layer called after all layers processed")
            return
        
        current_layer = self.layered_requests[self.current_layer_index]
        current_time = self.timeline.now()
        
        # Track when we actually submit this layer (includes reservation setup time)
        self.layer_start_times[self.current_layer_index] = current_time
        
        # Apply pre-generation time
        start_time = current_time + self.pregeneration_time
        end_time = start_time + self.request_duration
        
        # Determine if this is a retry layer
        is_retry_layer = self.current_layer_index >= self.original_layer_count
        
        print(f"\n--- Layer {self.current_layer_index} {'(RETRY due to congestion)' if is_retry_layer else ''} ---")
        print(f"Current time (reservation submission): {current_time / MILLISECOND:.2f} ms")
        print(f"Pre-generation buffer: {self.pregeneration_time / MILLISECOND:.2f} ms (excluded from measurements)")
        print(f"Entanglement generation start: {start_time / MILLISECOND:.2f} ms")
        print(f"Entanglement generation end (window): {end_time / MILLISECOND:.2f} ms")
        print(f"Number of parallel requests: {len(current_layer)}")
        print(f"NOTE: Measured latency = reservation_setup_time + entanglement_generation_time")
        
        # Send all requests in this layer
        for request in current_layer:
            request_id, src_name, dst_name, memo_size, fidelity, entanglement_number = request
            
            # Track this request as pending
            self.pending_requests.add(request_id)
            self.pending_request_data[request_id] = request
            
            # Track retries
            if request_id not in self.request_retry_count:
                self.request_retry_count[request_id] = 0
            else:
                self.request_retry_count[request_id] += 1
                print(f"  Request {request_id} is being RETRIED (attempt {self.request_retry_count[request_id] + 1})")
            
            # Track when we submit the reservation request (for setup time calculation)
            self.request_submission_times[request_id] = current_time
            # Track when entanglement generation will start (after pre-generation time)
            self.request_generation_start_times[request_id] = start_time
            
            # Get app and start request
            app = self.name_to_apps[src_name]
            app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, request_id)
            
            # Register callbacks
            app.set_reservation_approval_callback(self._on_reservation_approved, request_id)
            app.set_completion_callback(self._on_request_completed, request_id)
            
            print(f"  Sent request {request_id}: {src_name} -> {dst_name}")
        
        print(f"Layer {self.current_layer_index}: Submitted {len(current_layer)} requests")
        
        # Schedule a timeout check at the end of this layer's time window
        timeout_time = end_time
        process = Process(self, "_check_layer_timeout", [self.current_layer_index, timeout_time])
        event = Event(timeout_time, process)
        self.timeline.schedule(event)
        print(f"Scheduled timeout check for layer {self.current_layer_index} at {timeout_time / MILLISECOND:.2f} ms")
        
        self.current_layer_index += 1
    
    def _check_layer_timeout(self, layer_idx: int, timeout_time: int):
        """
        Check if a layer has timed out (i.e., some requests haven't completed).
        If there are pending requests, create a retry layer for them.
        """
        # Only check if this is the current active layer
        if layer_idx != self.current_layer_index - 1:
            return
        
        if len(self.pending_requests) > 0:
            print(f"\n{'!'*80}")
            print(f"WARNING: Layer {layer_idx} TIMEOUT at {timeout_time / MILLISECOND:.2f} ms")
            print(f"Pending requests that did not complete: {self.pending_requests}")
            print(f"These requests will be RETRIED in a new layer (congestion detected)")
            print(f"{'!'*80}\n")
            
            # Layer end time is the completion time of the LAST SUCCESSFUL request
            # Find the latest completion time among completed requests in this layer
            layer_requests = self.layered_requests[layer_idx]
            completed_request_ids = [req[0] for req in layer_requests if req[0] in self.request_end_times]
            
            if completed_request_ids:
                # Get the maximum completion time of successful requests
                last_completion_time = max(self.request_end_times[req_id] for req_id in completed_request_ids)
                self.layer_end_times[layer_idx] = last_completion_time
                print(f"Layer {layer_idx} end time set to: {last_completion_time / MILLISECOND:.2f} ms (last successful request)")
            else:
                # No requests completed - use layer start time
                self.layer_end_times[layer_idx] = self.layer_start_times[layer_idx]
                print(f"Layer {layer_idx}: No requests completed, end time = start time")
            
            # Create retry layer with pending requests
            retry_layer = []
            for req_id in list(self.pending_requests):
                if req_id in self.pending_request_data:
                    retry_layer.append(self.pending_request_data[req_id])
            
            # Clear pending requests (they'll be re-added when retry layer starts)
            self.pending_requests.clear()
            
            # Insert retry layer before the next original layer
            self.layered_requests.insert(self.current_layer_index, retry_layer)
            self.retry_layer_count += 1
            
            print(f"Created retry layer {self.current_layer_index} with {len(retry_layer)} requests")
            print(f"Total retry layers so far: {self.retry_layer_count}")
            
            # Check if we've processed all layers (including retries)
            if self.current_layer_index >= len(self.layered_requests):
                # Use the last layer's end time as series end time
                self.series_end_time = self.layer_end_times[layer_idx]
                print(f"\n{'='*80}")
                print(f"ParallelLayerRequestManager: ALL LAYERS COMPLETED (with retries)")
                print(f"Original layers: {self.original_layer_count}")
                print(f"Retry layers added: {self.retry_layer_count}")
                print(f"Total layers processed: {len(self.layered_requests)}")
                print(f"Series start time: {self.series_start_time / MILLISECOND:.2f} ms")
                print(f"Series end time: {self.series_end_time / MILLISECOND:.2f} ms")
                print(f"Total end-to-end latency: {self.get_end_to_end_latency():.2f} ms")
                print(f"{'='*80}\n")
            else:
                # Schedule next layer (retry layer) at timeout_time (not at last completion time)
                # The retry should start after the timeout window
                print(f"Scheduling next layer {self.current_layer_index} at {timeout_time / MILLISECOND:.2f} ms...\n")
                process = Process(self, "_send_layer", [])
                event = Event(timeout_time, process)
                self.timeline.schedule(event)
    
    def _on_reservation_approved(self, request_id: int, approval_time: int):
        """
        Callback when a reservation is approved.
        Tracks the time when RSVP protocol completes.
        """
        self.request_approval_times[request_id] = approval_time
        
        if request_id in self.request_submission_times:
            submission_time = self.request_submission_times[request_id]
            setup_time_ms = (approval_time - submission_time) / MILLISECOND
            print(f"  Request {request_id} reservation APPROVED at {approval_time / MILLISECOND:.2f} ms "
                  f"(setup time: {setup_time_ms:.2f} ms)")
    
    def _on_request_completed(self, request_id: int, completion_time: int):
        """
        Callback when a request completes.
        When all requests in current layer complete, start the next layer.
        """
        self.request_end_times[request_id] = completion_time
        
        # Remove from pending set
        if request_id in self.pending_requests:
            self.pending_requests.remove(request_id)
            # Also remove from pending data
            if request_id in self.pending_request_data:
                del self.pending_request_data[request_id]
        
        retry_info = f" (after {self.request_retry_count.get(request_id, 0)} retries)" if request_id in self.request_retry_count and self.request_retry_count[request_id] > 0 else ""
        print(f"  Request {request_id} completed at {completion_time / MILLISECOND:.2f} ms{retry_info}")
        
        # Check if all requests in current layer are complete
        if len(self.pending_requests) == 0:
            layer_idx = self.current_layer_index - 1  # We already incremented
            self.layer_end_times[layer_idx] = completion_time
            
            layer_duration = (completion_time - self.layer_start_times[layer_idx]) / MILLISECOND
            is_retry_layer = layer_idx >= self.original_layer_count
            retry_tag = " (RETRY LAYER)" if is_retry_layer else ""
            
            print(f"\n*** Layer {layer_idx}{retry_tag} COMPLETED at {completion_time / MILLISECOND:.2f} ms ***")
            print(f"*** Layer duration: {layer_duration:.2f} ms ***")
            print(f"*** Current layer index: {self.current_layer_index}, Total layers (with retries): {len(self.layered_requests)} ***")
            
            # Check if we've processed all layers
            if self.current_layer_index >= len(self.layered_requests):
                # All layers completed - set series end time
                self.series_end_time = completion_time
                print(f"\n{'='*80}")
                print(f"ParallelLayerRequestManager: ALL LAYERS COMPLETED")
                print(f"Original layers: {self.original_layer_count}")
                print(f"Retry layers added: {self.retry_layer_count}")
                print(f"Total layers processed: {len(self.layered_requests)}")
                print(f"Series start time: {self.series_start_time / MILLISECOND:.2f} ms")
                print(f"Series end time: {self.series_end_time / MILLISECOND:.2f} ms")
                print(f"Total end-to-end latency: {self.get_end_to_end_latency():.2f} ms")
                print(f"{'='*80}\n")
            else:
                # Schedule next layer immediately
                print(f"Scheduling next layer {self.current_layer_index}...\n")
                process = Process(self, "_send_layer", [])
                event = Event(completion_time, process)
                self.timeline.schedule(event)
    
    def get_end_to_end_latency(self) -> float:
        """
        Returns total end-to-end latency as the SUM of all layer latencies (in milliseconds).
        This represents the cumulative time spent processing all layers sequentially.
        """
        layer_latencies = self.get_layer_latencies()
        if not layer_latencies:
            return 0.0
        
        # Sum of all layer latencies (including retry layers)
        total_latency = sum(layer_latencies.values())
        return total_latency
    
    def get_layer_latencies(self) -> dict:
        """
        Returns latency for each layer in milliseconds.
        Layer latency = max(reservation_setup_time) + max(entanglement_generation_time)
        This represents the critical path through the layer.
        """
        layer_latencies = {}
        
        # Get breakdown for all requests
        breakdown = self.get_individual_latencies_breakdown()
        
        # Group requests by layer (including retry layers)
        for layer_idx in range(len(self.layered_requests)):
            layer_requests = self.layered_requests[layer_idx]
            request_ids = [req[0] for req in layer_requests]
            
            # Get max reservation time and max generation time for this layer
            max_reservation_time = 0
            max_generation_time = 0
            
            for req_id in request_ids:
                if req_id in breakdown:
                    max_reservation_time = max(max_reservation_time, breakdown[req_id]['reservation_setup_time_ms'])
                    max_generation_time = max(max_generation_time, breakdown[req_id]['entanglement_generation_time_ms'])
            
            # Layer latency is sum of max reservation time and max generation time
            if max_reservation_time > 0 or max_generation_time > 0:
                layer_latencies[layer_idx] = max_reservation_time + max_generation_time
        
        return layer_latencies
    
    def get_individual_latencies(self) -> dict:
        """
        Returns latency for each request in milliseconds.
        Latency = (completion_time - submission_time) - pre_generation_time
        This gives us: reservation_setup_time + entanglement_generation_time
        """
        latencies = {}
        for req_id in self.request_submission_times:
            if req_id in self.request_end_times:
                submission_time = self.request_submission_times[req_id]
                completion_time = self.request_end_times[req_id]
                # Subtract pre-generation time to get only setup + generation time
                latency_with_pregen = completion_time - submission_time
                latency_without_pregen = latency_with_pregen - self.pregeneration_time
                latencies[req_id] = latency_without_pregen / MILLISECOND
        return latencies
    
    def get_individual_latencies_breakdown(self) -> dict:
        """
        Returns detailed breakdown of timing for each request.
        Returns dict mapping request_id to {
            'reservation_setup_time_ms': time from submission to reservation approval,
            'entanglement_generation_time_ms': time from generation start to completion,
            'total_time_ms': setup + generation (excluding pre-generation buffer),
            'retry_count': number of times this request was retried
        }
        """
        breakdown = {}
        for req_id in self.request_submission_times:
            if req_id in self.request_approval_times and req_id in self.request_generation_start_times and req_id in self.request_end_times:
                submission_time = self.request_submission_times[req_id]
                approval_time = self.request_approval_times[req_id]
                generation_start = self.request_generation_start_times[req_id]
                completion_time = self.request_end_times[req_id]
                
                # Reservation setup time: from submission to approval (RSVP protocol time)
                setup_time = (approval_time - submission_time) / MILLISECOND
                
                # Entanglement generation time: from generation start to completion
                generation_time = (completion_time - generation_start) / MILLISECOND
                
                breakdown[req_id] = {
                    'reservation_setup_time_ms': setup_time,
                    'entanglement_generation_time_ms': generation_time,
                    'total_time_ms': setup_time + generation_time,
                    'retry_count': self.request_retry_count.get(req_id, 0)
                }
        return breakdown
    
    def get_statistics(self) -> dict:
        """Returns comprehensive statistics about the experiment"""
        stats = {
            'total_layers': self.original_layer_count,  # Report original layer count
            'retry_layers': self.retry_layer_count,
            'total_layers_with_retries': len(self.layered_requests),
            'total_requests': sum(len(layer) for layer in self.original_layered_requests),
            'completed_requests': len(self.request_end_times),
            'end_to_end_latency_ms': self.get_end_to_end_latency(),
            'layer_latencies': self.get_layer_latencies(),
            'individual_latencies': self.get_individual_latencies(),
            'timing_breakdown': self.get_individual_latencies_breakdown(),
        }
        
        layer_latencies = self.get_layer_latencies()
        if layer_latencies:
            stats['avg_layer_latency_ms'] = np.mean(list(layer_latencies.values()))
            stats['max_layer_latency_ms'] = np.max(list(layer_latencies.values()))
            stats['min_layer_latency_ms'] = np.min(list(layer_latencies.values()))
        
        individual_latencies = self.get_individual_latencies()
        if individual_latencies:
            stats['avg_request_latency_ms'] = np.mean(list(individual_latencies.values()))
        
        # Calculate average breakdown times
        breakdown = self.get_individual_latencies_breakdown()
        if breakdown:
            setup_times = [b['reservation_setup_time_ms'] for b in breakdown.values()]
            generation_times = [b['entanglement_generation_time_ms'] for b in breakdown.values()]
            retry_counts = [b['retry_count'] for b in breakdown.values()]
            
            stats['avg_reservation_setup_time_ms'] = np.mean(setup_times)
            stats['max_reservation_setup_time_ms'] = np.max(setup_times)
            stats['avg_entanglement_generation_time_ms'] = np.mean(generation_times)
            stats['max_entanglement_generation_time_ms'] = np.max(generation_times)
            stats['total_retries'] = sum(retry_counts)
            stats['requests_with_retries'] = sum(1 for r in retry_counts if r > 0)
        
        return stats


def run_parallel_experiment(config_file: str, update_prob_setting: bool, purify_setting: bool,
                            layered_requests: list, pregeneration_time_ms: float,
                            request_duration_ms: float, experiment_label: str):
    """
    Run an experiment with parallel layered requests.
    
    Returns:
        Dictionary with comprehensive results and statistics
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
        app = RequestAppLatencyParallel(router)
        name_to_apps[router.name] = app
        router.adaptive_continuous.has_empty_neighbor = True
        router.adaptive_continuous.update_prob = update_prob_setting
        router.resource_manager.purify = purify_setting
    
    # Create parallel layer request manager
    request_manager = ParallelLayerRequestManager(
        tl, name_to_apps, layered_requests,
        pregeneration_time_ms, request_duration_ms
    )
    
    # Schedule start
    
    process = Process(request_manager, "start", [])
    event = Event(0, process)
    tl.schedule(event)
    
    # Run simulation
    tl.init()
    tl.run()
    
    # Collect results from apps
    latency_dict = defaultdict(float)
    fidelity_dict = defaultdict(list)
    for _, app in name_to_apps.items():
        latency_dict |= app.latency
        fidelity_dict |= app.entanglement_fidelities
    
    # Get statistics
    stats = request_manager.get_statistics()
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"RESULTS: {experiment_label}")
    print(f"{'='*80}")
    print(f"Configuration: {config_file}")
    print(f"Update probability: {update_prob_setting}")
    print(f"Pre-generation buffer: {pregeneration_time_ms:.2f} ms (excluded from measurements)")
    print(f"\nStatistics (excluding pre-generation buffer):")
    print(f"  Original layers: {stats['total_layers']}")
    print(f"  Retry layers (due to congestion): {stats['retry_layers']}")
    print(f"  Total layers processed: {stats['total_layers_with_retries']}")
    print(f"  Total requests: {stats['total_requests']}")
    print(f"  Completed requests: {stats['completed_requests']}")
    print(f"  Total retries: {stats.get('total_retries', 0)}")
    print(f"  Requests with retries: {stats.get('requests_with_retries', 0)}")
    print(f"  End-to-end latency: {stats['end_to_end_latency_ms']:.2f} ms")
    if 'avg_layer_latency_ms' in stats:
        print(f"  Average layer latency: {stats['avg_layer_latency_ms']:.2f} ms")
        print(f"  Max layer latency: {stats['max_layer_latency_ms']:.2f} ms")
        print(f"  Min layer latency: {stats['min_layer_latency_ms']:.2f} ms")
    if 'avg_request_latency_ms' in stats:
        print(f"  Average request latency: {stats['avg_request_latency_ms']:.2f} ms")
    if 'avg_reservation_setup_time_ms' in stats:
        print(f"\nTiming Breakdown:")
        print(f"  Average reservation setup time: {stats['avg_reservation_setup_time_ms']:.2f} ms")
        print(f"  Max reservation setup time: {stats['max_reservation_setup_time_ms']:.2f} ms")
        print(f"  Average entanglement generation time: {stats['avg_entanglement_generation_time_ms']:.2f} ms")
        print(f"  Max entanglement generation time: {stats['max_entanglement_generation_time_ms']:.2f} ms")
        print(f"  (Layer latency = max(reservation_setup) + max(generation))")
    print(f"{'='*80}\n")
    
    return {
        'stats': stats,
        'latency_dict': latency_dict,
        'fidelity_dict': fidelity_dict,
        'request_manager': request_manager
    }

# if __name__ == "__main__":
#     # Create directories
#     os.makedirs('plots', exist_ok=True)
#     os.makedirs('data', exist_ok=True)
#     os.makedirs('log', exist_ok=True)
    
#     # Load requests from file
#     request_file = "test/fixed_qubit_displacement_1.json"
    
#     if not os.path.exists(request_file):
#         print(f"ERROR: {request_file} not found!")
#         exit(1)
    
#     print(f"Loading requests from {request_file}...")
#     with open(request_file, "r") as f:
#         layered_requests = json.load(f)
    
#     total_requests = sum(len(layer) for layer in layered_requests)
#     num_layers = len(layered_requests)
    
#     print(f"\nLoaded configuration:")
#     print(f"  Total layers: {num_layers}")
#     print(f"  Total requests: {total_requests}")
#     print(f"  Requests per layer: {[len(layer) for layer in layered_requests]}")
    
#     # Configuration
#     pregeneration_time_ms = 5.3
#     request_duration_ms = 100
    
#     # Store results
#     all_results = []
    
#     # Experiment 1: ACE-0 (on-demand)
#     exp_label = f"real_ACE0"
#     print(f"\n{'='*80}")
#     print(f"Running {exp_label}")
#     print(f"{'='*80}\n")
#     result = run_parallel_experiment(
#         config_file='config/grid_4x4_ace_0.json',
#         update_prob_setting=False,
#         purify_setting=False,
#         layered_requests=layered_requests,
#         pregeneration_time_ms=pregeneration_time_ms,
#         request_duration_ms=request_duration_ms,
#         experiment_label=exp_label
#     )
#     result['label'] = exp_label
#     result['config'] = 'ACE-0'
#     result['update_prob'] = False
#     all_results.append(result)
    
#     # Experiment 2: ACE-8 without adaptation
#     exp_label = f"real_ACE8_NoUpdate"
#     print(f"\n{'='*80}")
#     print(f"Running {exp_label}")
#     print(f"{'='*80}\n")
#     result = run_parallel_experiment(
#         config_file='config/grid_4x4_ace_8.json',
#         update_prob_setting=False,
#         purify_setting=False,
#         layered_requests=layered_requests,
#         pregeneration_time_ms=pregeneration_time_ms,
#         request_duration_ms=request_duration_ms,
#         experiment_label=exp_label
#     )
#     result['label'] = exp_label
#     result['config'] = 'ACE-8 (No Update)'
#     result['update_prob'] = False
#     all_results.append(result)
    
#     # Experiment 3: ACE-8 with adaptation
#     exp_label = f"real_ACE8_WithUpdate"
#     print(f"\n{'='*80}")
#     print(f"Running {exp_label}")
#     print(f"{'='*80}\n")
#     result = run_parallel_experiment(
#         config_file='config/grid_4x4_ace_8.json',
#         update_prob_setting=True,
#         purify_setting=False,
#         layered_requests=layered_requests,
#         pregeneration_time_ms=pregeneration_time_ms,
#         request_duration_ms=request_duration_ms,
#         experiment_label=exp_label
#     )
#     result['label'] = exp_label
#     result['config'] = 'ACE-8 (With Update)'
#     result['update_prob'] = True
#     all_results.append(result)
    
#     # Save CSV data
#     print(f"\n{'='*80}")
#     print("SAVING CSV DATA")
#     print(f"{'='*80}\n")
    
#     # Create request info map
#     request_info_map = {}
#     for layer in layered_requests:
#         for req in layer:
#             request_info_map[req[0]] = (req[1], req[2])
    
#     for result in all_results:
#         csv_filename = f"data/{result['label']}.csv"
#         with open(csv_filename, 'w', newline='') as csvfile:
#             writer = csv.writer(csvfile)
#             writer.writerow(['Request_ID', 'Source', 'Destination', 'Latency_ms', 'Fidelity'])
            
#             for reservation, latency in sorted(result['latency_dict'].items(), key=lambda x: x[0].identity):
#                 req_id = reservation.identity
#                 src, dst = request_info_map.get(req_id, ('Unknown', 'Unknown'))
#                 fidelity = result['fidelity_dict'][reservation][0] if reservation in result['fidelity_dict'] else 0
#                 latency_ms = latency / MILLISECOND
#                 writer.writerow([req_id, src, dst, f"{latency_ms:.4f}", f"{fidelity:.6f}"])
#         print(f"Saved {csv_filename}")
    
#     # Create comparison bar chart
#     print(f"\n{'='*80}")
#     print("CREATING COMPARISON PLOT")
#     print(f"{'='*80}\n")
    
#     configs = ['On-Demand', 'ACE (Max 8 qubit, No Update)', 'ACE (Max 8 qubit, With Update)']
#     colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    
#     e2e_latencies = [r['stats']['end_to_end_latency_ms'] for r in all_results]
    
#     fig, ax = plt.subplots(figsize=(10, 6))
#     bars = ax.bar(configs, e2e_latencies, color=colors, alpha=0.8, width=0.6)
    
#     # Add value labels on bars
#     for bar in bars:
#         height = bar.get_height()
#         ax.text(bar.get_x() + bar.get_width()/2., height,
#                f'{height:.1f} ms',
#                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
#     ax.set_ylabel('End-to-End Latency (ms)', fontsize=13, fontweight='bold')
#     ax.set_title(f'E2E Latency Comparison\n({num_layers} layers, {total_requests} requests)', 
#                  fontsize=14, fontweight='bold', pad=15)
#     ax.grid(True, alpha=0.3, axis='y')
#     ax.set_axisbelow(True)
    
#     plt.tight_layout()
#     plt.savefig('plots/real_comparison.png', dpi=300, bbox_inches='tight')
#     print("Saved plots/real_comparison.png")
#     plt.close()
    
#     # Print summary table
#     print(f"\n{'='*80}")
#     print("SUMMARY: real.json Results")
#     print(f"{'='*80}")
#     print(f"{'Configuration':<25} {'E2E Latency (ms)':<20} {'Avg Layer (ms)':<20} {'Completed':<15}")
#     print("-" * 80)
    
#     for result in all_results:
#         stats = result['stats']
#         avg_layer = stats.get('avg_layer_latency_ms', 0)
#         print(f"{result['config']:<25} {stats['end_to_end_latency_ms']:<20.2f} "
#               f"{avg_layer:<20.2f} {stats['completed_requests']}/{stats['total_requests']}")
    
#     print(f"{'='*80}\n")
    
#     # Performance analysis
#     print("PERFORMANCE ANALYSIS")
#     print("-" * 80)
#     ace0_latency = all_results[0]['stats']['end_to_end_latency_ms']
#     ace8_no_update = all_results[1]['stats']['end_to_end_latency_ms']
#     ace8_with_update = all_results[2]['stats']['end_to_end_latency_ms']
    
#     improvement_no_update = ((ace0_latency - ace8_no_update) / ace0_latency) * 100
#     improvement_with_update = ((ace0_latency - ace8_with_update) / ace0_latency) * 100
    
#     print(f"ACE-0 baseline: {ace0_latency:.2f} ms")
#     print(f"ACE-8 (No Update): {ace8_no_update:.2f} ms ({improvement_no_update:+.1f}%)")
#     print(f"ACE-8 (With Update): {ace8_with_update:.2f} ms ({improvement_with_update:+.1f}%)")
#     print(f"{'='*80}\n")
#     print("Experiment complete!")


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
    request_duration_ms = 100  # Maximum duration for each request
    seed = 42
    # Store all results organized by layer count
    results_by_layers = {layers: [] for layers in layer_scenarios}
    
    # Run experiments for each layer scenario
    for num_layers in layer_scenarios:
        print(f"\n{'#'*80}")
        print(f"TESTING WITH {num_layers} LAYERS")
        print(f"{'#'*80}\n")
        
        # Generate or load layered requests for this scenario
        scenario = "random" # "random", "structured","random_single","structured_single"

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
        
        total_requests = sum(len(layer) for layer in layered_requests)
        print(f"\nExperiment configuration:")
        print(f"  Total layers: {len(layered_requests)}")
        print(f"  Total requests: {total_requests}")
        
        # Experiment 1: ACE-0 (on-demand)
        exp_label = f"Parallel_ACE0_{num_layers}layers"
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

        # Experiment 2: ACE-8 without adaptation
        exp_label = f"Parallel_ACE8_NoUpdate_{num_layers}layers"
        print(f"\n--- Running {exp_label} ---")
        result = run_parallel_experiment(
            config_file='config/grid_4x4_ace_2.json',
            update_prob_setting=False,
            purify_setting=False,
            layered_requests=layered_requests,
            pregeneration_time_ms=pregeneration_time_ms,
            request_duration_ms=request_duration_ms,
            experiment_label=exp_label
        )
        result['label'] = exp_label
        result['num_layers'] = num_layers
        result['config'] = 'ACE (Max 8 qubit, No Update)'
        result['update_prob'] = False
        results_by_layers[num_layers].append(result)

        # Experiment 3: ACE-8 with adaptation
        exp_label = f"Parallel_ACE8_WithUpdate_{num_layers}layers"
        print(f"\n--- Running {exp_label} ---")
        result = run_parallel_experiment(
            config_file='config/grid_4x4_ace_2.json',
            update_prob_setting=True,
            purify_setting=False,
            layered_requests=layered_requests,
            pregeneration_time_ms=pregeneration_time_ms,
            request_duration_ms=request_duration_ms,
            experiment_label=exp_label
        )
        result['label'] = exp_label
        result['num_layers'] = num_layers
        result['config'] = 'ACE (Max 8 qubit, With Update)'
        result['update_prob'] = True
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
    # configs = ['ACE-0', 'ACE-8 (No Update)', 'ACE-8 (With Update)']
    configs = ['On-Demand', 'ACE (Max 8 qubit, No Update)', 'ACE (Max 8 qubit, With Update)']
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']  # Blue, Orange, Green
    
    # Extract E2E latencies for each configuration and layer count
    data_for_plot = {config: [] for config in configs}
    
    for num_layers in layer_scenarios:
        for result in results_by_layers[num_layers]:
            config = result['config']
            e2e_latency = result['stats']['end_to_end_latency_ms']
            data_for_plot[config].append(e2e_latency)
    
    # Create the grouped bar chart
    fig, ax = plt.subplots(figsize=(14, 8))
    
    x = np.arange(len(layer_scenarios))  # Label locations
    width = 0.25  # Width of bars
    multiplier = 0
    
    for config, color in zip(configs, colors):
        offset = width * multiplier
        rects = ax.bar(x + offset, data_for_plot[config], width, label=config, color=color, alpha=0.8)
        
        # Add value labels on top of bars
        for rect in rects:
            height = rect.get_height()
            ax.text(rect.get_x() + rect.get_width()/2., height,
                   f'{height:.1f}',
                   ha='center', va='bottom', fontsize=9, fontweight='bold')
        
        multiplier += 1
    
    # Customize the plot
    ax.set_xlabel('Number of Layers', fontsize=14, fontweight='bold')
    ax.set_ylabel('End-to-End Latency (ms)', fontsize=14, fontweight='bold')
    ax.set_title(f'End-to-End Latency Comparison Across Layer Scenarios\n(Max 6 requests/layer)', 
                 fontsize=15, fontweight='bold', pad=20)
    ax.set_xticks(x + width)
    ax.set_xticklabels([f'{n} Layers' for n in layer_scenarios], fontsize=12)
    ax.legend(fontsize=12, loc='upper left')
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_axisbelow(True)
    
    plt.tight_layout()
    plt.savefig('plots/parallel_e2e_latency_comparison.png', dpi=300, bbox_inches='tight')
    print("Saved plots/parallel_e2e_latency_comparison.png")
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
        ace8_no_update = data_for_plot['ACE (Max 8 qubit, No Update)'][idx]
        ace8_with_update = data_for_plot['ACE (Max 8 qubit, With Update)'][idx]

        improvement_no_update = ((ondemand_latency - ace8_no_update) / ondemand_latency) * 100
        improvement_with_update = ((ondemand_latency - ace8_with_update) / ondemand_latency) * 100

        print(f"{num_layers} Layers:")
        print(f"  On-Demand baseline: {ondemand_latency:.2f} ms")
        print(f"  ACE (No Update): {ace8_no_update:.2f} ms ({improvement_no_update:+.1f}%)")
        print(f"  ACE (With Update): {ace8_with_update:.2f} ms ({improvement_with_update:+.1f}%)")
        print()
    
    print(f"{'='*80}\n")
    print("Experiment complete!")




# if __name__ == "__main__":
#     # Create directories
#     os.makedirs('plots', exist_ok=True)
#     os.makedirs('data', exist_ok=True)
#     os.makedirs('log', exist_ok=True)
#     os.makedirs('test', exist_ok=True)
    
#     # Configuration
#     num_layers = 5
#     requests_per_layer = 3  # Up to 3 parallel requests with disjoint cores
#     pregeneration_times = [1.3, 10]  # Test different pre-generation times (ms)
#     request_duration_ms = 100  # Maximum duration for each request
    
#     # Generate or load layered requests
#     request_file = f"test/parallel_layered_requests.json"
    
#     if os.path.exists(request_file):
#         print(f"Loading layered requests from {request_file}...")
#         with open(request_file, "r") as f:
#             layered_requests = json.load(f)
#     else:
#         print(f"Generating structured layered requests...")
#         layered_requests = generate_structured_layered_requests(
#             num_layers=num_layers,
#             memo_size=1,
#             fidelity=0.01,
#             entanglement_number=1,
#             seed=42
#         )

#         layered_requests = generate_layered_requests(
#             num_layers=num_layers,
#             max_requests_per_layer=requests_per_layer,
#             memo_size=1,
#             fidelity=0.01,
#             entanglement_number=1,
#             seed=42
#         )

#         # Save for reproducibility
#         with open(request_file, "w") as f:
#             json.dump(layered_requests, f, indent=2)
#         print(f"Saved layered requests to {request_file}")
    
#     total_requests = sum(len(layer) for layer in layered_requests)
#     print(f"\nExperiment configuration:")
#     print(f"  Total layers: {len(layered_requests)}")
#     print(f"  Total requests: {total_requests}")
#     print(f"  Requests per layer: {[len(layer) for layer in layered_requests]}")
    
#     # Store all results
#     all_results = []
    
#     # Run experiments with different pre-generation times
#     for pregen_time in pregeneration_times:
#         print(f"\n{'#'*80}")
#         print(f"TESTING PRE-GENERATION TIME: {pregen_time} ms")
#         print(f"{'#'*80}\n")
        
#         # Experiment 1: ACE-0 (on-demand)
#         exp_label = f"Parallel_ACE0_PreGen{pregen_time}ms"
#         result = run_parallel_experiment(
#             config_file='config/grid_4x4_ace_0.json',
#             update_prob_setting=False,
#             purify_setting=False,
#             layered_requests=layered_requests,
#             pregeneration_time_ms=pregen_time,
#             request_duration_ms=request_duration_ms,
#             experiment_label=exp_label
#         )
#         result['label'] = exp_label
#         result['pregen_time'] = pregen_time
#         result['config'] = 'ACE-0'
#         result['update_prob'] = False
#         all_results.append(result)
        
#         # Experiment 2: ACE-8 without adaptation
#         exp_label = f"Parallel_ACE5_NoUpdate_PreGen{pregen_time}ms"
#         result = run_parallel_experiment(
#             config_file='config/grid_4x4_ace_5.json',
#             update_prob_setting=False,
#             purify_setting=False,
#             layered_requests=layered_requests,
#             pregeneration_time_ms=pregen_time,
#             request_duration_ms=request_duration_ms,
#             experiment_label=exp_label
#         )
#         result['label'] = exp_label
#         result['pregen_time'] = pregen_time
#         result['config'] = 'ACE-8'
#         result['update_prob'] = False
#         all_results.append(result)
        
#         # Experiment 3: ACE-8 with adaptation
#         exp_label = f"Parallel_ACE5_WithUpdate_PreGen{pregen_time}ms"
#         result = run_parallel_experiment(
#             config_file='config/grid_4x4_ace_5.json',
#             update_prob_setting=True,
#             purify_setting=False,
#             layered_requests=layered_requests,
#             pregeneration_time_ms=pregen_time,
#             request_duration_ms=request_duration_ms,
#             experiment_label=exp_label
#         )
#         result['label'] = exp_label
#         result['pregen_time'] = pregen_time
#         result['config'] = 'ACE-8'
#         result['update_prob'] = True
#         all_results.append(result)
    
#     # Save CSV data
#     print(f"\n{'='*80}")
#     print("SAVING CSV DATA")
#     print(f"{'='*80}\n")
    
#     # Create request info map
#     request_info_map = {}
#     for layer in layered_requests:
#         for req in layer:
#             request_info_map[req[0]] = (req[1], req[2])
    
#     for result in all_results:
#         csv_filename = f"data/{result['label']}.csv"
#         with open(csv_filename, 'w', newline='') as csvfile:
#             writer = csv.writer(csvfile)
#             writer.writerow(['Request_ID', 'Source', 'Destination', 'Latency_ms', 'Fidelity'])
            
#             for reservation, latency in sorted(result['latency_dict'].items(), key=lambda x: x[0].identity):
#                 req_id = reservation.identity
#                 src, dst = request_info_map.get(req_id, ('Unknown', 'Unknown'))
#                 fidelity = result['fidelity_dict'][reservation][0] if reservation in result['fidelity_dict'] else 0
#                 latency_ms = latency / MILLISECOND
#                 writer.writerow([req_id, src, dst, f"{latency_ms:.4f}", f"{fidelity:.6f}"])
#         print(f"Saved {csv_filename}")
    
#     # Create plots
#     print(f"\n{'='*80}")
#     print("CREATING PLOTS")
#     print(f"{'='*80}\n")
    
#     # Plot 1: End-to-end latency comparison
#     fig, ax = plt.subplots(figsize=(12, 7))
    
#     for config_type in ['ACE-0', 'ACE-8 (No Update)', 'ACE-8 (With Update)']:
#         if config_type == 'ACE-0':
#             results_subset = [r for r in all_results if r['config'] == 'ACE-0']
#         elif config_type == 'ACE-8 (No Update)':
#             results_subset = [r for r in all_results if r['config'] == 'ACE-8' and not r['update_prob']]
#         else:
#             results_subset = [r for r in all_results if r['config'] == 'ACE-8' and r['update_prob']]
        
#         pregen_times_plot = [r['pregen_time'] for r in results_subset]
#         e2e_latencies = [r['stats']['end_to_end_latency_ms'] for r in results_subset]
#         ax.plot(pregen_times_plot, e2e_latencies, marker='o', linewidth=2.5, markersize=10, label=config_type)
    
#     ax.set_xlabel('Pre-generation Time (ms)', fontsize=13)
#     ax.set_ylabel('End-to-End Latency (ms)', fontsize=13)
#     ax.set_title(f'Parallel Layered Requests: End-to-End Latency\n({len(layered_requests)} layers, {total_requests} total requests)', fontsize=14, fontweight='bold')
#     ax.legend(fontsize=11)
#     ax.grid(True, alpha=0.3)
#     plt.tight_layout()
#     plt.savefig('plots/parallel_e2e_latency.png', dpi=300)
#     print("Saved plots/parallel_e2e_latency.png")
#     plt.close()
    
#     # Plot 2: Layer latencies for each pre-generation time
#     for pregen_time in pregeneration_times:
#         fig, ax = plt.subplots(figsize=(14, 7))
        
#         results_at_pregen = [r for r in all_results if r['pregen_time'] == pregen_time]
        
#         for result in results_at_pregen:
#             layer_latencies = result['stats']['layer_latencies']
#             if layer_latencies:
#                 layers = sorted(layer_latencies.keys())
#                 latencies = [layer_latencies[l] for l in layers]
#                 ax.plot(layers, latencies, marker='s', linewidth=2, markersize=6, 
#                        label=result['label'], alpha=0.8)
        
#         ax.set_xlabel('Layer Index', fontsize=12)
#         ax.set_ylabel('Layer Latency (ms)', fontsize=12)
#         ax.set_title(f'Layer Latencies (Pre-gen: {pregen_time}ms)', fontsize=13, fontweight='bold')
#         ax.legend(fontsize=10)
#         ax.grid(True, alpha=0.3)
#         plt.tight_layout()
#         plt.savefig(f'plots/parallel_layer_latencies_pregen{pregen_time}ms.png', dpi=300)
#         print(f"Saved plots/parallel_layer_latencies_pregen{pregen_time}ms.png")
#         plt.close()
    
#     # Summary table
#     print(f"\n{'='*80}")
#     print("SUMMARY TABLE")
#     print(f"{'='*80}")
#     print(f"{'Experiment':<45} {'PreGen':<10} {'E2E Lat(ms)':<15} {'Avg Layer':<15} {'Avg Req':<15}")
#     print("-" * 100)
    
#     for result in all_results:
#         stats = result['stats']
#         avg_layer = stats.get('avg_layer_latency_ms', 0)
#         avg_req = stats.get('avg_request_latency_ms', 0)
#         print(f"{result['label']:<45} {result['pregen_time']:<10} "
#               f"{stats['end_to_end_latency_ms']:<15.2f} {avg_layer:<15.2f} {avg_req:<15.2f}")
    
#     print(f"{'='*80}\n")
#     print("Experiment complete!")
