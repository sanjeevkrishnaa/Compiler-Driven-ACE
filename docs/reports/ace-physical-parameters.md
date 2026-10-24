# Physical parameters in ACE, against the group's ACGP paper (Gate 5)

Nothing here has been changed. This is the table a decision needs. ACE values are read from
`config/final_config/grid_4x4_ace_3.json` and `router_net_topo_adaptive.py`; the paper column is Table I of
arXiv 2607.14592 (read from the PDF text). Units are SeQUeNCe's (read from its source).

| Parameter | ACE | ACGP paper, Table I | Differs? |
|---|---|---|---|
| Memory coherence time | `coherence_time: 1`; SeQUeNCe reads seconds, so 1 s | 1 ms | yes, 1000 times longer in ACE |
| Memory efficiency | 0.95 | 0.85 | yes |
| BSM detector efficiency | 0.95 | 0.95 | no |
| Communication qubits per core | set per run (the studies use 2 to 32; default 4 in the audits) | 4 | by run |
| Computation qubits per core | not a modelled quantity in ACE | 8 | not applicable |
| Swapping probability | not used: every trace hop joins adjacent cores, so no swap happens | 0.95 | not exercised |
| Memory fidelity | 0.95 | not in Table I | unknown |
| Gate / measurement fidelity | 0.99 / 0.99 | not in Table I | unknown |
| Router to BSM fibre | `distance: 0.025`, `attenuation: 0.0002`; SeQUeNCe reads metres and dB per metre, so 2.5 cm | not in Table I | **possible unit slip**: 0.025 looks like kilometres |
| Router to router classical delay | overwritten to distance/c + 20 us per hop + 100 us | not stated | unverified origin |
| Request window, pre-generation lead, retry period, empty-layer gap | 50 ms, 5.3 ms, 1 ms, 5 ms | not physical | harness constants |

What follows from this, stated with its limit:

* **Coherence.** With 1 s coherence, unused pairs essentially never expire at the millisecond scale of these
  runs; with the paper's 1 ms, pairs held across layers would decohere within a layer or two. That would
  change every pre-generation result, and the fidelity numbers. Which value the study intends is a decision
  for you and your guide.
* **Fibre length.** If 0.025 was meant as 25 m or 25 km, photon travel time and loss change. I did not test
  how much the 2.5 cm reading matters for latency; generation times of about 1 ms in the audits are
  dominated by what I have not separated.
* The harness constants are arguments or module constants and are the same in the old and new schedulers.

Nothing in the experiments should be described as using the paper's parameters until this is decided.
