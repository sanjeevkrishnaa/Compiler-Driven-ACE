# Ready-first compiler allocation sweep — 28 October 2026

Historical extra-slot consumption results. The subsequent
[memory handoff correction](compiler-memory-handoff-2026-10-28.md) fixes the C=4
collapse; the measurements below are retained as the before-fix record.

Full QFT-96 mesh/XY, four physical communication memories per core, physics seeds 6–9.
All compiler policies retain full-chain eligibility, a two-layer minimum lead,
eight-layer lookahead, zero artificial buffer, event admission and ready-pair priority.
Generation capacity in the offline planner equals C; physical hardware is unchanged.

Values are means across the same four seeds; p95 is the mean of per-run p95 values.

| Policy | Mean latency ms | p95 ms | Makespan s | Pre-ready % | Fidelity | Compiler expiry % | Completion % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ODG | 1.335462 | 3.150081 | 4.060008 | 0.00 | 0.949813 | 0.00 | 100 |
| Dynamic C=1 | 1.117096 | 2.800078 | 3.828425 | 27.63 | 0.944829 | 0.00 | 100 |
| Dynamic C=2 | 0.984647 | 2.775053 | 3.675670 | 52.24 | 0.940704 | 0.00 | 100 |
| Dynamic C=3 | 0.960416 | 2.750058 | 3.576115 | 69.29 | 0.937614 | 0.00 | 100 |
| Dynamic C=4 | 396.580257 | 993.175065 | 165.330826 | 19.61 | 0.941077 | 76.25 | 100 |

C=4 is deliberately tested at the user's request, outside the earlier C<M campaign.
The implementation requires a separate application communication memory to consume
a compiler-cached pair. Four overlapping compiler reservations can occupy every slot
and block consumption. Ready-first cannot admit without memory at both endpoints.
Reservation expiry eventually breaks the stall, rather than giving a permanent deadlock.
The reservation window remains 1,000 ms, explaining the approximately one-second tail.
Expired compiler pairs are excluded from delivered fidelity; mostly fresh fallback
delivery can therefore hide severe preparation waste if only fidelity is inspected.

C=1 and ODG were freshly run; C=2 and C=3 reuse the audited ready-first observations
on the identical trace and seeds. C=4 was freshly run with a diagnostic option that
allows incomplete results to be reported, but every C=4 run actually completed 100%.
The summary independently requires completion, clean physical/order audits, and zero
fitting-ready bypasses. No reserves or generation shortcuts were added for C=4.

All 152 compiler tests pass. This is one workload/route and four seeds, not a universal optimum.

[All seed rows](data/ready-allocation-2026-10-28/all_seeds.csv) ·
[All metrics and sample SDs](data/ready-allocation-2026-10-28/aggregate.csv) ·
[Input provenance](data/ready-allocation-2026-10-28/study.json)
