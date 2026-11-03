"""Conservative capacity diagnostics from non-invasive booking events."""
from collections import Counter, defaultdict
from ace.compiler.compiler_trace import router_name
from ace.observability.execution_events import Booked, Unbooked, RequestSubmitted, RequestCompleted, ADAPTIVE


def capacity_diagnostics(events, requests, columns, rejections):
    endpoints = {r.request_id: (router_name(r.source_core, columns), router_name(r.destination_core, columns)) for r in requests}
    bookings = {}
    slots = defaultdict(Counter)
    compiler = Counter()
    pending = set()
    pending_counts = Counter()
    peak_slots, peak_compiler, peak_bound = Counter(), Counter(), Counter()
    for event in events:
        touched = []
        if isinstance(event, Booked):
            key = (event.node, event.memory_index, event.reservation_id)
            if key not in bookings:
                bookings[key] = event.kind
                slots[event.node][event.memory_index] += 1
                compiler[event.node] += event.kind == ADAPTIVE
            touched = [event.node]
        elif isinstance(event, Unbooked):
            key = (event.node, event.memory_index, event.reservation_id)
            if key in bookings:
                compiler[event.node] -= bookings.pop(key) == ADAPTIVE
                slots[event.node][event.memory_index] -= 1
                if slots[event.node][event.memory_index] == 0:
                    del slots[event.node][event.memory_index]
            touched = [event.node]
        elif isinstance(event, RequestSubmitted):
            if event.request_id not in pending:
                pending.add(event.request_id)
                pending_counts.update(endpoints[event.request_id])
            touched = endpoints[event.request_id]
        elif isinstance(event, RequestCompleted):
            if event.request_id in pending:
                pending.remove(event.request_id)
                pending_counts.subtract(endpoints[event.request_id])
            touched = endpoints[event.request_id]
        for node in touched:
            peak_slots[node] = max(peak_slots[node], len(slots[node]))
            peak_compiler[node] = max(peak_compiler[node], compiler[node])
            # Outstanding requests include rejected/requeued attempts until
            # completion. Counting booked applications again is conservative.
            peak_bound[node] = max(peak_bound[node], len(slots[node]) + pending_counts[node])
    return dict(peak_booked_slots_per_node=dict(peak_slots),
                peak_compiler_bookings_per_node=dict(peak_compiler),
                peak_booked_plus_outstanding_bound_per_node=dict(peak_bound),
                compiler_rejection_reasons=dict(Counter(reason for rs in rejections.values() for reason in rs)))
