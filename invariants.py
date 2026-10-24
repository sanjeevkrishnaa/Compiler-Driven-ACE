"""Check a recorded ACE execution against the properties a correct run must have.

``check_events`` is a pure function of an event log (``execution_events``) and,
optionally, the trace metadata of the requests.  It never touches the simulator.

Invariants
----------
Memory ownership (needs only the log)
    ALIASED_RESERVATIONS       two live reservation objects compare equal, so every lookup
                               by equality (timecards, rules, per-reservation dictionaries)
                               can confuse them
    MEMORY_DOUBLE_BOOKED       a memory was booked while another reservation held it
    RELEASE_NOT_LIVE           a booking was released that was not live (double release)
    MISREMOVAL                 releasing one reservation released a different one that
                               merely compares equal to it
    STALE_BOOKING_ON_RESUBMIT  a request was resubmitted while its previous attempt's
                               application booking was still live (phantom occupancy)
    BOOKING_SURVIVES_COMPLETION the reservation that completed a request still held a
                               memory at the end of the run

Pair ownership (needs only the log)
    ORPHAN_PAIR                a pair was delivered into a memory no reservation held
    CREDIT_WITHOUT_BOOKING     a pair was credited to a reservation that did not hold
                               that memory
    CREDIT_EXCEEDS_REQUEST     a reservation was credited more pairs than it asked for
    COMPLETION_COUNT           a request completed more than once (or, with
                               ``require_completion``, not at all)

Ordering (needs the trace metadata ``requests``)
    USE_ORDER                  hops of one qubit within a layer did not complete in
                               trace order
    SUBMISSION_BEFORE_PREDECESSOR  with ``submission_after_predecessor``: a hop was first
                               submitted before the previous hop of its qubit completed
    LAYER_BARRIER              a request of layer L+1 was first submitted before every
                               request of layer L had completed

A pair is credited to a *reservation object*, and a reservation can be credited
once per side (initiator and responder).  Retried requests use a new reservation
object per attempt, so earlier attempts never count against a later one.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from execution_events import (
    ADAPTIVE, APPLICATION, Booked, Event, MisRemoved, PairCredited, PairDelivered,
    RequestCompleted, RequestRejected, RequestSubmitted, Unbooked,
)

ALIASED_RESERVATIONS = "ALIASED_RESERVATIONS"
MEMORY_DOUBLE_BOOKED = "MEMORY_DOUBLE_BOOKED"
RELEASE_NOT_LIVE = "RELEASE_NOT_LIVE"
MISREMOVAL = "MISREMOVAL"
STALE_BOOKING_ON_RESUBMIT = "STALE_BOOKING_ON_RESUBMIT"
BOOKING_SURVIVES_COMPLETION = "BOOKING_SURVIVES_COMPLETION"
ORPHAN_PAIR = "ORPHAN_PAIR"
CREDIT_WITHOUT_BOOKING = "CREDIT_WITHOUT_BOOKING"
CREDIT_EXCEEDS_REQUEST = "CREDIT_EXCEEDS_REQUEST"
COMPLETION_COUNT = "COMPLETION_COUNT"
USE_ORDER = "USE_ORDER"
SUBMISSION_BEFORE_PREDECESSOR = "SUBMISSION_BEFORE_PREDECESSOR"
LAYER_BARRIER = "LAYER_BARRIER"


@dataclass(frozen=True)
class RequestInfo:
    """What the trace says about a request."""

    request_id: int
    layer: int
    qubit: int
    order: int              # position within its layer, in trace order
    pairs_required: int = 1


@dataclass(frozen=True)
class Violation:
    invariant: str
    time_ps: int | None
    detail: str


def check_events(
    events: Sequence[Event],
    requests: Mapping[int, RequestInfo] | None = None,
    *,
    require_completion: bool = False,
    submission_after_predecessor: bool = False,
) -> list[Violation]:
    """Return every violation found in ``events`` (empty when the run is correct)."""
    violations: list[Violation] = []
    violations += _check_memory_and_pairs(events, requests, require_completion)
    if requests is not None:
        violations += _check_ordering(events, requests, submission_after_predecessor)
    return sorted(violations, key=lambda v: (-1 if v.time_ps is None else v.time_ps, v.invariant, v.detail))


def summarize(violations: Iterable[Violation]) -> Counter:
    """Count violations by invariant."""
    return Counter(v.invariant for v in violations)


# ----------------------------------------------------------------------------- memory and pairs
def _check_memory_and_pairs(
    events: Sequence[Event], requests: Mapping[int, RequestInfo] | None, require_completion: bool,
) -> list[Violation]:
    out: list[Violation] = []
    live: dict[tuple[str, int], Booked] = {}
    credits: Counter = Counter()                        # (reservation_id, side) -> pairs credited
    completions: Counter = Counter()                    # request_id -> times completed
    completing_reservation: dict[int, int] = {}         # request_id -> reservation that completed it
    last_initiator_credit: dict[int, int] = {}          # request_id -> reservation last credited at the initiator
    required = {rid: info.pairs_required for rid, info in (requests or {}).items()}

    for event in events:
        if isinstance(event, Booked):
            if event.key_hash is not None:
                twin = next((b for b in live.values()
                             if b.kind == event.kind and b.key_hash == event.key_hash
                             and b.reservation_id != event.reservation_id), None)
                if twin is not None:
                    out.append(Violation(ALIASED_RESERVATIONS, event.time_ps,
                                         f"request {event.request_id} ({event.kind}) and request "
                                         f"{twin.request_id} hold reservations that compare equal "
                                         f"({event.node} memory {event.memory_index} / "
                                         f"{twin.node} memory {twin.memory_index})"))
            held = live.get((event.node, event.memory_index))
            if held is not None and held.reservation_id != event.reservation_id:
                out.append(Violation(MEMORY_DOUBLE_BOOKED, event.time_ps,
                                     f"{event.node} memory {event.memory_index} booked for request "
                                     f"{event.request_id} ({event.kind}) while held for request "
                                     f"{held.request_id} ({held.kind})"))
            live[(event.node, event.memory_index)] = event
        elif isinstance(event, Unbooked):
            held = live.get((event.node, event.memory_index))
            if held is None or held.reservation_id != event.reservation_id:
                out.append(Violation(RELEASE_NOT_LIVE, event.time_ps,
                                     f"{event.node} memory {event.memory_index}: released a booking for request "
                                     f"{event.request_id} that was not live ({event.reason})"))
            else:
                del live[(event.node, event.memory_index)]
        elif isinstance(event, MisRemoved):
            out.append(Violation(MISREMOVAL, event.time_ps,
                                 f"{event.node} memory {event.memory_index}: releasing request "
                                 f"{event.request_id}'s reservation removed a different, equal-comparing one"))
            held = live.get((event.node, event.memory_index))
            if held is not None and held.reservation_id == event.removed_id:
                del live[(event.node, event.memory_index)]
        elif isinstance(event, RequestSubmitted):
            if event.attempt > 0:
                stale = sorted({b.request_id for b in live.values()
                                if b.kind == APPLICATION and b.request_id == event.request_id})
                if stale:
                    out.append(Violation(STALE_BOOKING_ON_RESUBMIT, event.time_ps,
                                         f"request {event.request_id} resubmitted (attempt {event.attempt}) while "
                                         f"its previous attempt still held "
                                         f"{sum(1 for b in live.values() if b.kind == APPLICATION and b.request_id == event.request_id)}"
                                         f" memory booking(s)"))
        elif isinstance(event, PairDelivered):
            if (event.node, event.memory_index) not in live:
                out.append(Violation(ORPHAN_PAIR, event.time_ps,
                                     f"{event.node} memory {event.memory_index}: pair delivered into a memory "
                                     f"no reservation held"))
        elif isinstance(event, PairCredited):
            held = live.get((event.node, event.memory_index))
            if held is None or held.reservation_id != event.reservation_id:
                out.append(Violation(CREDIT_WITHOUT_BOOKING, event.time_ps,
                                     f"{event.node} memory {event.memory_index}: pair credited to request "
                                     f"{event.request_id} whose reservation did not hold it"))
            credits[(event.reservation_id, event.side)] += 1
            if credits[(event.reservation_id, event.side)] > required.get(event.request_id, 1):
                out.append(Violation(CREDIT_EXCEEDS_REQUEST, event.time_ps,
                                     f"request {event.request_id}: {credits[(event.reservation_id, event.side)]} "
                                     f"pairs credited at the {event.side}, "
                                     f"{required.get(event.request_id, 1)} requested"))
            if event.side == "initiator":
                last_initiator_credit[event.request_id] = event.reservation_id
        elif isinstance(event, RequestCompleted):
            completions[event.request_id] += 1
            if completions[event.request_id] > 1:
                out.append(Violation(COMPLETION_COUNT, event.time_ps,
                                     f"request {event.request_id} completed {completions[event.request_id]} times"))
            if event.request_id in last_initiator_credit:
                completing_reservation[event.request_id] = last_initiator_credit[event.request_id]
        elif isinstance(event, RequestRejected):
            pass

    for request_id, reservation_id in sorted(completing_reservation.items()):
        leftover = [b for b in live.values()
                    if b.reservation_id == reservation_id and b.kind == APPLICATION]
        if leftover:
            where = ", ".join(f"{b.node}[{b.memory_index}]" for b in leftover)
            out.append(Violation(BOOKING_SURVIVES_COMPLETION, None,
                                 f"request {request_id} completed but its reservation still held {where} at the end"))
    if require_completion and requests is not None:
        for request_id in sorted(set(requests) - set(completions)):
            out.append(Violation(COMPLETION_COUNT, None, f"request {request_id} never completed"))
    return out


# ----------------------------------------------------------------------------- ordering
def _check_ordering(
    events: Sequence[Event], requests: Mapping[int, RequestInfo], submission_after_predecessor: bool,
) -> list[Violation]:
    out: list[Violation] = []
    first_submitted: dict[int, int] = {}
    completed: dict[int, int] = {}
    for event in events:
        if isinstance(event, RequestSubmitted) and event.request_id not in first_submitted:
            first_submitted[event.request_id] = event.time_ps
        elif isinstance(event, RequestCompleted):
            completed.setdefault(event.request_id, event.time_ps)

    chains: dict[tuple[int, int], list[RequestInfo]] = defaultdict(list)
    layers: dict[int, list[int]] = defaultdict(list)
    for info in requests.values():
        chains[(info.layer, info.qubit)].append(info)
        layers[info.layer].append(info.request_id)

    for (layer, qubit), hops in sorted(chains.items()):
        hops.sort(key=lambda info: info.order)
        for before, after in zip(hops, hops[1:]):
            done_before, done_after = completed.get(before.request_id), completed.get(after.request_id)
            if done_before is not None and done_after is not None and done_after < done_before:
                out.append(Violation(USE_ORDER, done_after,
                                     f"layer {layer} qubit {qubit}: hop {after.request_id} completed at "
                                     f"{done_after} before its predecessor {before.request_id} at {done_before}"))
            started = first_submitted.get(after.request_id)
            if (submission_after_predecessor and started is not None and done_before is not None
                    and started < done_before):
                out.append(Violation(SUBMISSION_BEFORE_PREDECESSOR, started,
                                     f"layer {layer} qubit {qubit}: hop {after.request_id} submitted at {started} "
                                     f"before its predecessor {before.request_id} completed at {done_before}"))

    ordered = sorted(layers)
    for layer, following in zip(ordered, ordered[1:]):
        finishes = [completed[r] for r in layers[layer] if r in completed]
        starts = [first_submitted[r] for r in layers[following] if r in first_submitted]
        if finishes and starts and min(starts) < max(finishes):
            out.append(Violation(LAYER_BARRIER, min(starts),
                                 f"layer {following} began at {min(starts)} before layer {layer} finished "
                                 f"at {max(finishes)}"))
    return out
