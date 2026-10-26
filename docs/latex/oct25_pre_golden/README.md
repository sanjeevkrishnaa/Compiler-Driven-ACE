# October 25: routing and Dynamic preparation, before the golden study

This is a separate retrospective report for the experiments before the golden
study. It does not incorporate the October 26 QFT campaign or relabel its results.

- [Compiled report](main.pdf)
- [LaTeX source](main.tex)
- [All per-seed observations](data/per_seed_results.csv)
- [All key metric means and sample SDs](data/all_metrics.csv)
- [Source hashes and Git blobs](data/source_ledger.csv)
- [Validation evidence](data/validation.json)
- [Research commits](data/commits.csv)

The exact source boundary is `4aa334542e9b9c8fe7a5f9cc8fe48ee2e4d2fa55`,
the parent of first golden-study commit `44fa139`. The generator reads historical
Git objects, rather than today's working-tree result files. Original source
links in the PDF point to that fixed revision.

## Reading order

1. Model, request eligibility, latency, makespan and metric denominators.
2. Why the midterm/local timings and corrected fair timings differ.
3. Placement recovery and the five-route QFT-96 comparison.
4. Controlled routing interventions, static congestion and per-core waiting.
5. All 13 Dynamic launch variants on two routes, including unsuccessful trials.
6. Thirty-seed first-hop/adaptive confirmation, readiness, fidelity and waste.
7. Threshold selection and memory/admission screens.
8. Ten **48-qubit** workloads; QFT here must not be called QFT-96.
9. Separate HQA/T-HQA mapper-only comparison and implemented-but-unswept controls.
10. Limitations, commit links, data inventory and reproduction instructions.

Every research graph is immediately followed by its numerical table and a CSV
link. Unrounded per-seed values and all archived runner columns are retained.
The four-model historical timing matrix is explicitly labelled as documented
aggregate evidence where original per-seed CSVs were not versioned.

## Rebuild

From the repository root, with NumPy, SciPy and Matplotlib available:

```sh
python tools/build_oct25_report.py
cd docs/latex/oct25_pre_golden
tectonic main.tex
```

This rebuild does not run ACE. It checks archived seeds and completion, exact
control reproduction, and independently parses/replays all 21 route traces and
recomputes their excess demand. Statistics describe stochastic variation on
fixed workloads; the three-seed generalisation is exploratory. The threshold
confirmation includes the screening seeds, rather than being wholly held out.
