# ACE correctness tools

`baseline.py` records and checks a bit-for-bit baseline of ACE's current (legacy) behaviour.
Every change to the scheduler or reservation layer must leave that behaviour exactly as it was.
Plan: [`docs/plans/ace-correctness-and-congestion-program.md`](../../docs/plans/ace-correctness-and-congestion-program.md).

## What a baseline is

`record` runs a fixed set of cases through `run_trace_comparison.py` and stores every output column
as the exact text the runner wrote. `check` reruns them and compares the text column by column, so
a difference in the last digit of a float is a failure.

| Case | Trace | Strategies | Seeds |
| --- | --- | --- | --- |
| `random16` | `data/tracegen/random16_d80_seed303.txt` (repo) | on-demand, fixed, dynamic, continuous, adaptive-continuous | 0-9 |
| `qft96` | the locked QFT-96 trace, outside the repo, SHA-256 checked | on-demand, fixed, dynamic | 0-2 |
| `mqt-<workload>-s42-c<N>` | the committed characterization archive, mapping seed 42 | on-demand, dynamic | 0-2 |
| `mqt-<workload>-s42-c4-fixed` | same | fixed | 0-2 |

The MQT workloads are `ghz`, `graphstate`, `draper_qft_adder`, `qft`, `qaoa`, at 2, 4 and 32
communication memories per core (compiler memories and generation capacity are N - 1, so one
memory always stays with demand). CGP and ACGP run only on `random16`: they generate continuously
until the stop time, and on the MQT traces that costs minutes per run.

## Commands

```bash
# record (about 15 minutes); pass the external QFT-96 trace or that case is reported as SKIPPED
python tools/ace_correctness/baseline.py record --output results/<dir>/legacy \
    --external qft96=/path/to/qft_requests.txt

# check a baseline against the current code; --strict fails if any case was skipped
python tools/ace_correctness/baseline.py check --golden results/<dir>/legacy \
    --external qft96=/path/to/qft_requests.txt --strict

# tie a baseline to results the project already published
python tools/ace_correctness/baseline.py verify-locked    --golden results/<dir>/legacy
python tools/ace_correctness/baseline.py verify-published --golden results/<dir>/legacy
```

`--only REGEX` selects cases. `--hash-seed N` sets `PYTHONHASHSEED` for the child runs.

## Comparison rules

* A row is (case, strategy, physics seed). Every recorded column must be present and equal as text.
* Columns that only the fresh run has are reported, not failed, so later gates can add metrics.
* A case whose trace is unavailable is SKIPPED and listed; `--strict` makes that a failure.
* `manifest.json` records the ACE commit and source hashes, the SeQUeNCe commit and whether it is
  modified, Python and package versions, and the SHA-256 of every trace. `check` fails if a trace
  changed and warns if the environment differs.

## Tests

```bash
python -B -m unittest discover -s tools/ace_correctness/tests -v
```
