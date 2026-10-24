# Physical parameters in ACE: where they come from, and the decision still open (Gate 5)

Nothing in the simulator was changed. ACE values are read from `config/final_config/grid_4x4_ace_3.json` and
`router_net_topo_adaptive.py`; units are SeQUeNCe's (read from its source). The two papers' values are read from
their own Table I (PDFs in the BTP folder, text extracted): the ACGP paper (arXiv 2607.14592, the group's
multi-core paper) and the adaptive-continuous protocol paper (arXiv 2502.01964, Zhan et al., SeQUeNCe, metro-scale
network). Where a number is not in a source, the cell says so.

| Parameter | ACE (config/code) | ACGP paper, Table I | ACP paper, Table I (2502.01964) |
|---|---|---|---|
| Memory coherence time | 1 s (`coherence_time: 1`, read as seconds) | **1 ms** | 2 s |
| Memory efficiency | **0.95** | **0.85** | 0.6 |
| BSM detector efficiency | 0.95 | 0.95 | 0.95 |
| Initial pair fidelity (memory fidelity) | 0.95 | not stated | 0.95 |
| Gate / measurement fidelity | 0.99 / 0.99 | not stated | 0.99 / 0.99 |
| End-node processing delay / forward delay | 100 us / 20 us per hop (overwritten in code) | not stated | 100 us / 20 us |
| Fibre attenuation | 0.0002 dB/m = 0.2 dB/km | not stated | 0.2 dB/km |
| Link length | **0.025 m = 2.5 cm** (router to BSM, SeQUeNCe reads metres) | not stated | **10 km** |
| Photonic BSM success rate | SeQUeNCe default (0.5 in the ACP paper) | not stated | 0.5 |
| Communication memories per core | set per run | 4 | 10 per node, at most 5 for caching |
| Swapping probability | not exercised (every trace hop joins adjacent cores) | 0.95 | 1 |

## What this shows

* **ACE's physics is the metro-network ACP setup, carried over.** Its classical delays, detector efficiency, memory
  and gate fidelities and fibre attenuation match the ACP paper's Table I. Three things differ from it: the link length
  (10 km there, 2.5 cm in ACE, evidently rescaled to a chip), the coherence time (2 s there, 1 s in ACE) and the memory
  efficiency (0.6 there, 0.95 in ACE).
* **The group's own multi-core paper states different values for the two that matter most:** coherence 1 ms and memory
  efficiency 0.85. ACE matches neither paper on those two.
* **Why it matters.** At millisecond scale the pre-generation results depend on coherence: with 1 s, unused pairs
  essentially never expire in these runs (none did, in any audited run); with 1 ms, a pair held across a few layers
  would decohere. Fidelity of every pre-generation result changes with it. On-demand fidelity is set by generation, not
  waiting (it did not vary with the budget in any of 45 cells), so on-demand results are the least exposed.
* A web search for an independent source fixing these numbers for a multi-core architecture found none; published
  figures vary by platform (cold-atom memories with about 1 ms coherence and 87% efficiency in one experiment, erbium
  spins above 1 s in the SeQUeNCe paper's own motivation).

## Decision for you and your guide

Until it is made, ACE's current values stay in use, and every result reported from them should say so.

> ACE's simulator takes its physics from the metro-scale adaptive-continuous paper (coherence 2 s, memory efficiency 0.6,
> 10 km links), rescaled in our config to coherence 1 s, memory efficiency 0.95 and 2.5 cm links. Our ACGP paper's Table I
> states coherence 1 ms and memory efficiency 0.85 for the chip-scale cores. For the compiler study, which should we report:
> (a) the ACGP Table I values, (b) ACE's current values, or (c) both, as a sensitivity sweep on coherence time? And was
> the 2.5 cm router-to-BSM link intended as an on-chip distance? If coherence is 1 ms, what lifetime should a pre-generated
> pair's reservation have (the runs use 1000 ms, which is longer than the coherence time itself)?

## Harness constants (not physical)

Request window 50 ms, pre-generation lead 5.3 ms, retry period 1 ms, empty-layer gap 5 ms. These dominate the
makespan on short traces, are identical under the legacy and the per-qubit scheduler, and are arguments or module
constants, not hidden values.
