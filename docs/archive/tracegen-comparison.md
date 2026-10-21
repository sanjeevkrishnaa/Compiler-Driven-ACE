> Historical implementation/context record. Current behavior and validated results are documented in [compiler-repair-validation.md](../reports/compiler-repair-validation.md).

# TraceGen-to-ACE physical comparison

`tracegen` (QM2026) exports the same format consumed by ACE's
`compiler_trace.py`: an initial logical-qubit placement followed by ordered,
layer-grouped, single-hop migrations. ACE validates the evolving placement and
requires every request to be an adjacent hop in its configured mesh.

## Generated workload suite

The generated inputs are in `data/tracegen/`:

| Trace | TraceGen command parameters | Layers | Hop requests |
| --- | --- | ---: | ---: |
| `qft16_seed101.txt` | QFT, 16 cores, width 16, seed 101 | 126 | 46 |
| `cuccaro16_seed202.txt` | Cuccaro adder, 16 cores, width 16, seed 202 | 218 | 9 |
| `random16_d80_seed303.txt` | Random circuit, width 16, depth 80, 70% two-qubit gates, seed 303 | 33 | 62 |

All use HQA with OEE initial placement, a 4x4 mesh, eight qubit slots per
core, two reserved ancillas, and link reliability sampled from `[0.8, 1.0]`.
They can be regenerated from the `tracegen` checkout, for example:

```powershell
python generate.py --benchmark random --initial-placement oee --cores 16 `
  --reliability-min 0.8 --reliability-max 1.0 --width 16 --depth 80 `
  --two-qubit-prob 0.7 --seed 303 `
  --output ..\ACE\data\tracegen\random16_d80_seed303.txt
```

## Fair physical comparison

Run the comparison from the ACE checkout with the project's SeQUeNCe fork on
`PYTHONPATH`:

```powershell
$env:PYTHONPATH = "C:\Users\sanje\Desktop\BTP\repo\qnoc-stress-testing\SeQUeNCe"
python run_trace_comparison.py `
  --trace data\tracegen\random16_d80_seed303.txt `
  --seeds 0,1,2,3,4,5,6,7,8,9 `
  --output output\tracegen\random16_10seed
```

The runner compares `on-demand`, `continuous`, `adaptive-continuous`, `fixed`,
and `dynamic`. The autonomous baselines run ACE's real continuous generator;
the compiler strategies use the one-shot compiler controller. Every run uses
the same physical topology, four memories per core, three compiler-memory
capacity, request windows, seeds, and conflict-free request batches. This last
point is important: an ACE core cannot truly serve simultaneous requests that
share it, so the runner serializes only those conflicts for *all* strategies.

## Initial seed-0 results

Results below come from the physical simulator and are stored as `summary.csv`
under `output/tracegen/`. They are exploratory single-seed observations, not
statistical claims.

| Workload | Strategy | Requests completed | Mean latency (ms) | Delivered fidelity | Retries |
| --- | --- | ---: | ---: | ---: | ---: |
| QFT first 15 layers (4 requests) | On-demand | 4/4 | 1.5000 | 0.9498 | 0 |
|  | Continuous | 4/4 | 0.3000 | 0.8161 | 3 |
|  | Adaptive-continuous | 4/4 | 0.3500 | 0.8345 | 3 |
|  | Fixed compiler | 4/4 | 0.9750 | 0.8371 | 3 |
|  | Dynamic compiler | 4/4 | 1.1500 | 0.9386 | 1 |
| Cuccaro (9 requests) | On-demand | 9/9 | 0.8778 | 0.9498 | 0 |
|  | Continuous | 9/9 | 0.6889 | 0.8457 | 2 |
|  | Adaptive-continuous | 9/9 | 0.7667 | 0.8511 | 2 |
|  | Fixed compiler | 9/9 | 0.7667 | 0.9185 | 2 |
|  | Dynamic compiler | 9/9 | 0.7667 | 0.9325 | 2 |
| Random (62 requests) | On-demand | 62/62 | 1.2291 | 0.9498 | 14 |
|  | Continuous | 62/62 | 0.2887 | 0.8351 | 60 |
|  | Adaptive-continuous | 62/62 | 0.3887 | 0.8510 | 56 |
|  | Fixed compiler | 62/62 | 1.1371 | 0.9058 | 31 |
|  | Dynamic compiler | 62/62 | 1.0597 | 0.9239 | 44 |

The autonomous methods minimize request latency here by holding speculative
pairs, at a visible fidelity and retry cost. Dynamic compiler scheduling is
the stronger compiler option: it improves on-demand latency while retaining
materially higher delivered fidelity than the autonomous caches. Its pre-ready
hit rate remains workload-dependent (14.52% on the random trace), so the next
step is a ten-seed study rather than drawing a ranking from seed 0.
