from collections import defaultdict
import numpy as np
from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
from sequence.kernel.process import Process
from sequence.kernel.event import Event
import sequence.utils.log as log
from execution_events import RequestCompleted, RequestRejected, RequestSubmitted
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
# A reservation must start strictly after the RSVP control message reaches the
# remote core.  One picosecond avoids relying on SeQUeNCe's unspecified order
# for equal-time events.
RESERVATION_START_GRACE_PS = 1

# write the new functions here


def serialize_core_conflicts(layered_requests: list) -> tuple[list, list[int]]:
    """Preserve trace order at each core while keeping disjoint work parallel.

    Every request follows all earlier requests touching either endpoint. This
    preserves consecutive hops of a migrating qubit without needing qubit IDs
    in the application tuples.
    """
    batches, origins = [], []
    for layer_index, layer in enumerate(layered_requests):
        layer_batches = []
        last_batch = {}
        for request in layer:
            endpoints = {request[1], request[2]}
            index = 1 + max((last_batch.get(core, -1) for core in endpoints))
            while len(layer_batches) <= index:
                layer_batches.append([])
            layer_batches[index].append(request)
            for core in endpoints:
                last_batch[core] = index
        layer_batches = layer_batches or [[]]
        batches.extend(layer_batches)
        origins.extend([layer_index] * len(layer_batches))
    return batches, origins


class ParallelLayerRequestManager:
    """
    Manages layered parallel requests where:
    - All requests in a layer are submitted simultaneously
    - Wait for ALL requests in current layer to complete before starting next layer
    - Reservation starts after the measured classical-control guard
    - Failed requests are retried in a new layer (treated as congestion)
    """
    
    def __init__(self, timeline, name_to_apps: dict, layered_requests: list,
                 pregeneration_time_ms: float, request_duration_ms: float,
                 compiler_controller=None, recorder=None):
        """
        Args:
            timeline: The simulation timeline
            name_to_apps: Dictionary mapping node names to RequestApp instances
            layered_requests: List of layers, each layer is a list of requests
            recorder: optional execution_events recorder; None disables event emission
            pregeneration_time_ms: optional experiment-specific extra delay in
                milliseconds; zero is the physical default
            request_duration_ms: Maximum duration for each request window in milliseconds
        """
        self.timeline = timeline
        self.recorder = recorder
        self.name_to_apps = name_to_apps
        self.original_layered_requests = layered_requests  # Keep original for reporting
        if compiler_controller is None:
            self.layered_requests = layered_requests.copy()
            self.working_layer_origins = list(range(len(layered_requests)))
        else:
            self.layered_requests, self.working_layer_origins = \
                serialize_core_conflicts(layered_requests)
        self.compiler_controller = compiler_controller
        self.pregeneration_time = int(pregeneration_time_ms * MILLISECOND)
        self.request_duration = int(request_duration_ms * MILLISECOND)
        self.control_plane_guard = self._control_plane_guard()
        
        self.current_layer_index = 0
        self.pending_requests = set()  # Tracks requests in current layer not yet completed
        self.pending_request_data = {}  # Maps request_id to full request tuple
        
        # Track original layer count
        self.original_layer_count = len(layered_requests)
        self.retry_layer_count = 0  # Number of retry layers added
        
        # Tracking metrics
        self.layer_start_times = {}    # Maps layer_index to when reservation requests are submitted
        self.layer_end_times = {}      # Maps layer_index to end time (when last request completes)
        self.request_attempt_submission_times = {}
        self.request_submission_times = {}  # Maps request_id to when reservation request is submitted
        self.request_approval_times = {}  # Maps request_id to when reservation is approved
        self.request_generation_start_times = {}  # Maps request_id to when entanglement generation starts
        self.request_end_times = {}    # Maps request_id to completion time
        self.request_retry_count = {}  # Maps request_id to number of retries
        
        self.series_start_time = None
        self.series_end_time = None

    def _control_plane_guard(self) -> int:
        """Return the configured adjacent RSVP round-trip delay plus 1 ps.

        ACE traces contain elementary adjacent hops.  A start time at ``now``
        is invalid because the RSVP request must reach the neighbour and its
        approval must return before the resource manager can schedule the
        reservation.  The old 5.3 ms constant merely hid this protocol
        requirement.  Read the round-trip delay from the built topology
        instead, so a changed topology/configuration receives the right guard.
        Lightweight unit-test apps need no guard.
        """
        delays = []
        for app in self.name_to_apps.values():
            node = getattr(app, "node", None)
            for channel in getattr(node, "cchannels", {}).values():
                delay = getattr(channel, "delay", None)
                if delay is not None:
                    delays.append(int(delay))
        return 2 * max(delays, default=0) + (RESERVATION_START_GRACE_PS if delays else 0)

    def _reservation_start_time(self, now: int) -> int:
        """Earliest valid RSVP start, plus an explicitly requested extra delay."""
        return now + self.control_plane_guard + self.pregeneration_time
        
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
        
        start_time = self._reservation_start_time(current_time)
        end_time = start_time + self.request_duration
        
        # Determine if this is a retry layer
        is_retry_layer = original_layer is None
        
        print(f"\n--- Layer {self.current_layer_index} {'(RETRY due to congestion)' if is_retry_layer else ''} ---")
        print(f"Current time (reservation submission): {current_time / MILLISECOND:.2f} ms")
        print(f"Classical RSVP guard: {self.control_plane_guard / MILLISECOND:.6f} ms")
        print(f"Additional reservation delay: {self.pregeneration_time / MILLISECOND:.2f} ms")
        print(f"Entanglement generation start: {start_time / MILLISECOND:.2f} ms")
        print(f"Entanglement generation end (window): {end_time / MILLISECOND:.2f} ms")
        print(f"Number of parallel requests: {len(current_layer)}")
        
        # Send all requests in this layer
        for request in current_layer:
            self._submit_request(request, current_time)

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
    
    def _submit_request(self, request, current_time):
        start_time = self._reservation_start_time(current_time)
        end_time = start_time + self.request_duration
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
        self.request_submission_times.setdefault(request_id, current_time)
        self.request_attempt_submission_times[request_id] = current_time
        # Track when entanglement generation will start (after pre-generation time)
        self.request_generation_start_times[request_id] = start_time
        if self.compiler_controller is not None:
            self.compiler_controller.mark_request_start(request_id, current_time)

        if self.recorder is not None:
            self.recorder.record(RequestSubmitted(
                self.timeline.now(), request_id, self.request_retry_count[request_id]))

        # Get app and start request
        app = self.name_to_apps[src_name]
        # Register callbacks before start: a local RSVP rejection is synchronous.
        # Register callbacks
        app.set_reservation_approval_callback(self._on_reservation_approved, request_id)
        app.set_completion_callback(self._on_request_completed, request_id)
        app.set_reservation_rejection_callback(self._on_reservation_rejected, request_id)
        app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, request_id)

        print(f"  Sent request {request_id}: {src_name} -> {dst_name}")


    def _on_reservation_rejected(self, request_id, rejected_at):
        if request_id not in self.pending_requests:
            return
        if self.recorder is not None:
            self.recorder.record(RequestRejected(rejected_at, request_id))
        attempt = self.request_attempt_submission_times[request_id]
        # Retry a definitive rejection with bounded backoff, rather than using
        # the physical-generation timeout as a reservation admission timer.
        event = Event(rejected_at + MILLISECOND,
                      Process(self, "_retry_rejected_request", [request_id, attempt]))
        self.timeline.schedule(event)

    def _retry_rejected_request(self, request_id, attempt):
        if request_id not in self.pending_requests or request_id in self.request_end_times:
            return
        if self.request_attempt_submission_times[request_id] != attempt:
            return
        self._submit_request(self.pending_request_data[request_id], self.timeline.now())
        end_time = self.request_generation_start_times[request_id] + self.request_duration
        self.timeline.schedule(Event(end_time, Process(
            self, "_check_layer_timeout", [self.current_layer_index - 1, end_time])))

    def _check_layer_timeout(self, layer_idx: int, timeout_time: int):
        """
        Check if a layer has timed out (i.e., some requests haven't completed).
        If there are pending requests, create a retry layer for them.
        """
        # Only check if this is the current active layer
        if layer_idx != self.current_layer_index - 1:
            return
        
        if len(self.pending_requests) > 0:
            # A promptly retried rejection has its own later service deadline.
            if any(self.request_generation_start_times[rid] + self.request_duration > timeout_time
                   for rid in self.pending_requests):
                return
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
                self.layer_end_times[layer_idx] = timeout_time
                print(f"Layer {layer_idx} end time set to: {last_completion_time / MILLISECOND:.2f} ms (last successful request)")
            else:
                # No requests completed - use layer start time
                self.layer_end_times[layer_idx] = timeout_time
                print(f"Layer {layer_idx}: No requests completed, end time = start time")
            
            # Create one separate retry layer per pending request, all inserted
            # sequentially before the next original layer
            pending_req_ids = sorted(self.pending_requests)
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
            submission_time = self.request_attempt_submission_times[request_id]
            setup_time_ms = (approval_time - submission_time) / MILLISECOND
            print(f"  Request {request_id} reservation APPROVED at {approval_time / MILLISECOND:.2f} ms (setup time: {setup_time_ms:.2f} ms)")
    
    def _on_request_completed(self, request_id: int, completion_time: int):
        """
        Callback when a request completes.
        When all requests in current layer complete, start the next layer.
        """
        if self.recorder is not None:
            self.recorder.record(RequestCompleted(completion_time, request_id))
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
        """Wall-clock makespan, including buffers, idle layers and retries."""
        if self.series_start_time is None:
            return 0.0
        end = self.series_end_time
        if end is None:
            end = self.timeline.now()
        return (end - self.series_start_time) / MILLISECOND

    def get_layer_latencies(self) -> dict:
        """Actual elapsed time of each finished batch, including timeouts."""
        return {
            index: (end - self.layer_start_times[index]) / MILLISECOND
            for index, end in self.layer_end_times.items()
        }

    def get_individual_latencies(self) -> dict:
        """
        Returns latency for each request in milliseconds.
        Latency = completion_time - first manager submission.

        This is the manager-local metric.  The configured pre-generation
        buffer is real elapsed time after that submission, so it must not be
        subtracted.  Failed attempts and retry waits are included too.  The
        trace-level, cross-scheduler arrival metric is in
        ``latency_metrics.arrival_latencies_ms``.
        """
        latencies = {}
        for req_id in self.request_submission_times:
            if req_id in self.request_end_times:
                submission_time = self.request_submission_times[req_id]
                completion_time = self.request_end_times[req_id]
                latencies[req_id] = (completion_time - submission_time) / MILLISECOND
        return latencies
    
    def get_individual_latencies_breakdown(self) -> dict:
        """Disjoint stages summing to full first-submission-to-completion time.

        ``arrival_to_completion_time_ms`` is retained as a compatibility name
        for the manager-local interval; the trace-level arrival metric is
        calculated separately by ``latency_metrics``.
        """
        breakdown = {}
        for req_id, completion in self.request_end_times.items():
            if req_id not in self.request_approval_times:
                continue
            first = self.request_submission_times[req_id]
            attempt = self.request_attempt_submission_times[req_id]
            generation = self.request_generation_start_times[req_id]
            approval = self.request_approval_times[req_id]
            retry_wait = (attempt - first) / MILLISECOND
            # The start delay is measured, not assumed: it contains the
            # topology-derived RSVP guard and any explicitly requested extra
            # delay after this attempt was submitted.
            initial_buffer = (generation - attempt) / MILLISECOND
            setup = max(0, approval - generation) / MILLISECOND
            service = (completion - max(generation, approval)) / MILLISECOND
            breakdown[req_id] = {
                'arrival_to_completion_time_ms': (completion - first) / MILLISECOND,
                'reservation_start_delay_time_ms': initial_buffer,
                # Compatibility name for metric-version-3 consumers.
                'initial_buffer_time_ms': initial_buffer,
                'retry_wait_time_ms': retry_wait,
                'reservation_setup_time_ms': setup,
                'entanglement_generation_time_ms': service,
                'total_time_ms': initial_buffer + retry_wait + setup + service,
                'retry_count': self.request_retry_count.get(req_id, 0),
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
            'metric_version': 3,
            'request_latency_definition': 'first manager submission to completion; includes initial buffer and retries',
            'end_to_end_latency_definition': 'wall-clock makespan including buffers, idle layers and retries',
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
            
            stats['avg_retry_wait_time_ms'] = np.mean([b['retry_wait_time_ms'] for b in breakdown.values()])
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
                            autonomous_cache_limit: int | None = None,
                            stop_after_workload: bool = False,
                            simulation_stop_time_s: float | None = None,
                            serialize_conflicts: bool = False,
                            recorder=None,
                            scheduler: str = "legacy",
                            request_plan=None,
                            scheduler_options: dict | None = None):
    """
    Run an experiment with parallel layered requests.

    ``scheduler`` is ``"legacy"`` (the historical per-core batches) or ``"per-qubit"``
    (``request_scheduler.QubitOrderedRequestManager``, which releases requests in the order
    their qubits need them).  The latter needs ``request_plan``, the trace's
    ``CompilerRequest`` records; a compiler run supplies them through ``compiler_spec``.
    ``scheduler_options`` are passed to that manager (``admission="poll"|"event"``,
    ``starvation_guard``).

    ``recorder`` is an optional ``execution_events`` recorder.  When given, the request
    manager, every router's reservation timecards and every application report what they
    do to it, for ``invariants.check_events``.  Results are identical with or without it.

    Returns:
        Dictionary with comprehensive results and statistics
    """
    if scheduler not in ("legacy", "per-qubit"):
        raise ValueError(f"unknown scheduler {scheduler!r}; use 'legacy' or 'per-qubit'")
    if scheduler == "per-qubit" and request_plan is None and compiler_spec is None:
        raise ValueError("scheduler 'per-qubit' needs request_plan (the trace's requests)")
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
    # Photon/detector sampling uses each node's own generator, not only the
    # timeline/global RNG. Give every physical node a deterministic seed.
    node_seed_manifest = {}
    for index, name in enumerate(sorted(tl.entities)):
        entity = tl.entities[name]
        if hasattr(entity, "set_seed"):
            node_seed = int(np.random.SeedSequence([seed, index]).generate_state(1)[0])
            entity.set_seed(node_seed)
            node_seed_manifest[name] = node_seed
    
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
        router.recorder = recorder
        name_to_apps[router.name] = app
        router.adaptive_continuous.has_empty_neighbor = True
        router.adaptive_continuous.update_prob = update_prob_setting
        router.resource_manager.purify = purify_setting

    if autonomous_cache_limit is not None and compiler_spec is None:
        # CGP/ACGP: cap the pairs the autonomous protocol may cache, in place of the config file's fixed value
        for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
            router.adaptive_continuous.set_adaptive_max_memory(autonomous_cache_limit)
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
            if not 0 <= compiler_limit <= total_memories:
                raise ValueError(
                    f"compiler memory limit {compiler_limit} must be between zero "
                    f"and the {total_memories} physical memories on {router.name}"
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
            reservation_duration_ms=compiler_spec["reservation_duration_ms"],
        )
        compiler_controller.attach()
    
    # Create parallel layer request manager
    if scheduler == "legacy":
        request_manager = ParallelLayerRequestManager(
            tl, name_to_apps, layered_requests,
            pregeneration_time_ms, request_duration_ms, compiler_controller, recorder
        )
    elif scheduler == "per-qubit":
        if request_plan is None:
            request_plan = compiler_spec["requests"]
        from request_scheduler import QubitOrderedRequestManager     # imports this module
        request_manager = QubitOrderedRequestManager(
            tl, name_to_apps, layered_requests,
            pregeneration_time_ms, request_duration_ms, compiler_controller, recorder,
            requests=request_plan, **(scheduler_options or {}),
        )
    if stop_after_workload:
        # CGP/ACGP keep generating pairs until the stop time.  Ending the run 1 ms after the last request completes
        # leaves every request metric unchanged and makes their pair counts cover the workload's own duration.
        if scheduler != "per-qubit":
            raise ValueError("stop_after_workload needs the per-qubit scheduler")
        def _end_run(when, timeline=tl):
            timeline.stop_time = min(timeline.stop_time, when + MILLISECOND)
        request_manager.on_series_end = _end_run
    # Compiler-driven runs have always used conflict-free batches because a
    # core cannot serve two reservations at once.  Expose the same batching to
    # non-compiler baselines so a comparison can use an identical workload
    # submission schedule without changing the historical default behavior.
    if serialize_conflicts and compiler_controller is None and scheduler == "legacy":
        request_manager.layered_requests, request_manager.working_layer_origins = \
            serialize_core_conflicts(layered_requests)
    
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
    stats["node_seeds"] = node_seed_manifest

    # The adaptive-continuous protocol counts every pair it generates, uses and
    # releases unused, on every router and under every strategy.  Aggregating
    # them here gives one entanglement-efficiency metric defined the same way
    # for the autonomous caches and for the compiler policies; the compiler's
    # own bookkeeping exists only when a compiler controller is attached.
    generated = used = unused = 0
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        protocol = router.adaptive_continuous
        generated += protocol.num_generated_entanglement_pairs
        used += protocol.num_used_entanglement_pairs
        unused += protocol.num_unused_entanglement_pairs
    stats["protocol_generated_pairs"] = generated
    stats["protocol_used_pairs"] = used
    stats["protocol_unused_pairs"] = unused
    stats["protocol_waste_percentage"] = 100 * unused / generated if generated else None

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
    print(f"Classical RSVP guard: {request_manager.control_plane_guard / MILLISECOND:.6f} ms")
    print(f"Additional reservation delay: {pregeneration_time_ms:.2f} ms (included in request latency)")
    print(f"\nStatistics (request latency and makespan include all elapsed time):")
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
        print(f"  Request latency = retry waiting + exposed setup + physical service")
    print(f"{'='*80}\n")
    
    return {
        'stats': stats,
        'latency_dict': latency_dict,
        'fidelity_dict': fidelity_dict,
        'request_manager': request_manager,
        'compiler_metrics': compiler_metrics,
    }
