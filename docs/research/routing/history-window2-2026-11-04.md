# Rolling History routing experiment (2026-11-04)

Branch: `history-algo-update`, forked from `main`. This change has not been merged
into `main`. Existing physical runs and presentation data retain their frozen
cumulative-History traces; they are not measurements of this experiment.

## Evidence about preparation lead

Source: `output/slide-graphs-2026-11-04/planner-replay.json`. The offline replays
span ten 224-qubit circuits, XY/History, and multiple memory configurations.
Restricting to the intended finite CD configurations (3/4 and 6/8):

| Minimum lead | Replays | Scheduled preparations | Observed active-layer lead |
|---|---:|---:|---|
| 2 | 40 | 127,467 | All 2; none greater than 2 |
| 1 | 40 | 195,255 | All 1; none greater than 1 |

The full 160-replay set, including 8/8 and 256/256, likewise has no scheduled
preparations earlier than the configured minimum: 363,137 at lead 2 and 461,715
at lead 1. These are **offline admission decisions**, not independent physical
simulation repetitions or successful pair deliveries.

As a second check, the 45 completed corrected CD runs available during inspection
contained 135,428 pair records in `pairs_dynamic_60.csv`. Mapping each recorded
`generation_layer` and `target_layer` to ranks of communication-active layers in
its own command's trace gave lead 1 for every record. This is launch-layer
attribution; it does not assert that generation completed at that layer boundary.
Of those records, 106,488 have an original logical-layer difference greater than
two because intervening empty layers are skipped. Therefore “no earlier than
L-2” is supported on the **active-layer axis**, not the raw trace layer numbers.

This supports testing a local history horizon, but does not prove that older
traffic has no predictive value or that pairs cannot physically remain held
longer. Current preparation search remains 1–8 active layers; it is not narrowed
by the routing change.

## What changed

`tools/routing_research/heavy_routing.py` previously accumulated visits to every
selected route's cores over all preceding active layers. This was compile-time
route-demand history, **not runtime memory occupancy**.

The default now keeps selected-route visits from the previous two active layers.
For current active layer L, history is visits in L-1 plus L-2; earlier visits are
subtracted. Current-layer assignments still update a separate local load counter
inside `choose`. Empty logical layers do not age the default window.

Unchanged: shortest-path candidates; primary incremental overload cost at the
routing reference capacity; current-layer squared-load cost; history weight 0.1;
longest-migration-first route ordering; deterministic path tie breaking; compiler
planning/admission; physical SeQUeNCe protocols.

Controls:

- `--history-window-layers 2`: new default, two preceding layers plus current load.
- `--history-window-layers 0`: legacy cumulative history for reproduction.
- `--history-layer-basis active`: default, ignore empty layers.
- `--history-layer-basis logical`: count raw trace layers instead.

Each newly generated route gets `routing_policy.json`, including window, basis,
weight, reference capacity and trace SHA-256. Existing cached traces are not
automatically regenerated. Use a fresh output directory for this experiment.

## Validation and first structural comparison

All 12 tests in `tools/routing_research/tests/test_heavy_routing.py` passed.
Coverage includes window eviction, empty-layer handling, logical-layer boundary,
cumulative reproduction, forgetting an obsolete hotspot, deterministic/legal
paths, and unchanged XY/YX/greedy behavior.

All 25 tests in the broader `tools/routing_research/tests` suite also passed.
Two archive tests initially encountered a sandbox temporary-directory permission
error; rerunning with `tempfile.tempdir` set to a workspace-local test directory
resolved the environment issue without changing test or routing behavior.

Two fresh QFT builds used the same actual 224-qubit mapped circuit, mapping seed
42, 4x4 mesh and routing reference capacity 4. Both builds replayed and verified
every placement transition, endpoint and legal shortest path, including empty
layers. Output: `output/history-algo-update-2026-11-04/{window2,cumulative}`.

| Compile-time metric | Cumulative | Two active layers |
|---|---:|---:|
| Migrations | 5,118 | 5,118 |
| Hop requests | 11,076 | 11,076 |
| Sum of route demand above capacity 4 | 1,278 | 1,424 |
| Overloaded core-layers | 720 | 767 |
| Peak route demand per core-layer | 11 | 11 |
| Peak link hop count | 900 | 935 |

The excess-demand proxy is **11.42% worse** for the rolling policy in this QFT
check. This is not latency, physical occupancy or a fidelity result. No new
physical runs were launched for this change. The evidence does not justify
claiming the rolling policy is more optimal; retain the separate branch until
matched physical comparisons establish its merits.

Reproduce using the compatible study Python environment:

```powershell
python -m unittest discover -s tools/routing_research/tests -p test_heavy_routing.py -v
python -B tools/routing_research/heavy_routing.py build --inputs output/benchmark-matrix-224-2026-11-04/inputs --output output/history-algo-update-2026-11-04/window2 --algorithms history --workloads qft
python -B tools/routing_research/heavy_routing.py build --inputs output/benchmark-matrix-224-2026-11-04/inputs --output output/history-algo-update-2026-11-04/cumulative --algorithms history --workloads qft --history-window-layers 0
```
