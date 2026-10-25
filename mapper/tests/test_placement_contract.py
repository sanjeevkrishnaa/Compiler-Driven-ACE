from __future__ import annotations

import json

import numpy as np

from tools.mapper_ace.export import export
from tools.mapper_ace.placement_contract import from_legacy, from_npz

LEGACY = """// Number of cores
4
// Number of qubit slots per core
2
// Number of qubits
3
// Initial placement: (qubit, core)
(0, 0)
(1, 0)
(2, 3)
// Inter-core communication requests: (qubit, src, dst)
// Layer 0
(0, 0, 1)
(0, 1, 3)
// Layer 1
// Layer 2
(2, 3, 2)
// Layer 3
// Layer 4
"""


def test_legacy_contract_keeps_declared_empty_layers(tmp_path) -> None:
    source = tmp_path / "requests.txt"
    source.write_text(LEGACY, encoding="utf-8")
    payload = from_legacy(source, dimensions=(2, 2), qubits_per_core=2, seed=1,
                          reliability_min=0.5, reliability_max=1.0, topology="mesh")
    assert len(payload["assignments"]) == 5                       # layers 0..4, two of them trailing and empty
    assert payload["initial_assignment"] == [0, 0, 3]
    assert payload["assignments"][0] == [3, 0, 3]                  # qubit 0 ended at core 3 after layer 0
    assert payload["assignments"][2] == [3, 0, 2]
    assert payload["assignments"][4] == payload["assignments"][2]
    assert payload["provenance"]["empty_trailing_layers_added"] == 2
    assert payload["provenance"]["legacy_logical_migrations"] == 2


def test_contract_round_trips_through_every_policy(tmp_path) -> None:
    source = tmp_path / "requests.txt"
    source.write_text(LEGACY, encoding="utf-8")
    payload = from_legacy(source, dimensions=(2, 2), qubits_per_core=2, seed=1,
                          reliability_min=0.5, reliability_max=1.0, topology="mesh")
    contract = tmp_path / "placement.json"
    contract.write_text(json.dumps(payload), encoding="utf-8")
    for policy in ("xy", "yx", "shortest_reliable", "max_reliability"):
        manifest = export(contract, tmp_path / policy, policy)
        assert manifest["placement"]["timeslices"] == 5
        assert manifest["placement"]["logical_migrations"] == 2
        rows = [json.loads(line) for line in (tmp_path / policy / "migrations.jsonl").read_text().splitlines()]
        assert {(r["qubit"], r["source_core"], r["destination_core"]) for r in rows} == {(0, 0, 3), (2, 3, 2)}


def test_npz_contract_uses_the_mappers_own_partition(tmp_path) -> None:
    npz = tmp_path / "mapping.npz"
    placements = np.array([[1, 0], [1, 2]], dtype=np.int32)
    np.savez(npz, initial=np.array([0, 0], dtype=np.int32), placements=placements, mesh=np.array([2, 2]))
    payload = from_npz(npz, seed=3, reliability_min=0.1, reliability_max=1.0, qubits_per_core=2, topology="mesh")
    assert payload["dimensions"] == [2, 2]
    assert payload["assignments"] == placements.tolist()
    assert payload["provenance"]["mapper_partition_exact"] is True
