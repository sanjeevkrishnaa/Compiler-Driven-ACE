#!/usr/bin/env python3
"""Why is a policy slower than on-demand?  One run, with the memory occupancy and wait decomposition measured.

Runs run_trace_comparison.main in-process, captures the simulator result, and writes a JSON record with

* latency, admission wait and generation time, split by whether the request was served by a pre-generated pair
  (hit) or fell back to on-demand generation;
* for pre-generated pairs: the time they sat ready in memory (utilized - generated);
* per-core memory occupancy over time: cached ready pairs plus requests in service, as a time-weighted histogram
  over the interval in which the core was busy at all.

Occupancy is reconstructed from the controller's pair records and the request manager's timestamps; it does not
touch the simulator.  A core's occupancy counts a memory per endpoint of every cached pair and of every request in
service (generation start to completion); relay hops count at both of their cores because every request is a hop.

    python tools/diagnostics/occupancy.py --out FILE.json -- <run_trace_comparison arguments>
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_trace_comparison as runner                                   # noqa: E402
from compiler_trace import router_name                                  # noqa: E402
from execution_events import Booked, ListRecorder, RequestRejected, Unbooked           # noqa: E402
from reservation import ADAPTIVE, ReservationAdaptive                                        # noqa: E402

PS_PER_MS = 10**9


class AdmissionLog:
    """Wraps QubitOrderedRequestManager._free_memories: at each admission check, which bookings made a card unavailable.

    A card is unavailable to the request if any reservation on it overlaps the request's window; the log
    attributes each blocked card to the kind of the overlapping reservation (autonomous > compiler > application).
    """

    def __init__(self):
        self.checks = []                      # (now, name, cards, free, promised, blocking)

    def install(self, manager_class):
        log = self
        original = manager_class._free_memories

        def wrapped(self, name, start, end):
            result = original(self, name, start, end)
            blocking = []
            for card in self._cards(name):
                hits = [r for r in card.reservations if max(r.start_time, start) <= min(r.end_time, end)]
                if not hits:
                    continue
                kinds = {("autonomous" if r.compiler_target_request_id is None else "compiler")
                         if isinstance(r, ReservationAdaptive) else "application" for r in hits}
                kind = "autonomous" if "autonomous" in kinds else ("compiler" if "compiler" in kinds else "application")
                longest = max(hits, key=lambda r: r.end_time - r.start_time)
                blocking.append((kind, (longest.end_time - longest.start_time) / PS_PER_MS,
                                 (longest.start_time - self.timeline.now()) / PS_PER_MS, len(hits)))
            log.checks.append((self.timeline.now(), name, len(self._cards(name)), result, blocking))
            return result
        manager_class._free_memories = wrapped
        return original

    def summary(self) -> dict:
        blocked = [c for c in self.checks if c[3] <= 0]
        kinds: dict = defaultdict(int)
        windows: dict = defaultdict(list)
        offsets: dict = defaultdict(list)
        for _, _, _, _, blocking in blocked:
            for kind, window, offset, _ in blocking:
                kinds[kind] += 1
                windows[kind].append(window)
                offsets[kind].append(offset)
        total = sum(kinds.values())
        return {"admission_checks": len(self.checks), "checks_that_found_no_free_memory": len(blocked),
                "blocked_cards_by_kind_share": {k: round(v / total, 4) for k, v in kinds.items()} if total else {},
                "blocking_window_ms_mean": {k: round(fmean(v), 2) for k, v in windows.items()},
                "blocking_window_start_offset_ms_mean": {k: round(fmean(v), 2) for k, v in offsets.items()},
                "mean_cards_per_core_blocked_when_stuck": round(total / len(blocked), 2) if blocked else None}


def histogram(intervals_by_core: dict) -> dict:
    """intervals: core -> list of (start, end).  Time-weighted share of busy time spent at each occupancy level."""
    weight: dict[int, float] = defaultdict(float)
    peak = 0
    for intervals in intervals_by_core.values():
        events = sorted([(s, 1) for s, e in intervals if e > s] + [(e, -1) for s, e in intervals if e > s])
        level, last = 0, None
        for time, step in events:
            if last is not None and level > 0:
                weight[level] += time - last
            level += step
            peak = max(peak, level)
            last = time
    total = sum(weight.values())
    return {"share_of_busy_time_by_level": {k: round(v / total, 4) for k, v in sorted(weight.items())} if total else {},
            "peak": peak, "mean_level_when_busy": round(sum(k * v for k, v in weight.items()) / total, 3) if total else None}


def bookings(events, horizon: int) -> dict:
    """Memory-card bookings, which is what admission checks.  A booking runs from its Booked to its Unbooked event.

    kind: application (a trace request), compiler (a preparation for request id >= 0) or autonomous (CGP/ACGP).
    Reports, per kind, the number and mean hold, and the time-weighted share of busy card time and card level.
    """
    open_: dict = {}
    spans: dict = defaultdict(list)                       # kind -> [(node, card, start, end)]
    for e in events:
        if isinstance(e, Booked):
            kind = "application" if e.kind != ADAPTIVE else ("compiler" if e.request_id >= 0 else "autonomous")
            open_[(e.node, e.memory_index, e.reservation_id)] = (kind, e.time_ps)
        elif isinstance(e, Unbooked):
            kind, start = open_.pop((e.node, e.memory_index, e.reservation_id), (None, None))
            if kind is not None:
                spans[kind].append((e.node, e.memory_index, start, e.time_ps))
    for (node, card, _), (kind, start) in open_.items():
        spans[kind].append((node, card, start, horizon))        # still booked when the run ended
    out = {}
    by_node: dict = defaultdict(lambda: defaultdict(list))
    for kind, items in spans.items():
        holds = [(e - s) / PS_PER_MS for _, _, s, e in items]
        out[kind] = {"bookings": len(items), "mean_hold_ms": fmean(holds) if holds else None,
                     "total_card_ms": sum(holds)}
        for node, card, s, e in items:
            by_node[node][kind].append((s, e))
    all_by_node = {n: [iv for ivs in kinds.values() for iv in ivs] for n, kinds in by_node.items()}
    out["card_level_all_kinds"] = histogram(all_by_node)
    out["card_level_application_only"] = histogram({n: k.get("application", []) for n, k in by_node.items()})
    return out


def analyse(result: dict, plan, columns: int, strategy: str, events=None, admission=None) -> dict:
    manager = result["request_manager"]
    stats = result["stats"]
    breakdown = stats["timing_breakdown"]
    compiler = result.get("compiler_metrics") or {}
    records = compiler.get("epr_utilization_trace", [])
    served_by_pair = {r["actual_request_id"]: r for r in records if r["status"] == "used"}
    rows = {"hit": [], "fallback": []}
    for request_id, parts in breakdown.items():
        rows["hit" if request_id in served_by_pair else "fallback"].append(parts)
    split = {}
    for kind, items in rows.items():
        split[kind] = {"requests": len(items),
                       "mean_total_ms": fmean(i["total_time_ms"] for i in items) if items else None,
                       "mean_wait_ms": fmean(i["retry_wait_time_ms"] for i in items) if items else None,
                       "mean_generation_ms": fmean(i["entanglement_generation_time_ms"] for i in items) if items else None,
                       "share_that_waited": fmean(i["retry_wait_time_ms"] > 1e-3 for i in items) if items else None}
    chain_index: dict = {}
    seen: dict = defaultdict(int)
    for request in sorted(plan, key=lambda q: (q.layer, q.order)):
        chain_index[request.request_id] = seen[(request.layer, request.qubit)]
        seen[(request.layer, request.qubit)] += 1
    by_chain: dict = defaultdict(list)
    for r in records:
        if r["status"] != "used":
            continue
        target = r["target_request_id"]
        layer_start = manager.layer_start_times.get(manager.layer_of[target])
        by_chain[min(chain_index[target], 2)].append((
            (r["utilized_at_ps"] - r["generated_at_ps"]) / PS_PER_MS,
            None if layer_start is None else (r["generated_at_ps"] - layer_start) / PS_PER_MS,
            (manager.request_eligible_times[target] - r["generated_at_ps"]) / PS_PER_MS))
    chain_summary = {("hop%d%s" % (k, "+" if k == 2 else "")): {
        "pairs": len(v), "mean_ready_hold_ms": round(fmean(x[0] for x in v), 2),
        "mean_generated_minus_layer_start_ms": None if any(x[1] is None for x in v) else round(fmean(x[1] for x in v), 2),
        "mean_request_eligible_minus_generated_ms": round(fmean(x[2] for x in v), 2)} for k, v in sorted(by_chain.items())}
    holds = [(r["utilized_at_ps"] - r["generated_at_ps"]) / PS_PER_MS for r in records if r["status"] == "used"]
    holds.sort()
    pairs_by_core: dict = defaultdict(list)
    horizon = max(manager.request_end_times.values(), default=0)
    for r in records:
        end = r["utilized_at_ps"] if r["utilized_at_ps"] is not None else (r["expired_at_ps"] or horizon)
        for side in ("source", "destination"):
            pairs_by_core[r[side]].append((r["generated_at_ps"], end))
    service_by_core: dict = defaultdict(list)
    for request in plan:
        rid = request.request_id
        if rid not in manager.request_end_times or rid not in manager.request_generation_start_times:
            continue
        if rid in served_by_pair:
            continue                         # its memory was already counted as a cached pair until consumption
        span = (manager.request_generation_start_times[rid], manager.request_end_times[rid])
        for core in (request.source_core, request.destination_core):
            service_by_core[router_name(core, columns)].append(span)
    both: dict = defaultdict(list)
    for source in (pairs_by_core, service_by_core):
        for core, spans in source.items():
            both[core] += spans
    quantile = lambda p: holds[min(len(holds) - 1, int(p * len(holds)))] if holds else None
    return {
        "strategy": strategy,
        "average_request_latency_ms": stats.get("avg_request_latency_ms"),
        "stats": {k: stats.get(k) for k in ("avg_retry_wait_time_ms", "avg_entanglement_generation_time_ms",
                                            "end_to_end_latency_ms", "protocol_generated_pairs", "protocol_used_pairs",
                                            "protocol_unused_pairs", "protocol_waste_percentage")},
        "average_delivered_epr_fidelity": runner._mean_fidelity(result["fidelity_dict"]),
        "requests": stats["total_requests"],
        "hit_vs_fallback": split,
        "pair_ready_hold_ms": {"mean": fmean(holds) if holds else None, "p50": quantile(0.5), "p90": quantile(0.9),
                               "max": holds[-1] if holds else None, "pairs": len(holds)},
        "wait_split_ms": {
            "before_admission_mean": fmean(b["admission_wait_time_ms"] for b in breakdown.values()),
            "after_admission_mean": fmean(b["retry_wait_time_ms"] - b["admission_wait_time_ms"] for b in breakdown.values()),
            "dependency_wait_mean": fmean(b["dependency_wait_time_ms"] for b in breakdown.values()),
        },
        "protocol_rejections": None if events is None else {
            "events": sum(isinstance(e, RequestRejected) for e in events),
            "requests_rejected_at_least_once": len({e.request_id for e in events if isinstance(e, RequestRejected)}),
            "requests": len(breakdown)},
        "pair_hold_by_chain_position": chain_summary,
        "admission_blocking": admission.summary() if admission is not None else None,
        "bookings": bookings(events, horizon) if events is not None else None,
        "occupancy_cached_pairs": histogram(pairs_by_core),
        "occupancy_cached_plus_in_service": histogram(both),
        "compiler": {k: v for k, v in compiler.items() if k not in ("epr_utilization_trace", "rejection_reasons")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only-chain-hops-below", type=int, default=None,
                        help="ablation: prepare pairs only for the first N hops of each multi-hop chain; later hops fall back")
    args, rest = parser.parse_known_args()
    rest = [a for a in rest if a != "--"]
    captured = []
    real = runner.run_parallel_experiment
    if args.only_chain_hops_below is not None:
        original_spec = runner._compiler_spec

        def filtered_spec(run_args, trace, columns, strategy):
            spec = original_spec(run_args, trace, columns, strategy)
            seen: dict = defaultdict(int)
            keep = set()
            for request in sorted(trace.requests, key=lambda q: (q.layer, q.order)):
                if seen[(request.layer, request.qubit)] < args.only_chain_hops_below:
                    keep.add(request.request_id)
                seen[(request.layer, request.qubit)] += 1
            spec["schedule"] = tuple(p for p in spec["schedule"] if p.request_id in keep)
            return spec
        runner._compiler_spec = filtered_spec

    def wrapper(*a, **kw):
        recorder = ListRecorder()
        log = AdmissionLog()
        from request_scheduler import QubitOrderedRequestManager
        original = log.install(QubitOrderedRequestManager)
        try:
            result = real(*a, **dict(kw, recorder=recorder))
        finally:
            QubitOrderedRequestManager._free_memories = original
        captured.append((result, kw.get("request_plan"), recorder.events, log))
        return result
    runner.run_parallel_experiment = wrapper
    sys.argv = ["run_trace_comparison.py"] + rest
    runner.main()
    out_dir = Path(rest[rest.index("--output") + 1])
    meta = json.loads((out_dir / "metadata.json").read_text())
    columns = int(meta["mesh"].split("x")[1])
    records = [analyse(r, plan, columns, meta["strategies"][0], events, log) for r, plan, events, log in captured]
    args.out.write_text(json.dumps({"arguments": rest, "per_seed": records}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
