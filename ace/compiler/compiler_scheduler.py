"""Runtime bridge from an offline compiler schedule to ACE physical protocols."""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from ace.compiler.compiler_trace import CompilerRequest, ScheduledPreparation
from sequence.constants import MILLISECOND
from sequence.kernel.event import Event
from sequence.kernel.process import Process


TRIGGERS = ("layer-start", "predecessor-start")
"""When a planned preparation is launched.  ``layer-start``: when its planned generation layer activates, plus
``trigger_delay_ms`` (the original behaviour with a zero delay).  ``predecessor-start``: a later hop of a qubit's chain is
launched when the previous hop of that chain begins; first hops follow ``layer-start``."""


def _pair_key(pair: tuple) -> tuple:
    return tuple(sorted(pair))


class CompilerPreGenerationController:
    """Launch directed ACE reservations and collect request/EPR-level metrics."""

    def __init__(
        self,
        *,
        timeline,
        routers: dict,
        requests: tuple[CompilerRequest, ...],
        schedule: tuple[ScheduledPreparation, ...],
        strategy: str,
        columns: int,
        planner_blocked: int,
        planner_peak_memory: int | None,
        fidelity: float,
        reservation_duration_ms: float,
        trigger: str = "layer-start",
        trigger_delay_ms: float = 0.0,
        chain_hops_prepared: int | None = None,
        predecessor_distance: int = 1,
        congestion_threshold: int | None = None,
        refill_on_release: bool = False,
        demand_first: bool = False,
        borrow_compiler_pairs: bool = False,
        reuse_compiler_memory: bool = True,
    ):
        if predecessor_distance < 1:
            raise ValueError("predecessor distance must be at least 1")
        if chain_hops_prepared is not None and chain_hops_prepared < 1:
            raise ValueError("chain_hops_prepared must be at least 1 (use the on-demand strategy to prepare nothing)")
        if congestion_threshold is not None and congestion_threshold < 0:
            raise ValueError("congestion_threshold must be non-negative")
        if trigger not in TRIGGERS:
            raise ValueError(f"unknown preparation trigger {trigger!r}; expected one of {TRIGGERS}")
        self.timeline = timeline
        self.refill_on_release = refill_on_release
        self.demand_first = demand_first
        self.admission_guard = None
        self.borrow_compiler_pairs = borrow_compiler_pairs
        self.readiness_observer = None
        self.reuse_compiler_memory = reuse_compiler_memory
        self.progress_yields = 0
        self.routers = routers
        self.requests = {request.request_id: request for request in requests}
        self.strategy = strategy
        self.columns = columns
        self.planner_blocked = planner_blocked
        self.planner_peak_memory = planner_peak_memory
        self.fidelity = fidelity
        self.reservation_duration_ms = reservation_duration_ms
        self.trigger = trigger
        self.trigger_delay = int(trigger_delay_ms * MILLISECOND)
        # position of every request inside its qubit's chain of hops in one layer, and the hop before it
        chains = defaultdict(list)
        for request in requests:
            chains[(request.layer, request.qubit)].append(request)
        self.chain_position, self.chain_predecessor = {}, {}
        for hops in chains.values():
            hops.sort(key=lambda r: r.order)
            for index, request in enumerate(hops):
                self.chain_position[request.request_id] = index
                # the hop whose start launches this one: predecessor_distance positions earlier, if the chain has one
                if index >= predecessor_distance:
                    self.chain_predecessor[request.request_id] = hops[index - predecessor_distance].request_id
        if chain_hops_prepared is not None:
            schedule = tuple(item for item in schedule if self.chain_position[item.request_id] < chain_hops_prepared)
        if congestion_threshold is not None:
            # Local, trace-derived congestion proxy: how many hop-requests target the same original layer as this
            # request.  A busy layer means many migrations contend for memory around the same time; preparing a
            # later hop there holds a card other chains need, which is exactly the effect measured on QFT-96
            # (docs/worklog/README.md, 2026-10-25).  A quiet layer has no such contention, so the full chain is
            # prepared as usual.  The threshold is in requests per layer, swept empirically, not derived from a
            # memory count, because the controller does not know the core count (only mesh ``columns``).
            layer_activity: dict[int, int] = defaultdict(int)
            for request in requests:
                layer_activity[request.layer] += 1
            schedule = tuple(item for item in schedule
                             if self.chain_position[item.request_id] == 0
                             or layer_activity[self.requests[item.request_id].layer] <= congestion_threshold)
        self.waiting_for_predecessor = defaultdict(list)
        self.schedule = {item.request_id: item.generation_layer for item in schedule}
        self.by_generation_layer = defaultdict(list)
        for item in schedule:
            self.by_generation_layer[item.generation_layer].append(item.request_id)

        self.deadlines = {}
        self.pending_preparations = {}
        self.admission_attempts = defaultdict(int)
        self.preparation_retry_events = {}
        self.triggered_generation_layers = set()
        self.launched = set()
        self.accepted = set()
        self.rejections = defaultdict(list)
        self.records = []
        self.active_record_by_pair = {}
        self.utilization_by_request = {}

    def attach(self) -> None:
        for router in self.routers.values():
            router.active = False
            router.adaptive_continuous.compiler_observer = self

    def on_original_layer(self, layer: int) -> None:
        if layer in self.triggered_generation_layers:
            return
        self.triggered_generation_layers.add(layer)
        for request_id in self.by_generation_layer.get(layer, ()):
            if self.trigger == "predecessor-start" and request_id in self.chain_predecessor:
                # a later hop is prepared when the hop before it of the same qubit begins
                self.waiting_for_predecessor[self.chain_predecessor[request_id]].append(request_id)
            elif self.trigger_delay > 0 or self.demand_first:
                self.timeline.schedule(Event(self.timeline.now() + max(1, self.trigger_delay),
                                             Process(self, "launch_preparation", [request_id])))
            else:
                self.launch_preparation(request_id)

    def launch_preparation(self, request_id: int) -> None:
        """Ask the directed protocol for the request's pair now (unless the request has already started)."""
        if request_id in self.deadlines or request_id in self.accepted:
            return
        request = self.requests[request_id]
        self.pending_preparations[request_id] = {
            "request_id": request_id,
            "generation_layer": self.schedule[request_id],
            "target_layer": request.layer,
            "strategy": self.strategy,
            "fidelity": self.fidelity,
            "reservation_duration_ms": self.reservation_duration_ms,
        }
        self.retry_preparation(request_id)

    def retry_preparation(self, request_id):
        self.preparation_retry_events.pop(request_id, None)
        if request_id in self.deadlines or request_id in self.accepted:
            self.pending_preparations.pop(request_id, None)
            return
        metadata = self.pending_preparations.get(request_id)
        if metadata is None:
            return
        request = self.requests[request_id]
        if self.admission_guard is not None and not self.admission_guard(request):
            self.on_preparation_rejected(request_id, "demand_priority")
            return
        self.admission_attempts[request_id] += 1
        self.routers[self._router_name(request.source_core)].adaptive_continuous.request_compiler_pair(
            self._router_name(request.destination_core), metadata)

    def mark_request_start(self, request_id: int, start_time: int) -> None:
        """Record first application submission, before its generation buffer."""
        self.deadlines.setdefault(request_id, start_time)
        self.pending_preparations.pop(request_id, None)
        event = self.preparation_retry_events.pop(request_id, None)
        if event is not None:
            self.timeline.remove_event(event)
        waiting = getattr(self, "waiting_for_predecessor", None)      # absent on bare test doubles
        for successor in (waiting.pop(request_id, ()) if waiting else ()):
            self.launch_preparation(successor)

    def on_resource_release(self) -> None:
        """Retry queued candidates after demand admission has observed a release."""
        if not self.refill_on_release:
            return
        for request_id in sorted(self.pending_preparations,
                                 key=lambda rid: (self.requests[rid].layer,
                                                  self.requests[rid].order)):
            event = self.preparation_retry_events.pop(request_id, None)
            if event is None:
                # No retry means a handshake may still be in flight.
                continue
            self.timeline.remove_event(event)
            replacement = Event(self.timeline.now() + 2,
                                Process(self, "retry_preparation", [request_id]))
            self.preparation_retry_events[request_id] = replacement
            self.timeline.schedule(replacement)

    def _router_name(self, core: int) -> str:
        return f"router_{core // self.columns}_{core % self.columns}"

    def on_preparation_launched(self, request_id: int) -> None:
        self.launched.add(request_id)

    def on_preparation_accepted(self, request_id: int) -> None:
        self.accepted.add(request_id)
        self.pending_preparations.pop(request_id, None)

    def on_preparation_rejected(self, request_id: int, reason: str) -> None:
        self.rejections[request_id].append(reason)
        if (request_id not in self.deadlines and request_id not in self.accepted
                and request_id not in self.preparation_retry_events):
            event = Event(self.timeline.now() + MILLISECOND,
                          Process(self, "retry_preparation", [request_id]))
            self.preparation_retry_events[request_id] = event
            self.timeline.schedule(event)

    def on_pair_generated(
        self, pair: tuple, generated_at: int, fidelity: float, metadata: dict
    ) -> None:
        # Either endpoint can report first. Wake after this instant, including
        # duplicate endpoint reports, so admission can verify bilateral readiness.
        if getattr(self, "readiness_observer", None) is not None:
            self.readiness_observer()
        key = _pair_key(pair)
        active_index = self.active_record_by_pair.get(key)
        if active_index is not None:
            active = self.records[active_index]
            if (active["status"] == "ready" and active["generated_at_ps"] == generated_at
                    and active["target_request_id"] == metadata["target_request_id"]):
                return
            if active["status"] == "ready":
                active["status"] = "expired"
                active["expired_at_ps"] = generated_at
                active["expiry_reason"] = "replaced_after_expiry"

        request = self.requests[metadata["target_request_id"]]
        record = {
            "pair_id": len(self.records),
            "strategy": metadata["strategy"],
            "target_request_id": metadata["target_request_id"],
            "actual_request_id": None,
            "qubit": request.qubit,
            "source": self._router_name(request.source_core),
            "destination": self._router_name(request.destination_core),
            "generation_layer": metadata["generation_layer"],
            "target_layer": metadata["target_layer"],
            "generated_at_ps": generated_at,
            "utilized_at_ps": None,
            "expired_at_ps": None,
            "expiry_reason": None,
            "fidelity_at_creation": fidelity,
            "fidelity_at_utilization": None,
            "prepared_before_request": None,
            "status": "ready",
        }
        self.records.append(record)
        self.active_record_by_pair[key] = record["pair_id"]

    def request_has_ready_pair(self, request_id: int) -> bool:
        request = self.requests[request_id]
        source = self.routers[self._router_name(request.source_core)]
        return source.adaptive_continuous.has_ready_compiler_pair(
            self._router_name(request.destination_core), request_id, self.fidelity)

    def request_can_handoff(self, request_id: int, start: int, end: int) -> bool:
        """Preview both existing leases without claiming a pair or another slot."""
        if not self.reuse_compiler_memory or not self.request_has_ready_pair(request_id):
            return False
        from ace.resources.reservation import ApplicationReservation
        request = self.requests[request_id]
        source, destination = map(self._router_name, (request.source_core, request.destination_core))
        preview = ApplicationReservation(source, destination, start, end, 1, self.fidelity, 1, request_id)
        first = self.routers[source].network_manager.protocol_stack[-1]._handoff_candidate(preview)
        if first is None:
            return False
        preview.compiler_handoff_pair = first[0]
        return self.routers[destination].network_manager.protocol_stack[-1]._handoff_candidate(preview) is not None

    def yield_future_pair_for_progress(self, blocked_cores, eligible_ids) -> bool:
        """Break a future-cache/current-demand cycle using the real remote expiry message.

        Called only when no application is in flight. Never discard a pair for
        an eligible request or cancel a physical generation attempt in progress.
        """
        candidates = []
        for name in blocked_cores:
            protocol = self.routers[name].network_manager.protocol_stack[-1]
            for lease in protocol._reservation_leases.values():
                if not lease["compiler"] or lease["released"]:
                    continue
                reservation = lease["reservation"]
                target = reservation.compiler_target_request_id
                if target in eligible_ids or not self.request_has_ready_pair(target):
                    continue
                remote_name = reservation.responder if reservation.initiator == name else reservation.initiator
                remote = self.routers[remote_name].network_manager.protocol_stack[-1]
                peer_lease = remote._reservation_leases.get(id(reservation))
                if peer_lease is None or peer_lease["released"]:
                    continue
                request = self.requests[target]
                candidates.append((request.layer, request.order, name, remote_name, reservation))
        if not candidates:
            return False
        _, _, name, remote_name, reservation = max(candidates, key=lambda item: item[:3])
        router = self.routers[name]
        if not router.network_manager.protocol_stack[-1].release_reservation(reservation, "demand_progress"):
            return False
        router.adaptive_continuous.send_expire_rules_message(remote_name, reservation)
        self.progress_yields += 1
        return True

    def on_pair_utilized(
        self,
        pair: tuple,
        request_id: int,
        utilized_at: int,
        fidelity: float,
        metadata: dict | None,
    ) -> None:
        if request_id in self.utilization_by_request:
            return
        active_index = self.active_record_by_pair.get(_pair_key(pair))
        if active_index is None:
            return
        record = self.records[active_index]
        if record["status"] != "ready":
            return
        deadline = self.deadlines.get(request_id)
        record.update({
            "actual_request_id": request_id,
            "utilized_at_ps": utilized_at,
            "fidelity_at_utilization": fidelity,
            "prepared_before_request": deadline is not None and record["generated_at_ps"] < deadline,
            "status": "used",
        })
        self.utilization_by_request[request_id] = active_index
        self.active_record_by_pair.pop(_pair_key(pair), None)
        if getattr(self, "borrow_compiler_pairs", False):
            target = record["target_request_id"]
            if target != request_id and target not in self.deadlines:
                # Replenish the displaced future target under the same quota.
                self.accepted.discard(target)
                self.launch_preparation(target)

    def can_borrow_pair(self, target_id: int, request_id: int) -> bool:
        if not self.borrow_compiler_pairs or target_id in self.deadlines:
            return False
        target, current = self.requests[target_id], self.requests[request_id]
        return (target.edge == current.edge and
                (current.layer, current.order) < (target.layer, target.order))

    def on_pair_expired(self, pair: tuple, expired_at: int, reason: str) -> None:
        active_index = self.active_record_by_pair.pop(_pair_key(pair), None)
        if active_index is None:
            return
        record = self.records[active_index]
        if record["status"] == "ready":
            record.update({
                "status": "expired",
                "expired_at_ps": expired_at,
                "expiry_reason": reason,
            })

    def finalize(self, completed_request_ids) -> dict:
        completed = set(completed_request_ids)
        for record in self.records:
            record["target_request_start_ps"] = self.deadlines.get(
                record["target_request_id"]
            )
        for active_index in tuple(self.active_record_by_pair.values()):
            record = self.records[active_index]
            if record["status"] == "ready":
                record["status"] = "remaining"

        utilized = [record for record in self.records if record["status"] == "used"]
        hits = {
            record["actual_request_id"] for record in utilized
            if record["prepared_before_request"]
        }
        compiler_served = {record["actual_request_id"] for record in utilized}
        intended = [
            record for record in utilized
            if record["actual_request_id"] == record["target_request_id"]
        ]
        late_compiler_uses = compiler_served - hits
        expired = [record for record in self.records if record["status"] == "expired"]
        unused = [record for record in self.records if record["status"] in {"expired", "remaining"}]
        creation_fidelities = [record["fidelity_at_creation"] for record in self.records]
        utilization_fidelities = [
            record["fidelity_at_utilization"] for record in utilized
            if record["fidelity_at_utilization"] is not None
        ]
        total_requests = len(self.requests)
        generated = len(self.records)
        return {
            "strategy": self.strategy,
            "requests": total_requests,
            "compiler_progress_yields": getattr(self, "progress_yields", 0),
            "completed_requests": len(completed),
            "scheduled_preparations": len(self.schedule),
            "planner_blocked_preparations": self.planner_blocked,
            "planner_peak_compiler_memory_per_core": self.planner_peak_memory,
            "runtime_admission_attempts": sum(self.admission_attempts.values()),
            "runtime_launched_preparations": len(self.launched),
            "runtime_accepted_preparations": len(self.accepted),
            "runtime_rejected_preparations": len(self.rejections),
            "runtime_rejection_events": sum(map(len, self.rejections.values())),
            "pregenerated_hits": len(hits),
            "pregenerated_success_rate": len(hits) / total_requests if total_requests else None,
            "intended_request_hits": len(intended),
            "intended_request_hit_rate": (
                len(intended) / total_requests if total_requests else None
            ),
            "compiler_not_ready_requests": total_requests - len(hits),
            "late_compiler_pair_uses": len(late_compiler_uses),
            "on_demand_fallbacks": total_requests - len(compiler_served),
            "on_demand_fallback_rate": (
                (total_requests - len(compiler_served)) / total_requests if total_requests else None
            ),
            "generated_compiler_pairs": generated,
            "utilized_compiler_pairs": len(utilized),
            "expired_compiler_pairs": len(expired),
            "remaining_compiler_pairs": sum(
                record["status"] == "remaining" for record in self.records
            ),
            "compiler_expiry_percentage": 100 * len(expired) / generated if generated else 0.0,
            "compiler_waste_percentage": 100 * len(unused) / generated if generated else 0.0,
            "average_fidelity_at_creation": (
                fmean(creation_fidelities) if creation_fidelities else None
            ),
            "average_fidelity_at_utilization": (
                fmean(utilization_fidelities) if utilization_fidelities else None
            ),
            "average_storage_time_ms": (
                fmean(
                    (record["utilized_at_ps"] - record["generated_at_ps"]) / MILLISECOND
                    for record in utilized
                ) if utilized else None
            ),
            "epr_utilization_trace": self.records,
            "rejection_reasons": dict(self.rejections),
        }
