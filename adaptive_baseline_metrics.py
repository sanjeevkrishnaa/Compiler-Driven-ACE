"""Lifecycle accounting for generic ACE CGP/ACGP cached EPR pairs."""

from __future__ import annotations


class AdaptiveBaselineObserver:
    """Deduplicate two-endpoint ACE callbacks into physical-pair records.

    ACE represents the same link EPR at both routers, often with reversed tuple
    orientation.  This observer canonicalizes the memory endpoints so that a
    generated/expired pair is counted once, while a utilization is associated
    with the application request that consumed it.
    """

    def __init__(self):
        self.records: dict[tuple, dict] = {}

    @staticmethod
    def _key(pair: tuple) -> tuple:
        return tuple(sorted((tuple(pair[0]), tuple(pair[1]))))

    def on_pair_generated(self, pair: tuple, timestamp: int) -> None:
        key = self._key(pair)
        self.records.setdefault(key, {
            "generated_at_ps": timestamp,
            "used_at_ps": None,
            "used_by_request_id": None,
            "fidelity_at_use": None,
            "expired_at_ps": None,
            "expiry_reason": None,
        })

    def on_pair_utilized(self, pair: tuple, request_id: int, timestamp: int,
                         fidelity: float) -> None:
        record = self.records.get(self._key(pair))
        if record is None:
            # A pair may have been generated before observation was attached;
            # retain it rather than silently treating it as a generated pair.
            return
        if record["used_at_ps"] is None and record["expired_at_ps"] is None:
            record.update({"used_at_ps": timestamp,
                           "used_by_request_id": request_id,
                           "fidelity_at_use": fidelity})

    def on_pair_expired(self, pair: tuple, timestamp: int, reason: str) -> None:
        record = self.records.get(self._key(pair))
        if record is not None and record["used_at_ps"] is None \
                and record["expired_at_ps"] is None:
            record.update({"expired_at_ps": timestamp, "expiry_reason": reason})

    def snapshot(self) -> dict:
        records = list(self.records.values())
        generated = len(records)
        used = [record for record in records if record["used_at_ps"] is not None]
        expired = [record for record in records if record["expired_at_ps"] is not None]
        remaining = generated - len(used) - len(expired)
        fidelities = [record["fidelity_at_use"] for record in used
                      if record["fidelity_at_use"] is not None]
        storage_ms = [(record["used_at_ps"] - record["generated_at_ps"]) / 1e9
                      for record in used]
        return {
            "generated_pairs": generated,
            "utilized_pairs": len(used),
            "expired_pairs": len(expired),
            "remaining_pairs": remaining,
            "expiry_percentage": 100 * len(expired) / generated if generated else 0.0,
            "waste_percentage": 100 * (len(expired) + remaining) / generated
            if generated else 0.0,
            "average_fidelity_at_use": (
                sum(fidelities) / len(fidelities) if fidelities else None
            ),
            "average_storage_time_ms": (
                sum(storage_ms) / len(storage_ms) if storage_ms else None
            ),
            "records": records,
        }
