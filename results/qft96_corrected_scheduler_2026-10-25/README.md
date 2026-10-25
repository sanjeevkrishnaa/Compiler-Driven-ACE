# QFT with 96 qubits (the mid-term trace) on the corrected scheduler

Trace: `qft96_requests.txt` (copy of `BTP/qft_requests.txt`, sha256 in `trace_sha256.txt`): 16 cores, 8 qubit slots per core, 96 qubits, 766 layers, 4,954 requests.
Configuration of the mid-term (and of every other experiment here): 4x4 mesh, `config/final_config/grid_4x4_ace_3.json`, 4 memories per core (3 compiler-eligible), delta 6, lookahead 8, coherence 10 layers,
compiler reservation 1000 ms, 5.3 ms lead, 50 ms request duration, scheduler `per-qubit`, physics seeds 0, 1, 2. Policies: on-demand and dynamic.

| | ODG | Dynamic |
|---|---|---|
| latency (ms), mean of 3 seeds ± sd | 2.157 ± 0.024 | 9.843 ± 0.025 |
| wait for a free memory (ms) | 1.055 | 9.157 |
| generation (ms) | 1.102 | 0.686 |
| delivered fidelity | 0.9498 | 0.9212 |
| ready-pair hit rate | - | 48.57% |
| whole-trace time (s) | 10.03 | 14.02 |

One trace, three physics seeds: the sd is over physics seeds only. For comparison the mid-term (old serialized scheduler) reported 1.0976 and 0.6858 ms. See `docs/plans/handoff-deep-study-2026-10-25.md`.
`run_<policy>/` hold the runner's summary.csv and metadata.json; `summary_means.csv` has the means.
