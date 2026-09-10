# Week 4 Verification Log

This file records post-report verification actions performed against the BTP
checkout. It is deliberately separate from the experimental result reports:
the commands below validate existing code and stored artifacts; they do not
create a new 30-seed policy result or replace any published measurement.

## 2026-09-10 — Documentation and evidence verification

**Checkout and starting commit**

- Repository: `Compiler-Driven-ACE`
- Branch: `codex/strict-compiler-4plus0`
- Starting documentation commit: `270c4f1` (`docs: add week four report introduction`)

### Focused implementation and audit test suite

Command:

```bash
.venv/bin/python -m pytest \
  test/test_compiler_trace.py \
  test/test_compiler_one_shot.py \
  test/test_experiment_contract.py \
  test/test_experiment_statistics.py \
  test/test_audit_compiler_results.py \
  test/test_audit_adaptive_baseline_results.py \
  -q
```

Outcome: **25 passed, 1 skipped** in 15.51 seconds.

Coverage includes trace parsing and validation, request-specific compiler pair
ownership, one-shot lifecycle release, memory and reservation invariants,
experiment-contract validation, paired-seed statistics, compiler-artifact
auditing, and adaptive-artifact auditing. The skipped test is optional.

Pytest emitted one environment-only warning because its cache directory was not
writable in the sandbox. This did not affect test execution or the result.

### Stored adaptive shared-pool artifact audit

Command:

```bash
MPLCONFIGDIR=/private/tmp/ace-mpl .venv/bin/python \
  audit_adaptive_baseline_results.py \
  output/qft_shared_pool_adaptive_30seed/runs.json \
  --expected-trace-sha256 \
  61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1 \
  --output /private/tmp/ace-week4-adaptive-audit.json
```

Outcome: **passed**.

| Audit property | Verified value |
|---|---:|
| Policy/seed cells | 90 |
| Request instances | 445,860 |
| Adaptive pair records | 21,226 |
| Trace SHA-256 | `61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1` |
| Audit errors | 0 |

The audit rechecks request completion, unique pair utilization, ordered pair
timestamps, fidelity bounds, per-run pair conservation, and agreement between
the raw pair trace and the stored summary counters. Its pass confirms that the
existing ACE ODG/CGP/ACGP shared-pool artifact remains internally consistent.

## Interpretation boundary

These verification results support reproducibility and integrity of the
existing Week 4 evidence. They do not change the reported latency, fidelity,
readiness, or expiry values. The remaining research items are still the native
physical CGP/ACGP shared-pool matrix, static-bank CGP/ACGP, reservation-aware
dynamic scheduling, and sensitivity studies on additional contracts.
