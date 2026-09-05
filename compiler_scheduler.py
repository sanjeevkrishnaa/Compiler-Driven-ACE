"""Runtime bridge from an offline compiler schedule to ACE physical protocols."""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from compiler_trace import CompilerRequest, ScheduledPreparation
from sequence.constants import MILLISECOND


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
        planner_peak_memory: int,
        fidelity: float,
        reservation_duration_ms: float,
    ):
        self.timeline = timeline
        self.routers = routers
        self.requests = {request.request_id: request for request in requests}
        self.strategy = strategy
        self.columns = columns
        self.planner_blocked = planner_blocked
        self.planner_peak_memory = planner_peak_memory
        self.fidelity = fidelity
        self.reservation_duration_ms = reservation_duration_ms
        self.schedule = {item.request_id: item.generation_layer for item in schedule}
        self.by_generation_layer = defaultdict(list)
        for item in schedule:
            self.by_generation_layer[item.generation_layer].append(item.request_id)

        self.deadlines = {}
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
            request = self.requests[request_id]
            source = self._router_name(request.source_core)
            destination = self._router_name(request.destination_core)
            self.routers[source].adaptive_continuous.request_compiler_pair(
                destination,
                {
                    "request_id": request_id,
                    "generation_layer": layer,
                    "target_layer": request.layer,
                    "strategy": self.strategy,
                    "fidelity": self.fidelity,
                    "reservation_duration_ms": self.reservation_duration_ms,
                },
            )

    def mark_request_start(self, request_id: int, start_time: int) -> None:
        self.deadlines.setdefault(request_id, start_time)

    def _router_name(self, core: int) -> str:
        return f"router_{core // self.columns}_{core % self.columns}"

    def on_preparation_launched(self, request_id: int) -> None:
        self.launched.add(request_id)

    def on_preparation_accepted(self, request_id: int) -> None:
        self.accepted.add(request_id)

    def on_preparation_rejected(self, request_id: int, reason: str) -> None:
        self.rejections[request_id].append(reason)

    def on_pair_generated(
        self, pair: tuple, generated_at: int, fidelity: float, metadata: dict
    ) -> None:
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
            "prepared_before_request": deadline is not None and record["generated_at_ps"] <= deadline,
            "status": "used",
        })
        self.utilization_by_request[request_id] = active_index
        self.active_record_by_pair.pop(_pair_key(pair), None)

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
            "completed_requests": len(completed),
            "scheduled_preparations": len(self.schedule),
            "planner_blocked_preparations": self.planner_blocked,
            "planner_peak_compiler_memory_per_core": self.planner_peak_memory,
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
