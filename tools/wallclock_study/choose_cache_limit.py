"""Pick the CGP/ACGP cache limit from the tuning runs, by a rule fixed before the results were in.

Rule: the limit with the lowest mean latency over QFT and Draper (XY), CGP and ACGP, on tuning seeds 70 and 71.
One limit is used for both strategies on every workload.  The evaluation seeds (60-63) play no part in the choice.
"""
import csv, json, statistics as st, sys
from pathlib import Path

RUNS = Path(__file__).resolve().parents[2] / "output" / "wallclock_study" / "runs"
LIMITS = (1, 2, 3)
WORKLOADS = ("qft", "draper_qft_adder")
STRATEGIES = ("continuous", "adaptive-continuous")


def latency(folder: str, workload: str, strategy: str) -> float:
    rows = list(csv.DictReader((RUNS / folder / f"{workload}_xy_{strategy}" / "summary.csv").open()))
    return st.mean(float(r["request_latency_mean_ms"]) for r in rows)


def main() -> None:
    table = {L: {f"{w}/{s}": latency(f"cgp_tune_L{L}", w, s) for w in WORKLOADS for s in STRATEGIES} for L in LIMITS}
    odg = {w: latency("cgp_tune_odg", w, "on-demand") if False else st.mean(
        float(r["request_latency_mean_ms"]) for r in csv.DictReader((RUNS / "cgp_tune_odg" / f"{w}_xy_on-demand" / "summary.csv").open())) for w in WORKLOADS}
    score = {L: st.mean(table[L].values()) for L in LIMITS}
    chosen = min(LIMITS, key=lambda L: score[L])
    result = dict(chosen=chosen, mean_latency_by_limit=score, per_case=table, odg_reference=odg)
    (RUNS / "cgp_tune_choice.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    Path(sys.argv[1]).write_text(str(chosen)) if len(sys.argv) > 1 else None


if __name__ == "__main__":
    main()
