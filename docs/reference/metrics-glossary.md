# Metrics glossary

Every column `run_trace_comparison.py` emits, what it means, and how to read it.

Metrics fall into two groups. **Protocol metrics** are defined identically for
every strategy. **Compiler metrics** exist only when a compiler controller is
attached, so they are `None` — not zero — for `on-demand`, `continuous` and
`adaptive-continuous`. An empty cell there is a meaningful absence: the policy has
no request identity, so the quantity is undefined rather than nil.

## Identity

| Column | Meaning |
| --- | --- |
| `strategy` | `on-demand`, `continuous` (CGP), `adaptive-continuous` (ACGP), `fixed`, `dynamic` |
| `seed` | physics seed — the EPR generation coin flips, not the mapping |
| `metric_version` | accounting version; results from different versions are not comparable |

## Completion

| Column | Meaning |
| --- | --- |
| `requests` | hop requests in the trace |
| `completed_requests` | requests that finished |
| `completion_rate` | **invariant: must be 1.0.** Anything less invalidates the run |

Falling back to on-demand is normal recovery, not failure. A request that never
completes is a different matter and voids the result.

## Latency

| Column | Meaning |
| --- | --- |
| `average_request_latency_ms` | **the headline metric.** Mean time from a request being submitted to its entanglement being delivered |
| `end_to_end_latency_ms` | makespan — wall-clock time for the whole trace |
| `avg_layer_latency_ms` | mean time to clear one circuit layer |
| `max_layer_latency_ms` / `min_layer_latency_ms` | worst and best layer; the spread shows whether cost is uniform or concentrated in hot layers |

Request latency and makespan answer different questions. Request latency is what a
single operation waits. Makespan is what the program takes. Pre-generation can cut
request latency sharply while barely moving makespan, because the critical path is
set by the scheduler rather than by any one request.

### Latency decomposition — where the time actually goes

| Column | Meaning |
| --- | --- |
| `avg_reservation_setup_time_ms` | negotiating the reservation before any physics happens |
| `max_reservation_setup_time_ms` | worst case of the above |
| `avg_entanglement_generation_time_ms` | the physical Barrett–Kok attempt loop |
| `max_entanglement_generation_time_ms` | worst case of the above |
| `avg_retry_wait_time_ms` | time lost to rejected attempts waiting to retry |

This decomposition is what distinguishes **congestion** from **slow physics**. If
removing the memory limit collapses setup and retry time while generation time
stays flat or rises, the bottleneck was queueing for a free memory. If generation
time dominates throughout, the link is the limit and more memory cannot help.

## Contention

| Column | Meaning |
| --- | --- |
| `total_layers` | layers in the trace |
| `retry_layers` | extra layer passes forced by requests that could not be served first time |
| `total_layers_with_retries` | `total_layers + retry_layers` — how far the schedule stretched |
| `total_retries` | total retry events |
| `requests_with_retries` | how many distinct requests needed at least one retry |

`retry_layers` is the most direct structural signature of congestion inside the
simulator: it counts how often the scheduler had to come back around.

## Fidelity

| Column | Meaning |
| --- | --- |
| `average_delivered_epr_fidelity` | **the quality metric.** Mean fidelity of pairs actually used for teleportation |
| `average_fidelity_at_creation` | fidelity of a compiler pair when it was made (compiler only) |
| `average_fidelity_at_utilization` | fidelity of that pair when it was consumed (compiler only) |

The gap between creation and utilization is **decoherence during storage**. A pair
prepared far ahead of its use decays while it waits, so a policy can buy latency
and pay for it in fidelity. On-demand has no gap, because nothing is stored.

## Entanglement efficiency — comparable across every strategy

| Column | Meaning |
| --- | --- |
| `protocol_generated_pairs` | every pair the entanglement protocol produced |
| `protocol_used_pairs` | pairs consumed by a request |
| `protocol_unused_pairs` | pairs released without ever being used |
| `protocol_waste_percentage` | `100 × unused / generated` |

These come from counters the adaptive-continuous protocol maintains on every
router under every policy, so **this is the only efficiency metric that lets the
autonomous caches and the compiler policies be compared on the same footing.**

Waste matters because generation attempts are not free: each one costs laser
shots, detector time and thermal budget. Two policies with equal latency are not
equally good if one burns an order of magnitude more entanglement to get there.

## Readiness — was the pair there in time?

| Column | Meaning |
| --- | --- |
| `pregenerated_hits` | requests whose pair completed **strictly before** first submission |
| `pregenerated_success_rate` | `hits / requests` — **the useful latency-hiding rate** |
| `compiler_not_ready_requests` | requests whose pair was not ready in time |
| `late_compiler_pair_uses` | a compiler pair was used, but finished too late to hide any latency |
| `intended_request_hits` | compiler pairs consumed by exactly the request they were prepared for |
| `intended_request_hit_rate` | `intended_request_hits / requests` — a **coverage** rate: the share of all requests served by their own prepared pair, ready or late. It is below 1.0 whenever a request falls back, so it is not an invariant |

**Identity and coverage are different quantities, and the difference is the
central claim of the project.**

*Identity* asks: of the compiler pairs that were used, did each one serve the
request it was prepared for? The check is
`intended_request_hits == utilized_compiler_pairs`. It must hold in every run; a
violation means pairs crossed between requests, which is a provenance bug and not
a performance result. In the ACE congestion budget study it holds in 189 of 189
dynamic rows.

*Coverage* asks: of all requests, how many were served by a prepared pair at all
(`intended_request_hit_rate`), and how many of those were ready strictly before
first submission (`pregenerated_success_rate`)? Both fall well below 1.0 on
congested workloads, because finite memory means the planner cannot schedule every
preparation. The gap between the two is `late_compiler_pair_uses`.

So the compiler's premise holds in the sense that a pair it uses is always the
right pair (identity, 100%). It does not hold in the sense that every request gets
one (coverage). Congestion breaks the second, not the first.

## Fallback

| Column | Meaning |
| --- | --- |
| `on_demand_fallbacks` | requests served by generating on demand instead |
| `on_demand_fallback_rate` | fraction of requests that fell back |

Fallback is the recovery path, not a failure. A high fallback rate means
pre-generation coverage was low, which is exactly what congestion causes.

## Planner — what was schedulable before anything ran

| Column | Meaning |
| --- | --- |
| `scheduled_preparations` | preparations the offline planner admitted |
| `planner_blocked_preparations` | preparations it refused, because the core was already at its cap in that layer |
| `planner_peak_compiler_memory_per_core` | peak compiler memory the plan needs on any core |

`planner_blocked_preparations` is congestion measured **before the simulator
starts**. It is the structural limit: these requests could never have been
pre-generated at this memory budget, whatever the physics did.

## Runtime admission — what happened when it tried

| Column | Meaning |
| --- | --- |
| `runtime_admission_attempts` | attempts to admit a preparation |
| `runtime_launched_preparations` | preparations actually launched |
| `runtime_accepted_preparations` | admissions accepted |
| `runtime_rejected_preparations` | preparations rejected at least once |
| `runtime_rejection_events` | total rejection events, including repeats |

The gap between `scheduled_preparations` and `runtime_accepted_preparations` is
the difference between what the plan assumed and what the running system allowed.

## Compiler pair bookkeeping

| Column | Meaning |
| --- | --- |
| `generated_compiler_pairs` | pairs the compiler created |
| `utilized_compiler_pairs` | pairs consumed |
| `expired_compiler_pairs` | pairs that decohered past threshold before use |
| `remaining_compiler_pairs` | pairs still held when the run ended |
| `compiler_expiry_percentage` | `100 × expired / generated` |
| `compiler_waste_percentage` | `100 × (expired + remaining) / generated` |

Scoped to compiler-directed pairs only. Use `protocol_waste_percentage` when
comparing against the autonomous caches.

## The four denominators

Four different quantities are all loosely called "hit rate". They answer different
questions and must never be merged:

1. `intended_request_hits / utilized_compiler_pairs` — **identity.** Did each used
   pair serve its own request? Must be 100%. Not a column; check the equality.
2. `intended_request_hit_rate` and `pregenerated_success_rate` — **coverage.**
   Served by a prepared pair, and ready in time? The second is the useful number.
3. `compiler_waste_percentage` — **efficiency.** Was what we made used?
4. `completion_rate` — **completion.** Already 100%, because fallback exists.

Quoting one and implying another is the most common way to overstate a
pre-generation result.
