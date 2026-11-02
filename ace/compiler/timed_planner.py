"""Wall-clock-aware preparation planning.

The layer planner (``plan_preparations``) picks a *layer* in which to start each pair, and the controller then
launches it when that layer opens.  Layers differ greatly in duration (an empty layer costs a gap, a busy one costs
several hops), so a lead of "two layers" is sometimes a few microseconds and sometimes several milliseconds.

This planner works on the clock.  It needs two things the compiler can know in advance:

* a ``LayerClock``: the estimated start time of every layer, in milliseconds; and
* a ``PreparationModel``: how long a pair takes to make, from the classical message delay and the success
  probability of one attempt.

For every request it computes when the pair must be launched so that it is ready, with a chosen probability, by
the time the request starts, and launches it then, which can be in the middle of a layer.  A launch is returned as
``ScheduledPreparation(request_id, generation_layer, offset_ms)``: the layer that is open at that moment and the
time into that layer.  Anchoring to a layer keeps the launch aligned with the real execution if the estimated clock
drifts, because the controller counts the offset from the moment the layer actually opens.

Timing of one preparation (measured on the simulator, see docs/research/generation-time-2026-11-01):

    launch -> window opens after 2 delta -> k attempts of c delta each -> pair ready,   c = 4 forward, 5 reverse

where *forward* means the source core has the lower number, and k is geometric with success probability p.
The pair holds one memory at each endpoint from the moment the window opens until its request starts.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
import json
from math import ceil, log
from pathlib import Path

from ace.compiler.compiler_trace import CompilerTrace, ScheduledPreparation

GUARD_DELAYS = 2          # the reservation handshake before the first attempt
FORWARD_CYCLE, REVERSE_CYCLE = 4, 5


@dataclass(frozen=True)
class PreparationModel:
    """How long one pair takes to make."""

    delay_ms: float                # one classical message
    success_probability: float     # one attempt
    quantile: float = 0.9          # probability that the pair is ready in time
    margin_ms: float = 0.0         # extra safety added to every lead

    def __post_init__(self):
        if self.delay_ms <= 0:
            raise ValueError("the classical delay must be positive")
        if not 0 < self.success_probability <= 1:
            raise ValueError("the success probability must lie in (0, 1]")
        if not 0 < self.quantile < 1:
            raise ValueError("the readiness quantile must lie in (0, 1)")
        if self.margin_ms < 0:
            raise ValueError("the margin must be non-negative")

    def attempts(self) -> int:
        """Smallest k with P(success within k attempts) >= quantile."""
        if self.success_probability >= 1:
            return 1
        return max(1, ceil(log(1 - self.quantile) / log(1 - self.success_probability)))

    def window_ms(self) -> float:
        """From launch until the reservation window opens and the memories are held."""
        return GUARD_DELAYS * self.delay_ms

    def lead_ms(self, source_core: int, destination_core: int) -> float:
        """From launch until the pair is ready with probability ``quantile``, including the margin."""
        cycle = REVERSE_CYCLE if source_core > destination_core else FORWARD_CYCLE
        return self.window_ms() + cycle * self.delay_ms * self.attempts() + self.margin_ms

    def mean_lead_ms(self, source_core: int, destination_core: int) -> float:
        cycle = REVERSE_CYCLE if source_core > destination_core else FORWARD_CYCLE
        return self.window_ms() + cycle * self.delay_ms / self.success_probability


def success_probability_from_config(path: str | Path) -> float:
    """One-attempt success probability of the configured heralded link (memory, detectors, fibre, BSM)."""
    config = json.loads(Path(path).read_text())
    template = config["templates"]["adaptive_protocol"]
    memory = template["MemoryArray"]["efficiency"]
    bsm = template["SingleHeraldedBSM"]
    detectors = 1.0
    for detector in bsm["detectors"]:
        detectors *= detector.get("efficiency", 0.9)
    fibre = 1.0
    if config.get("qchannels"):
        channel = config["qchannels"][0]
        fibre = 10 ** (-(channel["distance"] * channel.get("attenuation", 0.0)) / 10)
    return bsm.get("success_rate", 0.5) * (memory * fibre) ** 2 * detectors


class LayerClock:
    """Estimated start time, in milliseconds, of every layer."""

    def __init__(self, starts_ms: list[float]):
        if any(b < a for a, b in zip(starts_ms, starts_ms[1:])):
            raise ValueError("layer start times must not decrease")
        self.starts_ms = list(starts_ms)

    def __len__(self) -> int:
        return len(self.starts_ms)

    def layer_at(self, time_ms: float) -> int:
        """The layer that is open at ``time_ms``: the last one starting no later."""
        return max(0, bisect_right(self.starts_ms, time_ms) - 1)

    @classmethod
    def from_profile(cls, path: str | Path) -> "LayerClock":
        """Start times measured in an earlier run of the same trace (a list of milliseconds)."""
        return cls([float(x) for x in json.loads(Path(path).read_text())])

    @classmethod
    def analytic(cls, trace: CompilerTrace, hop_ms: float, empty_gap_ms: float) -> "LayerClock":
        """No measurement: a layer with requests lasts as long as its longest chain of hops, an empty layer one gap."""
        longest: dict[int, int] = defaultdict(int)
        chains: dict[tuple[int, int], int] = defaultdict(int)
        for request in trace.requests:
            chains[(request.layer, request.qubit)] += 1
            longest[request.layer] = max(longest[request.layer], chains[(request.layer, request.qubit)])
        starts, now = [], 0.0
        for layer in range(trace.layer_count):
            starts.append(now)
            now += longest[layer] * hop_ms if layer in longest else empty_gap_ms
        return cls(starts)


class _Intervals:
    """Intervals already planned on one core.

    Requests are planned in clock order, so ``bound`` (the time the request starts) never decreases; an interval
    that ends before ``bound`` < t cannot touch anything at or after t, which lets the scan stop early.
    """

    def __init__(self):
        self.items: list[tuple[float, float, float]] = []      # (start, end, bound)

    def peak_with(self, start: float, end: float) -> int:
        """Most intervals overlapping at once inside [start, end], counting one more over the whole range."""
        events = []
        for s, e, bound in reversed(self.items):
            if bound < start:
                break
            if e > start and s < end:
                events += [(max(s, start), 1), (min(e, end), -1)]
        events.sort(key=lambda item: (item[0], item[1]))        # a pair that ends first frees its memory first
        peak = running = 0
        for _, change in events:
            running += change
            peak = max(peak, running)
        return peak + 1

    def add(self, start: float, end: float, bound: float) -> None:
        self.items.append((start, end, bound))


def plan_timed_preparations(
    trace: CompilerTrace,
    clock: LayerClock,
    model: PreparationModel,
    *,
    compiler_memories_per_core: int,
    generation_capacity_per_core: int,
    max_lookback_ms: float = 20.0,
    search_step_ms: float = 0.25,
) -> tuple[tuple[ScheduledPreparation, ...], int, int]:
    """Plan one launch time per request.  Returns (schedule, blocked, peak pairs held per core).

    The ideal launch is ``lead`` before the request.  If a core is then already holding its compiler memories, or
    already has ``generation_capacity`` preparations in flight, the launch is moved earlier in steps of
    ``search_step_ms`` up to ``max_lookback_ms``.  A request that finds no such moment is *blocked* and falls back
    to on-demand generation, as in the layer planner.
    """
    if compiler_memories_per_core < 0 or generation_capacity_per_core < 1 or max_lookback_ms < 0 or search_step_ms <= 0:
        raise ValueError("invalid capacity, lookback or step")
    if len(clock) < trace.layer_count:
        raise ValueError(f"the clock covers {len(clock)} layers but the trace has {trace.layer_count}")
    if compiler_memories_per_core == 0:
        return (), len(trace.requests), 0
    held: dict[int, _Intervals] = defaultdict(_Intervals)        # a pair occupies its memory from window to request
    flying: dict[int, _Intervals] = defaultdict(_Intervals)      # a preparation is in flight from launch to ready
    schedule: list[ScheduledPreparation] = []
    blocked = peak = 0
    for request in sorted(trace.requests, key=lambda r: (r.layer, r.order)):
        needed_at = clock.starts_ms[request.layer]
        lead = model.lead_ms(request.source_core, request.destination_core)
        chosen, occupancy = None, 0
        shift = 0.0
        while shift <= max_lookback_ms and needed_at - lead - shift >= 0:
            launch = needed_at - lead - shift
            held_peak = max(held[core].peak_with(launch + model.window_ms(), needed_at) for core in request.edge)
            if (held_peak <= compiler_memories_per_core
                    and all(flying[core].peak_with(launch, launch + lead) <= generation_capacity_per_core
                            for core in request.edge)):
                chosen, occupancy = launch, held_peak
                break
            shift += search_step_ms
        if chosen is None:
            blocked += 1
            continue
        for core in request.edge:
            held[core].add(chosen + model.window_ms(), needed_at, needed_at)
            flying[core].add(chosen, chosen + lead, needed_at)
        peak = max(peak, occupancy)
        layer = clock.layer_at(chosen)
        schedule.append(ScheduledPreparation(request.request_id, layer, chosen - clock.starts_ms[layer]))
    schedule.sort(key=lambda item: item.request_id)
    return tuple(schedule), blocked, peak
