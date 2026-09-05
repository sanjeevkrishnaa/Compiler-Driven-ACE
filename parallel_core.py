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
from parallel_core_helper import *
from pathlib import Path
from tempfile import NamedTemporaryFile

SECOND = int(1e12)

# write the new functions here



class ParallelLayerRequestManager:
    """
    Manages layered parallel requests where:
    - All requests in a layer are submitted simultaneously
    - Wait for ALL requests in current layer to complete before starting next layer
    - Pre-generation time applied before each layer
    - Failed requests are retried in a new layer (treated as congestion)
    """
    
    def __init__(self, timeline, name_to_apps: dict, layered_requests: list,
                 pregeneration_time_ms: float, request_duration_ms: float,
                 compiler_controller=None):
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
        self.working_layer_origins = list(range(len(layered_requests)))
        self.compiler_controller = compiler_controller
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
        original_layer = self.working_layer_origins[self.current_layer_index]
        if self.compiler_controller is not None and original_layer is not None:
            self.compiler_controller.on_original_layer(original_layer)
        
        # Track when we actually submit this layer (includes reservation setup time)
        self.layer_start_times[self.current_layer_index] = current_time
        
        # Apply pre-generation time
        start_time = current_time + self.pregeneration_time
        end_time = start_time + self.request_duration
        
        # Determine if this is a retry layer
        is_retry_layer = original_layer is None
        
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
            if self.compiler_controller is not None:
                self.compiler_controller.mark_request_start(request_id, start_time)
            
            # Get app and start request
            app = self.name_to_apps[src_name]
            app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, request_id)
            
            # Register callbacks
            app.set_reservation_approval_callback(self._on_reservation_approved, request_id)
            app.set_completion_callback(self._on_request_completed, request_id)
            
            print(f"  Sent request {request_id}: {src_name} -> {dst_name}")
        
        print(f"Layer {self.current_layer_index}: Submitted {len(current_layer)} requests")
        
        # Handle empty layers - immediately proceed to next layer
        if len(current_layer) == 0:
            self.layer_end_times[self.current_layer_index] = current_time
            self.current_layer_index += 1
            
            # Check if we've processed all layers
            if self.current_layer_index >= len(self.layered_requests):
                self.series_end_time = current_time
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
                # Schedule next layer after a 5ms delay
                next_layer_time = current_time + 5 * MILLISECOND
                print(f"Empty layer - scheduling next layer {self.current_layer_index} at {next_layer_time / MILLISECOND:.2f} ms...\n")
                process = Process(self, "_send_layer", [])
                event = Event(next_layer_time, process)
                self.timeline.schedule(event)
            return
        
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
            
            # Create one separate retry layer per pending request, all inserted
            # sequentially before the next original layer
            pending_req_ids = list(self.pending_requests)
            self.pending_requests.clear()
            
            for i, req_id in enumerate(pending_req_ids):
                if req_id in self.pending_request_data:
                    retry_layer = [self.pending_request_data[req_id]]
                    self.layered_requests.insert(self.current_layer_index + i, retry_layer)
                    self.working_layer_origins.insert(self.current_layer_index + i, None)
                    self.retry_layer_count += 1
                    print(f"Created retry layer {self.current_layer_index + i} with request {req_id}")
            
            print(f"Inserted {len(pending_req_ids)} individual retry layers starting at index {self.current_layer_index}")
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
            print(f"  Request {request_id} reservation APPROVED at {approval_time / MILLISECOND:.2f} ms (setup time: {setup_time_ms:.2f} ms)")
    
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
            is_retry_layer = self.working_layer_origins[layer_idx] is None
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
                            request_duration_ms: float, experiment_label: str,
                            seed: int = 0, compiler_spec: dict | None = None,
                            total_memories_per_core: int | None = None,
                            simulation_stop_time_s: float | None = None):
    """
    Run an experiment with parallel layered requests.
    
    Returns:
        Dictionary with comprehensive results and statistics
    """
    log_filename = f'log/log_{experiment_label.replace(" ", "_")}'
    
    topology_config_file = config_file
    temporary_config = None
    if total_memories_per_core is not None or simulation_stop_time_s is not None:
        if simulation_stop_time_s is not None and simulation_stop_time_s <= 0:
            raise ValueError("simulation stop time must be positive")
        if total_memories_per_core is not None and total_memories_per_core < 1:
            raise ValueError("total memories per core must be positive")
        config = json.loads(Path(config_file).read_text(encoding="utf-8"))
        if total_memories_per_core is not None:
            for node_config in config["nodes"]:
                if "memo_size" in node_config:
                    node_config["memo_size"] = total_memories_per_core
        if simulation_stop_time_s is not None:
            config["stop_time"] = simulation_stop_time_s * SECOND
        temporary_config = NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        )
        json.dump(config, temporary_config)
        temporary_config.close()
        topology_config_file = temporary_config.name
    try:
        network_topo = RouterNetTopoAdaptive(topology_config_file)
    finally:
        if temporary_config is not None:
            Path(temporary_config.name).unlink(missing_ok=True)
    tl = network_topo.get_timeline()
    tl.seed(seed)
    
    # Set up logging
    # log.set_logger(__name__, tl, log_filename)
    # log.set_logger_level('INFO')
    # modules = ['adaptive_continuous', 'request_app', 'swapping', 'network_manager',
    #            'resource_manager', 'main', 'rule_manager', 'generation', 'purification', 'reservation']
    # for module in modules:
    #     log.track_module(module)
    
    # Configure routers and applications
    name_to_apps = {}
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        app = RequestAppLatencyParallel(router)
        name_to_apps[router.name] = app
        router.adaptive_continuous.has_empty_neighbor = True
        router.adaptive_continuous.update_prob = update_prob_setting
        router.resource_manager.purify = purify_setting

    compiler_controller = None
    if compiler_spec is not None:
        from compiler_scheduler import CompilerPreGenerationController
        routers = {
            router.name: router
            for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER)
        }
        compiler_limit = compiler_spec["compiler_memories_per_core"]
        for router in routers.values():
            total_memories = len(router.resource_manager.memory_manager)
            if not 0 <= compiler_limit < total_memories:
                raise ValueError(
                    f"compiler memory limit {compiler_limit} must leave at least one "
                    f"on-demand memory out of {total_memories} on {router.name}"
                )
            router.adaptive_continuous.set_adaptive_max_memory(compiler_limit)
        compiler_controller = CompilerPreGenerationController(
            timeline=tl,
            routers=routers,
            requests=compiler_spec["requests"],
            schedule=compiler_spec["schedule"],
            strategy=compiler_spec["strategy"],
            columns=compiler_spec["columns"],
            planner_blocked=compiler_spec["planner_blocked"],
            planner_peak_memory=compiler_spec["planner_peak_memory"],
            fidelity=compiler_spec["fidelity"],
        )
        compiler_controller.attach()
    
    # Create parallel layer request manager
    request_manager = ParallelLayerRequestManager(
        tl, name_to_apps, layered_requests,
        pregeneration_time_ms, request_duration_ms, compiler_controller
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
    compiler_metrics = None
    if compiler_controller is not None:
        compiler_metrics = compiler_controller.finalize(request_manager.request_end_times)
        stats['compiler'] = {
            key: value for key, value in compiler_metrics.items()
            if key not in {'epr_utilization_trace', 'rejection_reasons'}
        }
    
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
        'request_manager': request_manager,
        'compiler_metrics': compiler_metrics,
    }
