# Routing experiments

The researched EPR-delivery default is `handoff` (same physical pair, new owner).
The dated study uses that mode explicitly. `swap` is a separate-memory model
available as an explicit override. New metadata labels the latency scope as
entanglement delivery; the full data-teleportation circuit is not simulated.

`heavy_routing.py` compares seven compile-time path selectors on identical logical
migrations. It leaves the simulator, pre-generation policy, placement, layer
barriers, and memory budget unchanged.

| Name | Rule |
|---|---|
| `xy` | First coordinate, then second coordinate (core = 4 × first + second). |
| `yx` | Second coordinate, then first. |
| `greedy` | Longest migrations first; among shortest paths, minimize incremental demand above C=4, then squared core load. |
| `history` | Same greedy rule, with 0.1 × cumulative prior-layer core visits added to the secondary cost. |
| `minexcess` | Joint MILP selection among shortest paths; minimize total core demand above C=4, then hops. |
| `minhop` | Joint MILP among shortest paths, counting each hop endpoint; an internal relay counts twice to model incoming and outgoing pre-generation memories. |
| `detour2` | Same MILP, allowing paths up to shortest + two hops. |

All congestion-aware choices use the known circuit trace; none reads future
simulator outcomes. The MILP uses a two-second per-layer timeout and reports
unproved layers. The existing optimizer retains its supplied shortest XY paths
when there is no overload or no improving solution. Its small hop penalty breaks
ties; equal-cost shortest solutions can vary with solver versions.

Generate new 96-qubit MQT inputs with T-HQA (192 physical slots: eight data and
four communication slots/core, at least one initial data vacancy). The initial
budget is 96 occupied data slots + 32 free data slots + 64 communication memories:

```powershell
$env:PYTHONPATH=(Resolve-Path mapper).Path
python -B tools/congestion_study/run_study.py --mapper-dir mapper `
  --workloads qft draper_qft_adder qaoa --logical-qubits 96 --total-qubits 192 `
  --memory-slots 4 --seeds 42 --mapping-only --output output/routing-inputs96
python -B tools/routing_research/heavy_routing.py build `
  --inputs output/routing-inputs96 --output output/routing96
```

Use the compatible SeQUeNCe 0.8.1 runtime on `PYTHONPATH` for physical trials:

```powershell
$env:PYTHONPATH='C:/path/to/compatible/SeQUeNCe'
python -B tools/routing_research/heavy_routing.py simulate --output output/routing96 --seeds 60,61,62,63 --compiler-pair-consumption handoff
python -B tools/routing_research/report_heavy_routing.py --output output/routing96
```

The dated study additionally checked the two aggregate leaders and XY on fresh
QAOA simulator seeds, leaving their routes and weights frozen:

```powershell
python -B tools/routing_research/heavy_routing.py simulate --output output/routing96 `
  --algorithms greedy minhop xy --workloads qaoa --seeds 64,65,66,67 --simulation-dir validation --compiler-pair-consumption handoff
python -B tools/routing_research/report_heavy_routing.py --output output/routing96
```

`--algorithms` can restrict a build or simulation. The simulator resumes completed
route folders; use a new output/validation folder for a different seed set rather
than reusing an already completed one. It runs at most two subprocesses at once.

The physical comparison runs ODG and corrected compiler C=4, lookahead two,
ready-first admission and native pair ownership handoff, with zero additional
pre-generation buffer. Every trial must complete every hop and pass physical
invariant checks. Results include mean/p95 **logical migration** latency, so
detours cannot look faster merely by splitting a migration into more hops.
Migration latency sums each hop's eligibility-to-completion interval. The
per-qubit manager's `total_time_ms` already includes admission waiting; that
waiting must not be added a second time. The reporter checks the per-hop mean
against the simulator's canonical latency metric. Predecessor hops are sequential
and no dependency interval is counted twice.

Heatmaps distinguish compile-time route demand from measured admission waiting.
Route counts exceeding four are a contention proxy, not simultaneous occupancy.
Admission waiting is attributed to both incident cores for visualization and is
not a causal diagnosis of which endpoint blocked a request. Link heatmaps count
undirected hop requests, not bandwidth utilization. All algorithms in each panel
share a color scale and the same original-layer denominator.

Without `--inputs`, the build command also supports the older archived 48-qubit
inputs. Their three mapping-seed traces are identical, so simulation deliberately
uses seed 42 only rather than treating duplicate placements as replication.

The older `run_routing_study.py` performs a broader structural capacity sweep;
`simulate_rerouted.py` uses the historical budget-sweep runner. Use
`heavy_routing.py` for the corrected compiler scheduler comparison.
