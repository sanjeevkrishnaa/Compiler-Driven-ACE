"""Typed records of what an ACE simulation did, and the recorders that collect them.

The simulator emits these events at a few well-defined points; ``invariants.py``
checks a recorded log afterwards.  Keeping emission and checking apart means the
checker can be tested on hand-built logs, including deliberately wrong ones, and
the simulator carries no checking logic of its own.

Times are simulation picoseconds.  Events are stored in emission order, which is
the simulator's own order of execution, so two events with equal times keep the
order in which they happened.

``reservation_id`` is Python object identity (``id(reservation)``).  It is
deliberately *not* the request identity: two distinct reservation objects can
compare equal under SeQUeNCe's ``Reservation.__eq__``, and telling them apart is
exactly what the checker needs to be able to do.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Protocol, Union

APPLICATION = "application"     # a reservation made on behalf of a trace request
ADAPTIVE = "adaptive"           # a CGP/ACGP or compiler-preparation reservation


@dataclass(frozen=True)
class RequestSubmitted:
    """The request manager submitted a request (``attempt`` counts resubmissions from 0)."""

    time_ps: int
    request_id: int
    attempt: int


@dataclass(frozen=True)
class RequestRejected:
    """A reservation for the request was rejected; the manager will retry it."""

    time_ps: int
    request_id: int


@dataclass(frozen=True)
class RequestCompleted:
    """The request's pair was delivered at the initiator."""

    time_ps: int
    request_id: int


@dataclass(frozen=True)
class Booked:
    """A memory's timecard accepted a reservation.

    ``key_hash`` is ``hash(reservation)``: two reservations that compare equal hash alike, so
    two live bookings with different ``reservation_id`` but the same ``key_hash`` are the
    aliasing the checker looks for.  ``None`` when the emitter did not provide it.
    """

    time_ps: int
    node: str
    memory_index: int
    reservation_id: int
    request_id: int
    kind: str
    key_hash: int | None = None


@dataclass(frozen=True)
class Unbooked:
    """A memory's timecard released the reservation it held."""

    time_ps: int
    node: str
    memory_index: int
    reservation_id: int
    request_id: int
    kind: str
    reason: str


@dataclass(frozen=True)
class MisRemoved:
    """``remove(reservation)`` released a *different* reservation that compares equal to it."""

    time_ps: int
    node: str
    memory_index: int
    requested_id: int
    removed_id: int
    request_id: int


@dataclass(frozen=True)
class PairDelivered:
    """An entangled pair appeared in a memory (before any request is credited)."""

    time_ps: int
    node: str
    memory_index: int


@dataclass(frozen=True)
class PairCredited:
    """The application credited a delivered pair to a reservation (``side``: initiator/responder)."""

    time_ps: int
    node: str
    memory_index: int
    reservation_id: int
    request_id: int
    side: str


Event = Union[RequestSubmitted, RequestRejected, RequestCompleted, Booked, Unbooked,
              MisRemoved, PairDelivered, PairCredited]


_ID_FIELDS = ("reservation_id", "requested_id", "removed_id")


def canonical(events: Iterable[Event]) -> list[Event]:
    """Replace object ids by first-seen ordinals so two runs can be compared.

    ``id(reservation)`` differs between processes and runs; everything else in a log of a
    deterministic simulation is reproducible.
    """
    ordinals: dict[int, int] = {}
    result: list[Event] = []
    for event in events:
        changes = {name: ordinals.setdefault(getattr(event, name), len(ordinals))
                   for name in _ID_FIELDS if hasattr(event, name)}
        result.append(replace(event, **changes) if changes else event)
    return result


class Recorder(Protocol):
    """Anything that can receive events."""

    def record(self, event: Event) -> None: ...


class NullRecorder:
    """Discards events; the default, so unobserved runs pay nothing."""

    def record(self, event: Event) -> None:
        return None


class ListRecorder:
    """Keeps every event in emission order."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, event: Event) -> None:
        self.events.append(event)
