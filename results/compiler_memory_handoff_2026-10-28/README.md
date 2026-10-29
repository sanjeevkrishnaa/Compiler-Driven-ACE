# Compiler-memory handoff evidence — 28 October 2026

`evidence.zip` preserves the 32 reported full-trace runs, exact commands,
metadata/source hashes, per-request timing, pair records, physical audit
outcomes, source snapshots, and the 159-test verification log for the local
compiler-memory ownership fix. It is committed so the evidence does not depend
on ignored `output/` directories.

The comparison uses four physical communication memories per core, full-chain
preparation, ready-first admission, and eligibility-to-completion latency with
zero artificial buffer. Main XY seeds are 6–9; confirmation uses XY seeds 10–13
and YX seeds 6–7. All included runs complete with clean physical/order audits.

The archive intentionally retains original execution paths in its metadata.
Its embedded source snapshots and hashes identify the code used for each phase;
subsequent directory organization does not rewrite this historical provenance.

Physical dependency: SeQUeNCe 0.8.1 at
`cf5283cdfd6692a82a090d15fb09fbc01bd322fc`.

The [report and portable reproduction command](../../docs/research/compiler-pregeneration/compiler-memory-handoff-2026-10-28.md)
and [documentation index](../../docs/README.md) describe current paths.
`evidence.sha256` verifies the unchanged archive.

## Directory-cleanup verification

The ownership fix was committed as `a8f1b22` before the organization-only change.
Simulator modules and the 16 moved study-data files are unchanged from that
commit. The CLI moves require only their repository-root path adjustment.

- All 186 tests discovered in `test/` pass.
- All three relocated compiler CLI entry points load successfully.
- All 76 local Markdown links in the updated navigation/study pages resolve.
- A complete QFT-96 mesh/XY reproduction through the moved launcher completes
  all 3,876 requests for both policies with clean ownership/order audits:
  ODG 1.3344489197 ms; full-chain C=4 0.6587009809 ms (seed 6).

The log, run metadata, summary and physical audits are retained under
`cleanup-verification/`. Its paths record the actual local verification run.
