"""Create immutable fixed-policy contracts for every static profile and lead."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "experiments" / "qft_4x4_comparison_v1.json"
OUTPUT = ROOT / "experiments" / "fixed_lead_static"
PROFILES = ("static-3plus1", "static-2plus2", "static-1plus1")
LEADS = range(1, 7)


def main() -> None:
    base = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_id = {profile["id"]: profile for profile in base["profiles"]}
    OUTPUT.mkdir(exist_ok=True)
    for profile_id in PROFILES:
        profile = by_id[profile_id]
        for lead in LEADS:
            payload = dict(base)
            payload["study_id"] = f"qft-4x4-{profile_id}-fixed-delta{lead}-v1"
            payload["scheduler"] = dict(base["scheduler"], fixed_delta_layers=lead)
            payload["profiles"] = [dict(profile, id=f"{profile_id}-fixed-delta{lead}",
                                        policies=["fixed"])]
            payload["comparison_rules"] = dict(
                base["comparison_rules"],
                primary=("compare fixed leads one through six only within this "
                         "repository, static profile, locked trace, and paired seeds"),
            )
            name = f"qft_4x4_{profile_id}_fixed_delta{lead}_v1.json"
            (OUTPUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
