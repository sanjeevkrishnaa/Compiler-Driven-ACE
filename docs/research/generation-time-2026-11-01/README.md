# EPR generation time and the Dynamic strategy (2026-11-01 to 11-02)

Question: what is the EPR generation time in ACE, which parameters change it, and when does the
compiler-driven Dynamic strategy gain from a slower generation?

- **Report (40 pages):** [main.pdf](../../latex/generation_time_study/report/main.pdf), source in `docs/latex/generation_time_study/report/`
- **Plan, hypotheses and deviations (written before the sweeps):** [plan.md](plan.md)
- **Data:** [data/](data/) holds one `*_summary.csv` (mean, spread, 95% interval per setting) and one `*_trials.csv.gz` (one row per strategy and seed) per experiment, plus `link_screen.csv`, `anatomy.csv`, `hypotheses.json`, `model_*.csv`, `validation_check.csv` and `audit_runs.json`.
- **Raw per-case results:** [evidence.zip](../../../results/generation_time_2026-11-01/evidence.zip) with its checksum, and the 14 routed traces in `results/generation_time_2026-11-01/traces/`.
- **Code:** `tools/generation_time_study/` (14 tests). No file under `ace/` was changed.

Headline results, each with its evidence in the report:

1. Generation time is (4 or 5) x delay / p: about 1.1 ms at the baseline, measured on 360,000 pairs.
2. Slower generation helps Dynamic in absolute terms throughout and in relative terms up to about 3 ms of generation time.
3. The gain depends on the 5 ms charged per empty layer; without it, default Dynamic loses to ODG at normal speed.
4. QAOA's loss at chip-scale control comes from the fixed 1 ms retry waits (confirmed by a controlled test).
5. Letting Dynamic use all memories helps QFT by 16-24%, and borrowing or demand-first helps QAOA by 7-14%; all eight tuned choices held on unseen seeds.
