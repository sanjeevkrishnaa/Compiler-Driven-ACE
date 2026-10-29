# Golden-study scheduler audit

Status: **code-path audit complete; final four-policy execution blocked pending
the listed gates.** This document describes the current implementation, not an
idealised interpretation of policy names.

## Exact runner mapping

`run_trace_comparison.py` is the common physical runner. Its strategy argument
maps to code paths as follows.

| Golden-study label | Runner strategy | Actual mechanism | Request-targeted pair provenance |
| --- | --- | --- | --- |
| ODG | `on-demand` | No offline preparations; requests create EPR pairs when submitted | Not applicable |
| CGP | `continuous` | Autonomous cache generation with a fixed neighbour-probability table | No: cached pairs are generic link pairs |
| ACGP | `adaptive-continuous` | Same autonomous protocol, but feedback updates neighbour probabilities | No: cached pairs are generic link pairs |
| Dynamic | `dynamic` | Offline request-specific schedule plus runtime reservation admission and fallback | Yes: compiler pairs store their target request ID |

The only CGP/ACGP behavioural selector in the shared runner is
`update_prob = strategy == "adaptive-continuous"`. In `adaptive_continuous.py`,
CGP therefore continues producing pairs but does not update the probability table;
ACGP does update it. Dynamic disables autonomous cycles and calls
`request_compiler_pair` with a traced target request.

## What is already comparable

All four paths run through the same ACE topology construction, request manager,
per-qubit scheduler when selected, physical random seed, trace, request duration,
and total physical-memory setting. They can therefore be compared on:

- completion rate;
- eligibility-to-delivery latency distribution and makespan;
- admission wait, retry, reservation, and generation timing;
- delivered EPR fidelity;
- protocol-generated, used, and unused EPR pairs and protocol waste.

`protocol_waste_percentage` is the cross-policy waste metric. It is counted by
the physical adaptive protocol for every strategy.

## Metrics that must stay policy-specific

CGP and ACGP do not attach a target request ID to an autonomous cached pair.
Consequently, compiler-only fields such as intended-request hit rate, targeted
readiness, compiler expiry, and compiler storage age are **undefined** for them.
They must be rendered as `N/A`, not zero.

ODG is currently routed through an empty compiler controller so that it shares
the same request path. Its compiler counters are zero or empty by construction;
they are not evidence that ODG had a failed compiler plan.

## Blocking fairness gate: cache quota

Dynamic sets every router's `adaptive_max_memory` to
`--compiler-memories`. CGP/ACGP use the configuration-file cap unless the runner
is passed `--autonomous-cache-follows-compiler-memories`; with that flag, they use
the same explicit `--compiler-memories` value.

Therefore a final four-policy run **must explicitly choose and record** one of:

1. equal per-policy cache quota (`--autonomous-cache-follows-compiler-memories`);
2. each policy's native configured quota, reported as an architectural comparison,
   not a fixed-memory fair comparison.

The golden study will execute both only if they are registered as distinct
experiments. It will never mix them in one chart.

## Blocking observability gate: role-separated congestion

The common `summary.csv` contains overall request wait but not a standard endpoint
versus relay decomposition or peak physical-memory occupancy. Existing
`tools/mapper_ace/per_core_wait.py` can derive role-separated wait for a trace,
but its output is not yet part of every runner manifest. Before Experiment 2, the
golden runner must emit or derive a registered per-core diagnostics artifact for
each accepted run.

## Checks completed in this audit

- `on-demand`, `continuous`, `adaptive-continuous`, and `dynamic` are accepted by
  one CLI and reach the same physical simulator.
- The common runner writes source hashes, metric version, seed information, and
  all parsed CLI parameters into `metadata.json`.
- Dynamic's compiler-memory cap is checked against the physical memory count.
- The existing per-qubit request latency is the eligibility-to-delivery metric
  defined by the golden-study contract.

## Required next implementation work

1. Add a golden-run manifest that records policy-specific quota semantics and
   rejects an unregistered cache-cap comparison.
2. Add normalized role-separated congestion and occupancy artifacts.
3. Register and hash ten fresh workload traces.
4. Lock training/evaluation seed partitions and the exact physical configuration.
5. Run one four-policy smoke trace through the manifest validator before any sweep.
