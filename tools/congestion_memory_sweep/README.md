# Congestion memory-budget sweep

Measures what communication-memory congestion costs in request latency and EPR fidelity, on
the workloads the ten-workload characterization identified as congested.

Two cases, as posed:

- **Case 1** — 2, 3 or 4 communication memories per core: congestion present.
- **Case 2** — 32 per core: congestion removed. A 64-memory arm on QFT confirms 32 already
  saturates.

Results and discussion: [`docs/reports/congestion-memory-sweep.md`](../../docs/reports/congestion-memory-sweep.md).

## Backend

Runs on **native SeQUeNCe**, not ACE. ACE's `node.py` needs `msg.dst` / `msg.src` from the
`anub-dota/qnoc-stress-testing` fork, which is no longer reachable (`Repository not found`),
so ACE cannot execute here. Compare policies within a backend only; never compare these
milliseconds with ACE milliseconds.

## Prerequisites

1. A SeQUeNCe checkout on branch `codex/native-compiler-4x4-physical`
   (validated at commit `7b8cb2eb8998777f9f9a5ab4f39ef687f645b8d2`), on `PYTHONPATH`.
2. The ten-workload traces, extracted from
   `results/congestion/mqt_ten_workload_congestion_results.zip`. The sweep reads
   `<workload>/seed_<42|43|44>/requests.txt` from the extracted
   `mqt_ten_workload_study/` directory.
3. Python 3.13 with SeQUeNCe's runtime dependencies (networkx, numpy, scipy, qutip).

## Running

Edit the four path constants at the top of `run_sweep.py` — `SCRATCH`, `ZIP`, `SEQ`, `PY` —
to match your machine, then:

```bash
python run_sweep.py
```

It writes `results.csv` incrementally (one row per completed run) and a per-run directory
under `runs/`, printing progress as it goes. Expect roughly 135 minutes for the full
126-run matrix; GHZ and Graph state take seconds each, QFT and QAOA about 16 seconds per run.

## Matrix

| Axis | Values |
| --- | --- |
| Workloads | `qft`, `qaoa`, `draper_qft_adder`, `graphstate`, plus `ghz` as control |
| Mapping seeds | 42, 43, 44 |
| Communication memories | 2, 3, 4, 32 (+64 on QFT) |
| Strategies | `odg`, `dynamic` |
| Physics seeds | 3 per run |

## Memory partitioning

The sweep sets `pregeneration_memories` per strategy:

- `odg` → 0. The whole bank serves demand, nothing is reserved for a compiler. This isolates
  contention from any pre-generation effect.
- `dynamic` → `communication_memories - 1`, reserving one demand slot. This reproduces the
  project's established 3+1 split at a budget of four.

Note that `odg` and `dynamic` take different code paths in the runner. `odg` goes to
`simulate_sequence_workload`, which honours the config directly. `dynamic` goes to
`simulate_native_compiler_trace`, which under static allocation recomputes
`compiler_memories = communication_memories - on_demand_reserve` with `on_demand_reserve`
defaulting to 1 — which happens to equal what the config requests, so the two agree. Verify
the recorded `memory_partition` in each run record rather than assuming.

**The two strategies are not directly comparable here**, because on-demand gets the whole bank
for demand while dynamic gets one slot. Use the runner's `matched-odg` strategy for that
comparison. Within-strategy budget sweeps are unaffected.

## Verifying a result set

Each run's `study.json` records `trace_sha256` and the resolved `config`. Check that every
row's trace hash matches the source `requests.txt`, and that `config.communication_memories`
matches the intended budget, before trusting any aggregate.
