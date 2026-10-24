#!/usr/bin/env python3
"""Build results.csv from the per-invocation folders of an Experiment 1 run that was stopped before its driver wrote one.

Each folder ``runs/<workload>_m<mapping seed>_c<memories>_<policy>`` that holds both summary.csv and metadata.json is a finished
invocation (three physics seeds); anything else is ignored.  The rows are those of the runner, with the workload, mapping seed and
memory count added from the folder name.  Wall-clock times are not recovered (the driver records them only when it finishes).

    python tools/experiment1/assemble_results.py RUN_DIR OUTPUT.csv
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


def main(run_dir: Path, output: Path) -> int:
    rows, skipped = [], []
    for folder in sorted((run_dir / "runs").iterdir()):
        if not (folder / "summary.csv").exists() or not (folder / "metadata.json").exists():
            skipped.append(folder.name)
            continue
        match = re.match(r"(.+)_m(\d+)_c(\d+)_(.+)$", folder.name)
        workload, mapping_seed, memories = match.group(1), int(match.group(2)), int(match.group(3))
        with (folder / "summary.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                rows.append(dict(workload=workload, mapping_seed=mapping_seed, total_memories=memories, run_status="ok", **row))
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows from {len(rows) // 3} invocations -> {output}; skipped incomplete: {skipped or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
