"""Summarize full-chain experiments, requiring complete runs and clean physical audits."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, stdev

METRICS = ("request_latency_mean_ms", "request_latency_p95_ms", "end_to_end_latency_ms",
           "average_admission_wait_ms", "avg_entanglement_generation_time_ms",
           "pregenerated_success_rate", "average_delivered_epr_fidelity",
           "compiler_waste_percentage", "compiler_expiry_percentage", "average_storage_time_ms")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("roots", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    aggregates, all_rows, audit_rows = [], [], []
    for root in args.roots:
        with (root / "all_seeds.csv").open() as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            if float(row["completion_rate"]) != 1:
                raise ValueError(f"incomplete run: {root} {row['variant']} {row['seed']}")
            audit = root / row["variant"] / f"audit_{row['strategy']}_{row['seed']}.json"
            report = json.loads(audit.read_text())
            if report["violations"]:
                raise ValueError(f"failed audit: {audit}")
            audit_rows.append(dict(phase=root.name, variant=row["variant"], seed=row["seed"],
                                   events=report["events"], violations=0))
            all_rows.append({"phase": root.name, **row})
        odg = {r["seed"]: float(r["request_latency_mean_ms"]) for r in rows if r["variant"] == "odg"}
        for variant in sorted({r["variant"] for r in rows}):
            group = [r for r in rows if r["variant"] == variant]
            result = dict(phase=root.name, variant=variant, observations=len(group))
            for key in METRICS:
                values = [float(r[key]) for r in group if r[key] != ""]
                result[key + "_mean"] = mean(values) if values else None
                result[key + "_sd"] = stdev(values) if len(values) > 1 else None
            reductions = [100 * (odg[r["seed"]] - float(r["request_latency_mean_ms"])) / odg[r["seed"]]
                          for r in group if r["seed"] in odg]
            result["paired_latency_reduction_percent_mean"] = mean(reductions) if reductions else None
            aggregates.append(result)
    for name, rows in (("aggregate.csv", aggregates), ("all_seeds.csv", all_rows), ("audits.csv", audit_rows)):
        with (args.output / name).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({"runs": len(all_rows), "audits": len(audit_rows), "violations": 0,
                      "aggregate": str(args.output / "aggregate.csv")}))


if __name__ == "__main__":
    main()
