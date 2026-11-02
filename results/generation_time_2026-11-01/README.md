# Evidence: EPR generation-time study

- `traces/`: the 14 routed traces used (`traces_manifest.json` holds their SHA-256 and provenance). The XY and greedy QFT/QAOA traces equal the 2026-10-30 traces after line-ending normalisation.
- `evidence.zip`: for each of the 544 cases, `spec.json` (the exact case) and `reduced.json` (per-seed, per-class results with the audit outcome), plus the single-link probe files under `link/`. Unzip into `output/generation_time_study/` to rerun the collection scripts. Per-request timing and pair files are not kept; any case can be regenerated from its spec because runs are deterministic in the seed.
- `SHA256SUMS`: checksum of the archive.
