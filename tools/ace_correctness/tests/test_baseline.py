import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ace_correctness import baseline
from tools.ace_correctness.baseline import (
    Case, Comparison, Mismatch, MissingTrace, TraceSource, build_cases, compare_rows,
    environment_differences, parse_externals, read_baseline, select_cases, write_baseline,
)


def row(**overrides):
    base = {"strategy": "dynamic", "seed": "0", "average_request_latency_ms": "0.5", "completion_rate": "1.0"}
    base.update(overrides)
    return base


class CompareRowsTests(unittest.TestCase):
    KEY = ("c", "dynamic", "0")

    def test_identical_rows_pass(self):
        result = compare_rows({self.KEY: row()}, {self.KEY: row()})
        self.assertTrue(result.ok)
        self.assertEqual((result.compared, result.identical), (1, 1))

    def test_last_digit_of_a_float_is_a_difference(self):
        old = {self.KEY: row(average_request_latency_ms="0.5000000000000001")}
        new = {self.KEY: row(average_request_latency_ms="0.5")}
        result = compare_rows(old, new)
        self.assertFalse(result.ok)
        self.assertEqual(result.mismatches, [
            Mismatch(self.KEY, "average_request_latency_ms", "0.5000000000000001", "0.5")])

    def test_equal_values_with_different_text_are_a_difference(self):
        """'1' and '1.0' are the same number but not the same output."""
        result = compare_rows({self.KEY: row(completion_rate="1")}, {self.KEY: row(completion_rate="1.0")})
        self.assertFalse(result.ok)

    def test_missing_fresh_row_fails(self):
        result = compare_rows({self.KEY: row()}, {})
        self.assertFalse(result.ok)
        self.assertEqual(result.missing, [self.KEY])

    def test_missing_fresh_column_fails_but_extra_column_is_informational(self):
        shorter = {k: v for k, v in row().items() if k != "completion_rate"}
        self.assertFalse(compare_rows({self.KEY: row()}, {self.KEY: shorter}).ok)
        longer = {self.KEY: row(new_metric="7")}
        result = compare_rows({self.KEY: row()}, longer)
        self.assertTrue(result.ok)
        self.assertEqual(result.new_columns, {"new_metric"})

    def test_rows_only_in_the_fresh_run_are_listed_not_failed(self):
        other = ("c", "fixed", "0")
        result = compare_rows({self.KEY: row()}, {self.KEY: row(), other: row(strategy="fixed")})
        self.assertTrue(result.ok)
        self.assertEqual(result.unexpected, [other])

    def test_empty_comparison_is_ok_by_itself(self):
        self.assertTrue(Comparison().ok)


class CaseDefinitionTests(unittest.TestCase):
    def test_case_names_are_unique_and_strategies_are_known(self):
        cases = build_cases()
        self.assertEqual(len({c.name for c in cases}), len(cases))
        for case in cases:
            self.assertTrue(set(case.strategies) <= set(baseline.ALL_STRATEGIES), case.name)
            self.assertTrue(case.seeds and len(set(case.seeds)) == len(case.seeds), case.name)

    def test_autonomous_strategies_only_run_on_the_fast_case(self):
        autonomous = {"continuous", "adaptive-continuous"}
        for case in build_cases():
            if set(case.strategies) & autonomous:
                self.assertEqual(case.name, "random16")

    def test_budget_cases_keep_one_memory_for_demand_and_scale_generation(self):
        for case in build_cases():
            if case.name.startswith("mqt-") and not case.name.endswith("fixed"):
                self.assertEqual(case.compiler_memories, case.total_memories - 1)
                self.assertEqual(case.generation_capacity, case.compiler_memories)

    def test_command_is_fully_explicit(self):
        case = next(c for c in build_cases() if c.name == "mqt-ghz-s42-c4")
        command = case.command(Path("/t/trace.txt"), Path("/t/out"))
        for flag in ("--trace", "--strategies", "--seeds", "--total-memories", "--compiler-memories",
                     "--generation-capacity", "--delta-layers", "--dynamic-lookahead-layers",
                     "--coherence-time-layers", "--compiler-reservation-ms", "--stop-time-s", "--output"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--strategies") + 1], "on-demand,dynamic")

    def test_select_cases_filters_by_regex_and_rejects_empty_selection(self):
        self.assertEqual({c.name for c in select_cases("^random16$")}, {"random16"})
        with self.assertRaises(SystemExit):
            select_cases("no-such-case")


class TraceSourceTests(unittest.TestCase):
    def test_external_trace_needs_a_path(self):
        with self.assertRaises(MissingTrace):
            TraceSource("external", "qft96").materialize(Path("."), {})

    def test_external_trace_is_verified_by_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "t.txt"
            trace.write_bytes(b"hello")
            good = hashlib.sha256(b"hello").hexdigest()
            path, digest = TraceSource("external", "x", good).materialize(Path(tmp), {"x": trace})
            self.assertEqual((path, digest), (trace, good))
            with self.assertRaises(ValueError):
                TraceSource("external", "x", "0" * 64).materialize(Path(tmp), {"x": trace})

    def test_missing_external_file_is_reported_as_missing(self):
        with self.assertRaises(MissingTrace):
            TraceSource("external", "x").materialize(Path("."), {"x": Path("/does/not/exist")})

    def test_repo_trace_is_read_and_hashed(self):
        source = TraceSource("repo", "data/tracegen/random16_d80_seed303.txt")
        path, digest = source.materialize(Path("."), {})
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_archive_trace_agrees_with_the_archives_own_checksum_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, digest = TraceSource("archive", "ghz/seed_42/requests.txt").materialize(Path(tmp), {})
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_archive_trace_that_contradicts_the_checksum_list_is_rejected(self):
        with mock.patch.object(baseline, "_archive_checksums", return_value={"ghz/seed_42/requests.txt": "0" * 64}):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    TraceSource("archive", "ghz/seed_42/requests.txt").materialize(Path(tmp), {})


class BaselineFileTests(unittest.TestCase):
    def test_round_trip_preserves_text_exactly_and_orders_rows_by_case_and_strategy(self):
        rows = {
            ("random16", "dynamic", "1"): row(seed="1", strategy="dynamic", average_request_latency_ms="0.1"),
            ("random16", "on-demand", "0"): row(seed="0", strategy="on-demand", average_request_latency_ms="1.10"),
            ("random16", "dynamic", "0"): row(seed="0", strategy="dynamic", average_request_latency_ms="0.123456789012345678"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            write_baseline(Path(tmp), rows, {"schema": 1})
            again, manifest = read_baseline(Path(tmp))
            self.assertEqual(again, rows)
            self.assertEqual(manifest, {"schema": 1})
            with (Path(tmp) / "baseline.csv").open(newline="") as handle:
                order = [(r["strategy"], r["seed"]) for r in csv.DictReader(handle)]
            self.assertEqual(order, [("on-demand", "0"), ("dynamic", "0"), ("dynamic", "1")])


class MiscTests(unittest.TestCase):
    def test_parse_externals(self):
        self.assertEqual(parse_externals(["a=/x/y", "b=~/z"])["a"], Path("/x/y"))
        for bad in ("noequals", "=path", "name="):
            with self.assertRaises(SystemExit):
                parse_externals([bad])

    def test_environment_differences_names_only_what_changed(self):
        recorded = {"python": "3.13.3", "packages": {"numpy": "2.5.3", "scipy": "1.18.1"}, "sequence": {"commit": "abc"}}
        current = {"python": "3.13.3", "packages": {"numpy": "2.5.3", "scipy": "1.19.0"}, "sequence": {"commit": "abc"}}
        self.assertEqual(environment_differences(recorded, current), ["scipy: recorded 1.18.1 vs now 1.19.0"])


if __name__ == "__main__":
    unittest.main()
