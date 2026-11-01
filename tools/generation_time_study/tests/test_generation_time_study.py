"""Run with: python -m pytest tools/generation_time_study/tests  (SEQUENCE_ENGINE set)."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import experiments
import knobs as kn
import run_case
import run_matrix


def config():
    return json.loads(kn.CONFIG.read_text())


def test_default_knobs_leave_the_configuration_unchanged():
    assert kn.apply_config(config(), kn.Knobs()) == config()
    assert kn.Knobs().key() == "base"


def test_a_knob_changes_only_its_own_field():
    template = kn.apply_config(config(), kn.Knobs(memory_efficiency=0.6))["templates"][kn.TEMPLATE]
    assert template["MemoryArray"]["efficiency"] == 0.6
    assert template["SingleHeraldedBSM"]["detectors"][0]["efficiency"] == 0.95
    template = kn.apply_config(config(), kn.Knobs(detector_efficiency=0.6))["templates"][kn.TEMPLATE]
    assert [d["efficiency"] for d in template["SingleHeraldedBSM"]["detectors"]] == [0.6, 0.6]
    assert template["MemoryArray"]["efficiency"] == 0.95


def test_applying_knobs_does_not_mutate_the_input():
    original = config()
    kn.apply_config(original, kn.Knobs(distance_scale=1000, memory_efficiency=0.5))
    assert original == config()


def test_distance_scales_both_channel_lists():
    scaled = kn.apply_config(config(), kn.Knobs(distance_scale=10))
    assert scaled["qchannels"][0]["distance"] == config()["qchannels"][0]["distance"] * 10
    assert scaled["cchannels"][0]["distance"] == config()["cchannels"][0]["distance"] * 10


def test_microsecond_is_used_only_by_the_classical_delay_formula():
    source = (kn.ROOT / "ace" / "topology" / "router_net_topo_adaptive.py").read_text()
    uses = [line for line in source.splitlines() if "MICROSECOND" in line and "import" not in line]
    assert uses == ["            return distance / SPEED_OF_LIGHT + hop_count * 20 * MICROSECOND + 100 * MICROSECOND"]


def test_the_empty_layer_constant_is_the_only_gap_used():
    source = (kn.ROOT / "ace" / "simulation" / "request_scheduler.py").read_text()
    assert source.count("EMPTY_LAYER_GAP_MS") == 2
    assert re.search(r"_finish_layer\(layer, completion_time, gap_ms=0\)", source)


def test_success_probability_of_the_default_configuration():
    assert abs(kn.success_probability(kn.Knobs()) - 0.5 * (0.95 * 0.95) ** 2) < 1e-5


def test_attempt_cost_follows_the_primary():
    assert kn.attempt_messages(0, 1) == 4 and kn.attempt_messages(1, 0) == 5
    assert kn.hit_messages(0, 1) == 2 and kn.hit_messages(1, 0) == 3


def test_request_classes_prefer_a_hit_and_separate_late_pairs():
    pairs = [dict(status="used", actual_request_id="3", prepared_before_request="True"),
             dict(status="used", actual_request_id="4", prepared_before_request="False"),
             dict(status="expired", actual_request_id="", prepared_before_request="False")]
    assert run_case.request_classes(pairs) == {3: "hit", 4: "late"}


def test_every_base_case_matches_the_published_options():
    spec = experiments.case("qft", "history", 4, 3)
    assert (spec["lead"], spec["consumption"], spec["reservation_ms"], spec["priority"]) == (2, "handoff", 50.0, "ready-first")
    assert spec["generation_capacity"] == 3 and spec["chain_hops"] is None and spec["knobs"] == {}


def test_case_keys_identify_a_case_and_nothing_else():
    first = experiments.case("qft", "history", 4, 3)
    assert run_matrix.case_key(first) == run_matrix.case_key(experiments.case("qft", "history", 4, 3))
    assert run_matrix.case_key(first) != run_matrix.case_key(experiments.case("qft", "xy", 4, 3))


def test_argv_passes_every_option_the_study_varies():
    spec = experiments.case("qft", "history", 4, 3, lead=6, chain_hops=1, congestion=25, flags=["--demand-first"])
    argv = run_case.build_argv(spec, Path("c.json"), Path("o"))
    assert argv[argv.index("--planner-lead-layers") + 1] == "6"
    assert argv[argv.index("--chain-hops-prepared") + 1] == "1"
    assert argv[argv.index("--congestion-threshold") + 1] == "25"
    assert "--demand-first" in argv and "--audit-events" in argv and "--all-chain-hops" not in argv
