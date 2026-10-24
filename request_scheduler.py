"""Release requests in the order their qubits need them, not one core at a time.

``ParallelLayerRequestManager`` splits every layer into batches with at most one request per
core, so a core never holds more than one request and the memory budget cannot bind.
``QubitOrderedRequestManager`` releases requests under the rules the trace actually implies:

* the hops of one qubit within one layer form a chain in trace order, and a hop is released when
  the previous hop of its chain has completed (the qubit has to arrive before it can move on);
* hops of different qubits are independent, so they are released together and compete for memory;
* layer L+1 starts when every request of layer L has completed (the trace has no gate-level
  dependencies, so the layer boundary is kept as the barrier).

Admission, that is when a released request is actually handed to the reservation protocol, has
two modes.

``poll``   The request is submitted at once.  If a core has no free memory the protocol rejects
           it and it tries again every millisecond.  Two requests that need each other's only
           memory (a swap between two cores with one memory each) reject each other on the same
           period for ever: a livelock, measured in test/test_compiler_scheduler_admission.py.
``event``  A request is submitted only when both of its cores have a memory free for its whole
           window, counting the requests already admitted but not yet booked, and the oldest
           request that fits is admitted first.  A core releasing a booking is what triggers the
           next admission.  Nothing waits holding a memory while it waits for another, so there is
           no hold-and-wait, hence no deadlock; with ``starvation_guard`` a request that cannot
           be admitted yet keeps the free memory it would need, so younger requests cannot take
           it for ever.

The scheduler is modelled as a central classical controller that reads each core's reservation
table without delay.  That is an assumption about the system, not a measurement.

Event order within one simulation instant is not defined by SeQUeNCe (its event list is a heap
ordered by time and priority only), so nothing here relies on one same-instant event running
before another: whatever must come after is scheduled one picosecond later.

See docs/plans/ace-request-scheduler-design.md.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from sequence.constants import MILLISECOND
from sequence.kernel.event import Event
from sequence.kernel.process import Process

from execution_events import RequestCompleted, RequestRejected
from parallel_core import ParallelLayerRequestManager
from reservation import ApplicationReservation

# Preserved from the legacy manager so the two are comparable; made configurable in Gate 5.
EMPTY_LAYER_GAP_MS = 5
RETRY_PERIOD = MILLISECOND          # the legacy retry cadence, used after a physical rejection
# The reservation window ends at the instant a request times out, and a release is reported at the
# instant it happens.  Acting strictly later guarantees the booking is gone, whatever order SeQUeNCe
# runs same-instant events in.
GRACE_PS = 1
ADMISSION_MODES = ("poll", "event")


class TraceError(ValueError):
    """The request list contradicts the layered requests, the chain assumption, or the hardware."""


class QubitOrderedRequestManager(ParallelLayerRequestManager):
    """Per-qubit hop order with per-request retry, instead of per-core batches.

    ``requests`` are the trace's ``CompilerRequest`` records (id, layer, qubit, position in layer,
    endpoints); ``layered_requests`` are the same requests in the tuple form ACE's applications take.
    """

    def __init__(self, timeline, name_to_apps: dict, layered_requests: list,
                 pregeneration_time_ms: float, request_duration_ms: float,
                 compiler_controller=None, recorder=None, *, requests: Sequence,
                 admission: str = "event", starvation_guard: bool = True):
        if admission not in ADMISSION_MODES:
            raise ValueError(f"admission must be one of {ADMISSION_MODES}, got {admission!r}")
        super().__init__(timeline, name_to_apps, layered_requests, pregeneration_time_ms,
                         request_duration_ms, compiler_controller, recorder)
        # The base class has just split the layers into per-core batches when a compiler
        # controller is attached.  This manager releases whole layers, so undo that.
        self.layered_requests = [list(layer) for layer in layered_requests]
        self.working_layer_origins = list(range(len(layered_requests)))
        self.admission = admission
        self.starvation_guard = starvation_guard

        self.tuple_by_id = {tuple_[0]: tuple_ for layer in layered_requests for tuple_ in layer}
        self.layer_of, self.predecessor, self.successor = self._plan_chains(requests, layered_requests)
        self.position = {r.request_id: (r.layer, r.order) for r in requests}
        self.remaining_in_layer = [len(layer) for layer in layered_requests]
        self.request_eligible_times: dict[int, int] = {}
        self.request_admission_times: dict[int, int] = {}      # first admission
        self.active_layer = -1

        self.waiting: dict[int, int] = {}      # released, not admitted: request id -> time it became eligible
        self.in_flight: set[int] = set()       # admitted, not completed
        self._admission_scheduled = False
        self._admitting = False
        if admission == "event":
            self._require_the_hardware_can_ever_serve(requests)
            for app in name_to_apps.values():
                app.node.release_observer = self._on_release

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

    def _require_the_hardware_can_ever_serve(self, requests: Sequence):
        """Fail now, not after a retry loop, if a request needs more memories than a core has."""
        for r in requests:
            _, source, destination, memo_size, *_ = self.tuple_by_id[r.request_id]
            for name in (source, destination):
                available = len(self._cards(name))
                if memo_size > available:
                    raise TraceError(f"request {r.request_id} needs {memo_size} memories on {name}, "
                                     f"which has {available}; it could never be admitted")

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
        """The request became eligible: from here on it counts as waiting, whether or not it can start."""
        self.request_eligible_times[request_id] = now
        # A request's latency runs from the moment it was eligible, so time spent waiting for a
        # memory is part of it.  (_submit_request keeps the first value it finds.)
        self.request_submission_times.setdefault(request_id, now)
        if self.admission == "poll":
            self._admit(request_id, now)
        else:
            self.waiting[request_id] = now
            self._schedule_admission(0)

    def _release_successor(self, request_id: int):
        self._release(request_id, self.timeline.now())

    def _admit(self, request_id: int, now: int):
        """Hand the request to the reservation protocol."""
        self.waiting.pop(request_id, None)
        self.in_flight.add(request_id)
        self.request_admission_times.setdefault(request_id, now)
        self._submit_and_arm(self.tuple_by_id[request_id], now)

    def _submit_and_arm(self, request, now: int):
        request_id = request[0]
        self._submit_request(request, now)
        attempt = self.request_retry_count[request_id]
        deadline = self.request_generation_start_times[request_id] + self.request_duration
        self.timeline.schedule(Event(deadline, Process(self, "_request_timeout", [request_id, attempt])))

    # ------------------------------------------------------------------ event-driven admission
    def _cards(self, name: str):
        return self.name_to_apps[name].node.network_manager.protocol_stack[-1].timecards

    @staticmethod
    def _overlaps(card, start: int, end: int) -> bool:
        return any(max(r.start_time, start) <= min(r.end_time, end) for r in card.reservations)

    def _booked_here(self, name: str, request_id: int) -> bool:
        return any(isinstance(r, ApplicationReservation) and r.identity == request_id
                   for card in self._cards(name) for r in card.reservations)

    def _free_memories(self, name: str, start: int, end: int) -> int:
        """Memories of ``name`` with nothing booked in [start, end], less those already promised.

        A request admitted a moment ago has booked its initiator at once but its responder only
        when the reservation message arrives, so until then the booking is not in the table and
        has to be counted here.
        """
        free = sum(1 for card in self._cards(name) if not self._overlaps(card, start, end))
        promised = sum(1 for rid in self.in_flight
                       if name in self.tuple_by_id[rid][1:3] and not self._booked_here(name, rid))
        return free - promised

    def _schedule_admission(self, delay_ps: int):
        if self._admission_scheduled:
            return
        self._admission_scheduled = True
        self.timeline.schedule(Event(self.timeline.now() + delay_ps, Process(self, "_try_admit", [])))

    def _on_release(self, name: str):
        """A core released a booking: some waiting request may now fit."""
        if self.waiting and not self._admitting:
            self._schedule_admission(GRACE_PS)

    def _try_admit(self):
        """Admit, oldest first, every waiting request whose two cores each have a memory free."""
        self._admission_scheduled = False
        if not self.waiting:
            return
        now = self.timeline.now()
        start = now + self.pregeneration_time
        end = start + self.request_duration
        free: dict[str, int] = {}

        def available(name):
            if name not in free:
                free[name] = self._free_memories(name, start, end)
            return free[name]

        self._admitting = True
        try:
            for request_id in sorted(self.waiting, key=lambda r: (self.waiting[r], self.position[r])):
                _, source, destination, need, *_ = self.tuple_by_id[request_id]
                if available(source) >= need and available(destination) >= need:
                    free[source] -= need
                    free[destination] -= need
                    self._admit(request_id, now)
                elif self.starvation_guard:
                    for name in (source, destination):          # keep what it would need
                        if available(name) >= need:
                            free[name] -= need
        finally:
            self._admitting = False
        if self.waiting and not self.in_flight:
            # Nothing is running whose end could wake the waiters: a booking that blocks them
            # can only end with time, which no event reports.
            self._schedule_admission(RETRY_PERIOD)

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
        self.in_flight.discard(request_id)

        following = self.successor[request_id]
        if following is not None:
            self.timeline.schedule(Event(completion_time, Process(self, "_release_successor", [following])))
        if self.admission == "event" and self.waiting:
            self._schedule_admission(GRACE_PS)

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

    def _on_reservation_rejected(self, request_id, rejected_at):
        """The protocol refused the attempt.  Poll mode retries it in place; event mode puts it back in line."""
        if self.admission == "poll":
            return super()._on_reservation_rejected(request_id, rejected_at)
        if request_id not in self.pending_requests:
            return
        if self.recorder is not None:
            self.recorder.record(RequestRejected(rejected_at, request_id))
        self.in_flight.discard(request_id)
        self.waiting[request_id] = self.request_eligible_times[request_id]
        self._schedule_admission(RETRY_PERIOD)

    def _retry_rejected_request(self, request_id: int, attempt: int):
        """Poll mode: a rejected request tries again on its own; no other request waits for it."""
        if request_id not in self.pending_requests or request_id in self.request_end_times:
            return
        if self.request_attempt_submission_times[request_id] != attempt:
            return
        self._submit_and_arm(self.pending_request_data[request_id], self.timeline.now())

    def _request_timeout(self, request_id: int, attempt: int):
        """The attempt's reservation window has ended without a pair: resubmit this request alone."""
        if request_id not in self.pending_requests or self.request_retry_count[request_id] != attempt:
            return
        self.timeline.schedule(Event(self.timeline.now() + GRACE_PS,
                                     Process(self, "_resubmit_after_timeout", [request_id, attempt])))

    def _resubmit_after_timeout(self, request_id: int, attempt: int):
        if request_id not in self.pending_requests or self.request_retry_count[request_id] != attempt:
            return
        if request_id not in self.in_flight:
            return          # it was put back in line after a rejection; admission will resubmit it
        self._submit_and_arm(self.pending_request_data[request_id], self.timeline.now())

    # ------------------------------------------------------------------ statistics
    def get_individual_latencies_breakdown(self) -> dict:
        """The legacy breakdown plus the time each request waited for its predecessor and for admission."""
        breakdown = super().get_individual_latencies_breakdown()
        for request_id, parts in breakdown.items():
            layer_start = self.layer_start_times[self.layer_of[request_id]]
            parts["dependency_wait_time_ms"] = (self.request_eligible_times[request_id] - layer_start) / MILLISECOND
            parts["admission_wait_time_ms"] = (
                self.request_admission_times[request_id] - self.request_eligible_times[request_id]) / MILLISECOND
        return breakdown
