# ACE legacy baseline, 2026-10-24

The behaviour of ACE **before any correctness change**: 164 rows from 22 cases, every output column
stored as the exact text the runner wrote. Later gates must reproduce it exactly in legacy mode.
Tool and rules: [`tools/ace_correctness/README.md`](../../tools/ace_correctness/README.md).
Plan: [`docs/plans/ace-correctness-and-congestion-program.md`](../../docs/plans/ace-correctness-and-congestion-program.md).

| File | Contents |
| --- | --- |
| `legacy/baseline.csv` | 164 rows x 51 columns: case, strategy, physics seed and every runner output |
| `legacy/manifest.json` | environment, ACE source hashes, SeQUeNCe commit, hash of every input trace |
| `record.log` | progress of the recording run |
| `check_hashseed777.log` | the independent rerun described below |

## What was recorded from

| | |
| --- | --- |
| ACE commit | `14cfdd2`, no tracked file modified (the tool, tests and plan were added afterwards and change no ACE source) |
| SeQUeNCe | v0.8.1, commit `cf5283cd`, no tracked file modified |
| Python / platform | 3.13.3, macOS arm64 |
| numpy / scipy / networkx / qutip | 2.5.3 / 1.18.1 / 3.6.1 / 5.3.1 |
| `PYTHONHASHSEED` while recording | unset |
| Skipped cases | none; the external QFT-96 trace matched its SHA-256 `61d97492...3da1` |

## What was verified about it

* **Reproducible in fresh processes.** A complete rerun of all 22 cases, with `PYTHONHASHSEED=777`
  and `--strict`, reproduced **164 of 164 rows identically**, including CGP, ACGP and QFT-96.
* **Independent of Python's hash seed.** A separate comparison of Random-16, all five strategies,
  three physics seeds, under hash seeds 0, 1, 12345 and random gave byte-identical output.
* **Matches the locked validation table.** `verify-locked`: the 18 recorded means for Random-16 and
  QFT-96 are within 1e-12 of `results/compiler_repaired_validation.csv`.
* **Matches the published budget study.** `verify-published`: 90 MQT rows compared with
  `results/ace_congestion_budget_2026-10-23/results.csv`, 90 identical on every shared column. The
  other 74 recorded rows (Random-16, QFT-96 and the fixed policy) are cases that study never ran.

## Scope and limits

* This is a regression reference for legacy ACE, **not** a congestion measurement. Legacy ACE
  cannot show memory contention (see the budget study report).
* The MQT cases use mapping seed 42 only.
* CGP and ACGP are covered only on Random-16.
