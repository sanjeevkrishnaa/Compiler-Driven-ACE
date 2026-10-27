# QFT-96 final report

This standalone report presents the completed QFT-96 experiment, with final
results rather than a history of changing results.

- [Compiled report](main.pdf)
- [Editable LaTeX](main.tex)
- [Complete numerical evidence](data/)
- [Validation](data/validation.json)
- [Metric coverage](data/metric_registry.csv)

Reading order: three-page methodology; verified congestion definitions and all
210 heatmaps in 70 readable three-seed groups; mesh memory curves starting with
latency; torus Dijkstra curves; every cache allocation; thirteen Dynamic launch
variants; final matched-budget tables; instrumentation and reproducibility.

Every research figure has a numerical table and committed CSV link. Main curves
use ODG C=0 and cached policies C=M-1; generation capacity follows max(1,C).
All legal C allocations remain in the allocation chapter and full metric CSV.
The report does not label a retrospective best allocation as a validated optimum.

The report builder independently checks the 1,639 base jobs and 143 variant jobs,
all 6,688 observations, source/config/trace identities, saved aggregate statistics,
placement replay, topology adjacency and every overload percentage in the 210
heatmap cells. Identical trace aliases are not treated as independent runs.

```sh
python -m tools.golden_study.build_qft96_final_report
cd docs/latex/qft96_final
tectonic main.tex
```

Use `--verify-only` to validate without plotting. No new simulation is launched.
This study uses two physics seeds and one workload; it is not proof of universal
policy superiority or a complete hardware QFT execution model.
