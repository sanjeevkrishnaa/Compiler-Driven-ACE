# 224-qubit benchmark matrix (4 November 2026)

Requested matrix: ten committed 224-qubit QASM benchmarks, both XY and History
routing, nine configurations, physics seed 60 (180 runs). Mapping seed is 42.
Each core has 16 **data** slots, initially 14 occupied and two migration vacancies.
The separate communication bank has four or eight slots. CD uses three or six
of these respectively. The unlimited case starts at 256 and is accepted only
when capacity is nonbinding, including an offline plan comparison against 512.
CGP/ACGP retain the existing configuration's autonomous cache limit of three.
All strategies use the same physical config, memory efficiency 0.8, 10 ns empty
layers and four-reference-memory entity seeding. CD uses the current main policy,
not the alternate wall-clock planner.

## Run and resume

Use the existing SeQUeNCe-study Python environment:

```powershell
python -u tools/benchmark_matrix.py
```

The runner maps the **committed QASM** for each benchmark once, then produces
both routing variants from the same frozen mapping. Physical simulations run
one at a time. Completed outputs are checkpointed under
`output/benchmark-matrix-224-2026-11-04/runs/<benchmark>/<routing>/<configuration>`.
It skips complete runs on restart and fails on protocol audit/completion errors.
Inspect `progress.json`, `failure.json` (if present), and each run's `run.log`.

The Excel builder is in that output folder. It reads `results.json`, includes
all 180 planned rows, and leaves unfinished measurements empty with Pending
status. The final workbook is `outputs/benchmark-matrix-224-2026-11-04/benchmark_results.xlsx`.
The builder runs automatically when the queue is resumed and after each workload
in the updated runner. A hidden finalizer waits for the original queue before
resuming/validating/exporting, never intentionally launching a second queue.

## Metrics

- Latency: eligibility to EPR delivery, including admission wait, per routed hop.
- Workload duration: full simulated workload completion time.
- Delivered fidelity: all completed hop requests. CD additionally reports the
  fidelity of compiler-generated pairs when used.
- Coverage: physical cached-pair availability at first application submission;
  this is not an assertion of actual adoption. Actual CD pre-ready hits are
  reported separately by the compiler controller.
- Wastage: unique physical cached pairs (canonicalized across endpoints), split
  into reservation/coherence expiry and still-unused-at-finish. There is no
  separate eviction policy. Total waste includes unused pairs; unused does not
  imply expired. ODG-only generation is excluded from cached-pair accounting.

Study-only read-only lifecycle observers wrap the physical cache callbacks.
A BV/XY/CGP-4 run without observers exactly reproduced the observed latency
and fidelity, validating that these measurements did not alter that execution.
The production scheduler and protocols are unchanged by the study harness.

These are physical SeQUeNCe **entanglement-delivery** simulations, not data
teleportation or full computational circuit execution. One seed was requested;
no confidence intervals or statistical significance are claimed.
