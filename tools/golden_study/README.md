# Golden-study control plane

This directory contains the project-owned control plane for the fresh ACE study.
It does not launch simulations by itself. Its first responsibility is preventing an
unregistered trace, seed, or configuration from becoming a reported result.

```bash
python tools/golden_study/studyctl.py init \
  --root results/golden_study_2026-10-25
python tools/golden_study/studyctl.py validate \
  --root results/golden_study_2026-10-25
python tools/golden_study/studyctl.py render-latex \
  --root results/golden_study_2026-10-25 \
  --latex-output docs/latex/ace_report/generated/golden_study_contract.tex
```

`validate --run-ready` is deliberately stricter. It refuses execution until the
contract names non-overlapping training and evaluation physics seeds, mapper seeds,
a preregistered adaptive-policy threshold, and ten workload traces with hashes.

No runner has implicit workloads, seed ranges, memory capacities, or routing choices.
Those values belong in the study contract and inventory, not in Python constants.
