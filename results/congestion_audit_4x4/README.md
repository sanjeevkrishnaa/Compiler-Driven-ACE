# 4x4 static congestion audit

This is a **trace-level capacity diagnostic**, not a physical-simulation
result. It asks what becomes due at the same compiler layer, before any
pre-generation policy chooses when to prepare a pair. It therefore identifies
the structural congestion that no scheduler can make disappear without
deferring, serialising, rerouting, or adding capacity.

Generated with `../../congestion_diagnostic.py` on 2026-10-21.

## Definitions

For a request `r` due in source layer `l`, let its endpoints be `src(r)` and
`dst(r)`. The endpoint demand at core `c` is:

```
D(l, c) = count of requests r in l such that c is src(r) or dst(r)
```

At endpoint capacity `K`, a core is overloaded precisely when `D(l,c) > K`.
An *affected request* is a request with at least one overloaded endpoint. The
reported excess is `sum(max(D(l,c) - K, 0))` over all core-layer pairs. It is a
lower bound on the number of endpoint-demand units that cannot be simultaneously
resident or reserved; it is not a count of failed physical generations.

Route-link demand is independently measured by routing each request
horizontal-first and then vertical (XY) across undirected 4x4 mesh links. The
link figures are demand counts, not a statement that one link can serve exactly
one request per simulator time unit.

## Two workload families -- do not mix their claims

1. **Locked QFT** (`qft_locked_96q.json`) is the audited study workload:
   96 logical qubits, 16 cores, 766 source layers, and 4,954 *elementary
   adjacent-core transfers*. Its SHA-256 is
   `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1`.
   Every transfer has one physical hop, so route-link pressure is directly
   trace pressure.
2. **Fixed-mapping suite** is the available common suite for QFT, Cuccaro,
   Draper, and MCMTV: `4x4`, `q8` (eight computation-qubit slots per core),
   dense mapping (`s1`). Its requests are cross-core gates, which can be
   multi-hop. These four are comparable *with each other*. They are not a
   replacement for the locked 96-qubit QFT experiment.

## Headline results

| Trace | Source / active layers | Requests | Mean requests per active layer | Max requests in a layer | Mean XY hops/request |
|---|---:|---:|---:|---:|---:|
| Locked QFT (96q) | 766 / 227 | 4,954 | 21.82 | 62 | 1.00 |
| Fixed QFT (4x4 q8 s1) | 1,018 / 614 | 15,552 | 25.33 | 64 | 2.68 |
| Fixed Cuccaro (4x4 q8 s1) | 1,513 / 609 | 678 | 1.11 | 63 | 2.07 |
| Fixed Draper (4x4 q8 s1) | 699 / 641 | 7,744 | 12.08 | 35 | 2.93 |
| Fixed MCMTV (4x4 q8 s1) | 884 / 393 | 399 | 1.02 | 2 | 4.09 |

## Endpoint-memory pressure

`p95` and mean here are calculated over nonzero core-layer demands, so they
describe a core *when it participates in communication*, rather than being
diluted by idle cores.

| Trace | Mean nonzero demand | p95 | Peak demand | Peak core (x,y), layer |
|---|---:|---:|---:|---|
| Locked QFT | 4.28 | 14 | 28 | (1,2), 372 |
| Fixed QFT | 6.77 | 8 | 8 | (1,0), 958 |
| Fixed Cuccaro | 1.09 | 1 | 8 | (0,0), 0 |
| Fixed Draper | 3.75 | 8 | 8 | (3,3), 633 |
| Fixed MCMTV | 1.01 | 1 | 2 | (1,1), 379 |

The peak alone can be misleading. Cuccaro has a 63-request burst at its first
layer and hence a peak endpoint demand of eight, but it is otherwise mostly
sparse. Draper and QFT repeatedly overload many active layers; MCMTV is almost
entirely endpoint-feasible even at two memories.

## Capacity sweep: endpoint overload

Each cell is `overloaded active layers / affected requests (percent of all
requests)`. An overloaded layer has at least one core with demand above K.

| Trace | K=1 | K=2 | K=3 | K=4 |
|---|---|---|---|---|
| Locked QFT | 221 / 4,948 (99.88%) | 159 / 4,485 (90.53%) | **158 / 4,307 (86.94%)** | 150 / 3,687 (74.43%) |
| Fixed QFT | 476 / 15,408 (99.07%) | 471 / 15,392 (98.97%) | **467 / 15,374 (98.86%)** | 463 / 15,352 (98.71%) |
| Fixed Cuccaro | 8 / 77 (11.36%) | 1 / 63 (9.29%) | **1 / 63 (9.29%)** | 1 / 63 (9.29%) |
| Fixed Draper | 587 / 7,630 (98.53%) | 529 / 7,430 (95.95%) | **467 / 7,172 (92.61%)** | 413 / 6,884 (88.90%) |
| Fixed MCMTV | 6 / 12 (3.01%) | 0 / 0 (0.00%) | **0 / 0 (0.00%)** | 0 / 0 (0.00%) |

At K=3, the endpoint-demand excesses are: locked QFT 4,497; fixed QFT 18,335;
fixed Cuccaro 78; fixed Draper 7,282; and fixed MCMTV 0. These are not pair
failures. They quantify the unavoidable simultaneous reservation shortfall if
the whole source layer is treated as one deadline.

## Route-link pressure

| Trace | Mean nonzero link demand | p95 | Peak link demand | Peak link (x,y) -- (x,y), layer |
|---|---:|---:|---:|---|
| Locked QFT | 2.10 | 5 | 10 | (1,1) -- (1,2), 444 |
| Fixed QFT | 8.19 | 16 | 32 | (1,1) -- (2,1), 764 |
| Fixed Cuccaro | 1.09 | 1 | 16 | (0,1) -- (0,2), 0 |
| Fixed Draper | 4.88 | 12 | 32 | (1,0) -- (2,0), 381 |
| Fixed MCMTV | 1.00 | 1 | 1 | (0,0) -- (1,0), 880 |

This shows two distinct bottlenecks. Fixed QFT and Draper have sustained
endpoint pressure **and** concentrated route links, so an admission policy must
consider both. Locked QFT has a higher endpoint spike (28) than link spike
(10), making endpoint memory/reservation the dominant first constraint. MCMTV
has longer individual routes on average but almost no simultaneous overlap;
path length by itself is not congestion.

## Benchmark-specific interpretation

### Locked 96-qubit QFT

This is the real target workload for the current physical study. The 158
overloaded layers at K=3 and 4,307 affected transfers reproduce the presentation
diagnostic. Moving from three to four memories only reduces overloaded layers
from 158 to 150. Thus a fixed lead alone cannot make most QFT requests ready:
the requested pairs want the same endpoint slots at the same time. The proposed
scheduler should defer low-urgency speculative pairs whenever their endpoint
reservation would compete with a nearer-deadline request.

### Fixed QFT

This is the most globally congested member of the common fixed-mapping suite.
At K=3, 467 of 614 active layers overload an endpoint and 98.86% of all
cross-core gates touch an overloaded endpoint. Its p95 endpoint demand is
already eight, and its peak link demand is 32. Extra memory from K=3 to K=4
barely changes the affected-request fraction (98.86% to 98.71%). A congestion
policy should be evaluated here as a severe stress test, but only after it is
shown safe on the locked QFT trace.

### Fixed Draper

Draper is also highly congested but less extreme than fixed QFT. K=3 affects
92.61% of requests, falling to 88.90% at K=4. The larger capacity response is
useful: it suggests a mix of burst capacity pressure and route contention rather
than a completely saturated pattern. Its high mean route length (2.93) and
p95 link demand (12) make route-aware scoring meaningful.

### Fixed Cuccaro

Cuccaro is sparse overall: only 678 remote requests in 609 active layers. Its
apparent K=3 congestion is dominated by one early burst: layer 0 has 63
requests, a peak endpoint demand of eight, and a peak link demand of 16. The
remaining profile is largely uncongested. This is a good test of whether the
scheduler prevents one burst from over-reserving memory without penalising
ordinary low-contention traffic.

### Fixed MCMTV

MCMTV is the least endpoint-congested benchmark. At K=2 or above, it has zero
overloaded layers and zero affected requests. Its average route is the longest
(4.09 hops), yet link demand never exceeds one. It is the clean control case:
an endpoint-aware policy should behave almost like the existing future-aware
policy, with deferrals close to zero. If it slows MCMTV materially, the policy
is too conservative.

## Reproducing or extending the audit

```bash
repo='/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE'
python3 "$repo/congestion_diagnostic.py" \
  --trace '/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/qft_requests.txt' \
  --mesh 4x4 \
  --output "$repo/results/congestion_audit_4x4/qft_locked_96q.json"

python3 "$repo/congestion_diagnostic.py" \
  --traffic "$repo/real_benchmarks/traffic_files/draper_fixed_4x4_q8_s1_traffic.json" \
  --output "$repo/results/congestion_audit_4x4/draper_fixed_4x4_q8_s1.json"
```

For a new workload, first lock its circuit specification, compiler/Qiskit
version, qubit count, mapping, route rule, and trace hash. Generate its traffic
once, then run this diagnostic before running stochastic physical simulations.
