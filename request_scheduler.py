"""Release requests in the order their qubits need them, not one core at a time.

``ParallelLayerRequestManager`` splits every layer into batches with at most one request per
core, so a core never holds more than one request and the memory budget cannot bind.
``QubitOrderedRequestManager`` releases requests under the rules the trace actually implies:

* the hops of one qubit within one layer form a chain in trace order, and a hop is released when
  the previous hop of its chain has completed (the qubit has to arrive before it can move on);
* hops of different qubits are independent, so they are released together and compete for memory
  through the reservation protocol, which is the only thing that limits them;
* layer L+1 starts when every request of layer L has completed (the trace has no gate-level
  dependencies, so the layer boundary is kept as the barrier).

Event order within one simulation instant is not defined by SeQUeNCe (its event list is a heap
ordered by time and priority only), so nothing here relies on one same-instant event running
before another.  The one place where order matters, a timed-out request that must not be
resubmitted before its old booking has expired, is made explicit by resubmitting one picosecond
later.

See docs/plans/ace-request-scheduler-design.md.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from sequence.constants import MILLISECOND
from sequence.kernel.event import Event
from sequence.kernel.process import Process

from execution_events import RequestCompleted
from parallel_core import ParallelLayerRequestManager

# Preserved from the legacy manager so the two are comparable; made configurable in Gate 5.
EMPTY_LAYER_GAP_MS = 5
# The reservation window ends at the instant a request times out.  Resubmitting strictly later
# guarantees the old booking has expired, whatever order SeQUeNCe runs same-instant events in.
TIMEOUT_GRACE_PS = 1


class TraceError(ValueError):
    """The request list contradicts the layered requests or the chain assumption."""


class QubitOrderedRequestManager(ParallelLayerRequestManager):
    """Per-qubit hop order with per-request retry, instead of per-core batches.

    ``requests`` are the trace's ``CompilerRequest`` records (id, layer, qubit, position in layer,
    endpoints); ``layered_requests`` are the same requests in the tuple form ACE's applications take.
    """

    def __init__(self, timeline, name_to_apps: dict, layered_requests: list,
                 pregeneration_time_ms: float, request_duration_ms: float,
                 compiler_controller=None, recorder=None, *, requests: Sequence):
        super().__init__(timeline, name_to_apps, layered_requests, pregeneration_time_ms,
                         request_duration_ms, compiler_controller, recorder)
        # The base class has just split the layers into per-core batches when a compiler
        # controller is attached.  This manager releases whole layers, so undo that.
        self.layered_requests = [list(layer) for layer in layered_requests]
        self.working_layer_origins = list(range(len(layered_requests)))
        self.tuple_by_id = {tuple_[0]: tuple_ for layer in layered_requests for tuple_ in layer}
        self.layer_of, self.predecessor, self.successor = self._plan_chains(requests, layered_requests)
        self.remaining_in_layer = [len(layer) for layer in layered_requests]
        self.request_eligible_times: dict[int, int] = {}
        self.active_layer = -1

    # ------------------------------------------------------------------ planning
    @staticmethod
    def _plan_chains(requests: Sequence, layered_requests: list):
        """Return (layer of each request, predecessor, successor), checking the trace as it goes."""
        ids_in_layers = [tuple_[0] for layer in layered_requests for tuple_ in layer]
        if sorted(ids_in_layers) != sorted(r.request_id for r in requests) or len(set(ids_in_layers)) != len(ids_in_layers):
            raise TraceError("requests and layered_requests do not describe the same set of request ids")
        layer_of: dict[int, int] = {}
        for index, layer in enumerate(layered_requests):
            for tuple_ in layer:
                layer_of[tuple_[0]] = index
        for r in requests:
            if layer_of[r.request_id] != r.layer:
                raise TraceError(f"request {r.request_id} is in layer {layer_of[r.request_id]}, not {r.layer}")

        chains: dict[tuple[int, int], list] = defaultdict(list)
        for r in requests:
            chains[(r.layer, r.qubit)].append(r)
        predecessor: dict[int, int | None] = {r.request_id: None for r in requests}
        successor: dict[int, int | None] = {r.request_id: None for r in requests}
        for (layer, qubit), hops in sorted(chains.items()):
            hops.sort(key=lambda r: r.order)
            for before, after in zip(hops, hops[1:]):
                if before.destination_core != after.source_core:
                    raise TraceError(
                        f"layer {layer} qubit {qubit}: hop {after.request_id} starts at core {after.source_core} "
                        f"but the previous hop {before.request_id} ends at core {before.destination_core}")
                predecessor[after.request_id] = before.request_id
                successor[before.request_id] = after.request_id
        return layer_of, predecessor, successor

    # ------------------------------------------------------------------ releasing
    def start(self):
        """Start the series: activate the first layer."""
        self.series_start_time = self.timeline.now()
        self._activate_layer(0)

    def _activate_layer(self, index: int):
        """Open layer ``index``: tell the controller, then release every request with no predecessor."""
        if index >= len(self.layered_requests):
            return
        now = self.timeline.now()
        self.active_layer = index
        if self.compiler_controller is not None:
            self.compiler_controller.on_original_layer(index)
        self.layer_start_times[index] = now
        layer = self.layered_requests[index]
        if not layer:
            self._finish_layer(index, now, gap_ms=EMPTY_LAYER_GAP_MS)
            return
        for tuple_ in layer:
            if self.predecessor[tuple_[0]] is None:
                self._release(tuple_[0], now)

    def _release(self, request_id: int, now: int):
        """The request became eligible: submit it and arm its timeout."""
        self.request_eligible_times[request_id] = now
        self._submit_and_arm(self.tuple_by_id[request_id], now)

    def _submit_and_arm(self, request, now: int):
        request_id = request[0]
        self._submit_request(request, now)
        attempt = self.request_retry_count[request_id]
        deadline = self.request_generation_start_times[request_id] + self.request_duration
        self.timeline.schedule(Event(deadline, Process(self, "_request_timeout", [request_id, attempt])))

    def _release_successor(self, request_id: int):
        self._release(request_id, self.timeline.now())

    # ------------------------------------------------------------------ outcomes
    def _on_request_completed(self, request_id: int, completion_time: int):
        """Record the completion, release the next hop of the chain, and close the layer if done."""
        if self.recorder is not None:
            self.recorder.record(RequestCompleted(completion_time, request_id))
        if request_id in self.request_end_times:
            return          # a second completion is reported by the invariant checker, and counted once
        self.request_end_times[request_id] = completion_time
        self.pending_requests.discard(request_id)
        self.pending_request_data.pop(request_id, None)

        following = self.successor[request_id]
        if following is not None:
            self.timeline.schedule(Event(completion_time, Process(self, "_release_successor", [following])))

        layer = self.layer_of[request_id]
        self.remaining_in_layer[layer] -= 1
        if self.remaining_in_layer[layer] == 0:
            self._finish_layer(layer, completion_time, gap_ms=0)

    def _finish_layer(self, layer: int, when: int, *, gap_ms: float):
        self.layer_end_times[layer] = when
        if layer + 1 >= len(self.layered_requests):
            self.series_end_time = when
            return
        self.timeline.schedule(Event(when + int(gap_ms * MILLISECOND),
                                     Process(self, "_activate_layer", [layer + 1])))

    def _retry_rejected_request(self, request_id: int, attempt: int):
        """A rejected request tries again on its own; no other request waits for it."""
        if request_id not in self.pending_requests or request_id in self.request_end_times:
            return
        if self.request_attempt_submission_times[request_id] != attempt:
            return
        self._submit_and_arm(self.pending_request_data[request_id], self.timeline.now())

    def _request_timeout(self, request_id: int, attempt: int):
        """The attempt's reservation window has ended without a pair: resubmit this request alone."""
        if request_id not in self.pending_requests or self.request_retry_count[request_id] != attempt:
            return
        self.timeline.schedule(Event(self.timeline.now() + TIMEOUT_GRACE_PS,
                                     Process(self, "_resubmit_after_timeout", [request_id, attempt])))

    def _resubmit_after_timeout(self, request_id: int, attempt: int):
        if request_id not in self.pending_requests or self.request_retry_count[request_id] != attempt:
            return
        self._submit_and_arm(self.pending_request_data[request_id], self.timeline.now())

    # ------------------------------------------------------------------ statistics
    def get_individual_latencies_breakdown(self) -> dict:
        """The legacy breakdown plus how long each request waited for its predecessor."""
        breakdown = super().get_individual_latencies_breakdown()
        for request_id, parts in breakdown.items():
            layer_start = self.layer_start_times[self.layer_of[request_id]]
            parts["dependency_wait_time_ms"] = (self.request_eligible_times[request_id] - layer_start) / MILLISECOND
        return breakdown
