# HQA versus T-HQA placement — QFT-96

This is a mapper-only comparison, not an ACE latency result. It holds the
QFT-96 circuit, 4x4 mesh, 8 mapper slots/core, two reserved initial slots/core,
OEE initial placement, and every mapper configuration fixed. It varies only the
placement objective: HQA versus T-HQA. Seeds 42–44 vary the synthetic link
reliability map.

| Metric, mean ± sample SD over three reliability seeds | HQA | T-HQA |
| --- | ---: | ---: |
| Mapper cost | 33,915.14 ± 17,084.56 | 24,696.88 ± 8,850.08 |
| EPR-latency proxy | 9,910.62 ± 4,525.00 | 9,921.46 ± 2,897.32 |
| Path-quality sum | 612.65 ± 164.26 | 807.73 ± 234.23 |
| Physical hops | 4,954 | 3,876 |
| Residual operations | 0 | 0 |
| Intermediate infeasible attempts | 1,739 | 1,904 |

T-HQA reduces the exported-hop count by 1,078 (21.76%). Its reliability-weighted
cost is lower in two of the three seeds and higher in seed 43, so this evidence
does not prove it is universally superior. T-HQA is selected as the placement
policy for **new** routing/pre-generation studies; HQA remains the required
historical and controlled-placement baseline.

Raw mapper output and exact command metadata are in `qft96.*` for seed 42 and
in `seed_43/` and `seed_44/` for the other two seeds.
