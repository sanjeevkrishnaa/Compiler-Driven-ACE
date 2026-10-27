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

The report and portable reproduction command are maintained in the documentation
index at `docs/README.md`.
