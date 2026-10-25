"""One latency definition that means the same under every request manager.

``ParallelLayerRequestManager.get_individual_latencies`` starts a request's clock at its first
submission.  Under the legacy manager a request in a later per-core batch is submitted only after
the earlier batches finish, so time spent waiting for them is not counted.  The per-qubit manager
counts the time a request waits to be admitted.  Those two numbers are not comparable.

Here a request's clock starts when it could first have been asked for:

* the moment its layer became active, or
* for a hop that follows another hop of the same qubit in the same layer, the moment that hop
  completed (the qubit has to arrive before it can move on).

Latency is completion minus that moment, minus the configured pre-generation lead once, as in the
manager's own definition.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from sequence.constants import MILLISECOND


def layer_activation_times(layer_start_times: Mapping[int, int], working_layer_origins: Sequence) -> dict[int, int]:
    """First time each original layer was started (a layer may be split into several batches)."""
    first: dict[int, int] = {}
    for index, origin in enumerate(working_layer_origins):
        if origin is None or index not in layer_start_times:
            continue
        first[origin] = min(first.get(origin, layer_start_times[index]), layer_start_times[index])
    return first


def eligible_latencies_ms(manager, requests: Sequence, subtract_lead: bool = True) -> dict[int, float]:
    """Latency of every completed request, from the moment it could first be asked for.

    ``subtract_lead=False`` is the headline definition (arrival to EPR delivery, queueing and reservation
    control included).  ``True`` keeps the manager's older convention of excluding the configured lead once.
    """
    activation = layer_activation_times(manager.layer_start_times, manager.working_layer_origins)
    chains: dict[tuple[int, int], list] = defaultdict(list)
    for r in requests:
        chains[(r.layer, r.qubit)].append(r)
    previous: dict[int, int] = {}
    for hops in chains.values():
        hops.sort(key=lambda r: r.order)
        for before, after in zip(hops, hops[1:]):
            previous[after.request_id] = before.request_id

    latencies = {}
    for r in requests:
        end = manager.request_end_times.get(r.request_id)
        if end is None:
            continue
        if r.request_id in previous:
            eligible = manager.request_end_times.get(previous[r.request_id])
        else:
            eligible = activation.get(r.layer)
        if eligible is None:
            continue
        lead = manager.pregeneration_time if subtract_lead else 0
        latencies[r.request_id] = (end - eligible - lead) / MILLISECOND
    return latencies
