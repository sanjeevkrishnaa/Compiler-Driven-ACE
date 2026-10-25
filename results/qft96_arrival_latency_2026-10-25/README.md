# QFT-96 arrival-to-completion latency rerun

This folder reruns the mid-term QFT-96 trace from the exact remote base
`origin/codex/ace-scheduler-correctness` commit `1cc7eb6`, with metric version
3.  The metric is each hop's completion time minus its arrival time; the 5.3 ms
reservation/pre-generation buffer is real elapsed time and is included.

`legacy_midterm_reproduction/` uses the historical serial scheduler.  Its
manager-local first-submission metric reproduces the old values plus 5.3 ms:
ODG **6.398 ms** and Dynamic **5.986 ms** (mean of seeds 0, 1, 2).  Its fair
arrival metric includes serialization before the request was submitted: ODG
**36.214 ms**, Dynamic **33.486 ms**.  It remains a historical reproduction,
not the final comparison.

`per_qubit_corrected/` uses the corrected event-admission scheduler.  The fair
arrival metric is ODG **7.457 ms** and Dynamic **15.143 ms**.  Whole-trace
makespan is respectively **10.026 s** and **14.018 s**.  Thus Dynamic remains
slower under the corrected, four-memory configuration even after fixing the
latency definition.

Each subfolder records raw seed-level CSV rows and metadata.  Do not compare
these metric-version-3 values with the prior metric-version-2 tables.
