# Active-layer dynamic preparation, 2026-11-02

Branch: codex/active-layer-pregeneration. Same complete 96-qubit QAOA trace,
T-HQA/OEE mapping seed 42, History routing, physics seed 60, M=4/C=4,
generation capacity 4, all chain hops, two-layer lead, eight-layer maximum,
planner age limit ten, ready-first event admission, handoff and 50 ms compiler
reservation cap. SeQUeNCe 0.8.1 remains pinned. Four controlled variants separate
the empty-gap change from the planner change; each runs ODG and dynamic.
All eight trials completed 7913/7913 requests with clean runtime audits.
The rerun of the old policy reproduces the earlier seed-60 means exactly.

## Implementation

Active communication layers are the sorted unique layer IDs having at least one
hop request. Dynamic planning ranks these layers and runs the existing latest-
feasible 2-8 lookback on that compressed axis. Generation capacity, stored-pair
occupancy and planner coherence-age checks all use active-layer positions.
Chosen generation positions are mapped back to original layer IDs before runtime
launch. No preparation can launch from an empty layer. Runtime memory quotas,
physical timecards, physical coherence, retry behavior and pair handoff are
unchanged. Both offline and runtime-candidate planner modes support this axis.
Fixed-offset preparation retains its existing logical-layer semantics.

With active IDs [2,5,9,15,20], a request at 20 tries 9,5,2 for minimum lead two;
15 is only one active layer earlier and is excluded. The first two active layers
have no candidate at the two-active-layer minimum. Plans are first-feasible in
trace order, not global latency optimization.

The default empty-layer gap for the per-qubit scheduler is now 0.001 ms = 1 us,
configurable with --empty-layer-gap-ms. This is an explicitly chosen timing
placeholder, NOT calibrated local processing, gates, movement or teleportation.
A final empty layer has no following gap. The historical legacy scheduler is
unchanged. No full intra-core processing model was added.

## Compiler results (one seed)

| Policy | Empty gap | Mean hop latency (ms) | Makespan (s) | EPR fidelity (%) | Readiness (%) | Admission wait (ms/hop) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| logical | 5.0 ms | 1.0044 | 3.7064 | 93.777 | 65.41 | 0.2102 |
| logical | 0.001 ms | 1.8829 | 2.6121 | 94.582 | 41.07 | 0.8863 |
| active | 5.0 ms | 3.0014 | 5.6390 | 93.553 | 33.49 | 1.8128 |
| active | 0.001 ms | 2.5098 | 3.4046 | 93.597 | 41.29 | 1.4779 |

## ODG control

| Policy | Empty gap | Mean hop latency (ms) | Makespan (s) |
| --- | --- | ---: | ---: |
| logical | 5.0 ms | 1.3732 | 4.0941 |
| logical | 0.001 ms | 1.3722 | 2.0857 |
| active | 5.0 ms | 1.3732 | 4.0941 |
| active | 0.001 ms | 1.3722 | 2.0857 |

## Findings

The requested policy is implemented but is worse on per-request latency. Under
the new 1 us timing, active lookback gives 2.5098 ms versus 1.8829 ms for logical
lookback. Both are slower than ODG's 1.3722 ms. This isolates an additional
contention cost from active-layer planning, rather than attributing everything
to removal of 5 ms gaps. Active lookback at the old 5 ms timing is worse still.

The new active/1 us makespan is lower than the old logical/5 ms makespan, but
that comparison removes roughly 2.02 s of explicit idle gaps and changes how
much physical time preparation has. It is not evidence that EPR service got
faster. Measured admission wait increases from 0.2102 to 1.4779 ms/hop. Earlier
active-layer scheduling extends storage/reservation overlap; guaranteeing
nonempty generation layers does not guarantee adequate useful preparation time
or prevent future preparations occupying memories needed by current work.
The counters establish the waiting increase; they do not isolate every causal
protocol interaction. No additional policy tuning was introduced to hide this
result. Readiness counts consumed pairs generated before first submission,
not necessarily initial eligibility. Delivered EPR fidelity is not circuit
output fidelity. These are single-seed findings.

## Validation and use

202 simulator tests and 19 routing tests pass. Regressions cover second-previous
active selection, earlier feasible active-layer fallback under launch capacity,
active-age checks across large logical gaps, empty traces, the active lookback
bounds and the default 1 us runtime gap. Historical handoff/equivalence fixtures
explicitly retain 5 ms so they still test the behavior for which they were built.
All active schedules in the experiment are also checked to launch only in active
layers and to have active lead 2-8.

```text
make run WORKLOAD=qaoa ROUTING=history
make run WORKLOAD=qaoa ROUTING=history LAYER_BASIS=logical EMPTY_LAYER_GAP_MS=5 OUTPUT=output/old-policy-reproduction
```

Direct CLI overrides: --dynamic-layer-basis active --empty-layer-gap-ms 0.001.
The current experiment launcher supplies --planner-lead-layers 2; raw CLI defaults
still require explicitly selecting that lead when bypassing the launcher.
Use a fresh output directory. Old cached routing results are rejected if their
layer basis or gap differs. Historical reports remain measurements of their old
policy. Kernel coherence parameters and the 50 ms reservation cap are unchanged.
