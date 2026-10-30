"""Regression coverage for first-run engine bootstrap."""
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.run_workload import ensure_engine, module_available, empty_failed_generation
import json


class EngineBootstrapTests(unittest.TestCase):
    def source(self, root):
        p = root / "third_party/SeQUeNCe/sequence/__init__.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")

    def test_existing_engine_needs_no_git_or_network(self):
        with tempfile.TemporaryDirectory() as d, patch("tools.run_workload.subprocess.run") as run:
            root = Path(d)
            self.source(root)
            self.assertEqual(ensure_engine(root), root / "third_party/SeQUeNCe")
            run.assert_not_called()

    def test_missing_engine_initializes_pinned_submodule(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch("tools.run_workload.subprocess.run", side_effect=lambda *a, **k: self.source(root)) as run:
                ensure_engine(root)
            run.assert_called_once_with(["git", "submodule", "update", "--init", "--recursive", "--", "third_party/SeQUeNCe"], cwd=root, check=True)

    def test_git_failure_explains_recovery(self):
        with tempfile.TemporaryDirectory() as d, patch("tools.run_workload.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            with self.assertRaisesRegex(RuntimeError, "Ensure Git and network"):
                ensure_engine(Path(d))

    def test_source_zip_without_submodule_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch("tools.run_workload.subprocess.run"):
            with self.assertRaisesRegex(RuntimeError, "Git clone"):
                ensure_engine(Path(d))


class DependencyAndRetryTests(unittest.TestCase):
    def test_missing_parent_module_is_reported_without_traceback(self):
        with patch("tools.run_workload.importlib.util.find_spec", side_effect=ModuleNotFoundError("mqt")):
            self.assertFalse(module_available("mqt.bench"))

    def test_metadata_only_failure_can_be_retried(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "study.json").write_text(json.dumps(dict(status="partial_failure", trials=[])))
            (p / "summary.csv").write_text("")
            self.assertTrue(empty_failed_generation(p))
            (p / "qaoa").mkdir()
            self.assertFalse(empty_failed_generation(p))

    def test_successful_generation_is_protected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "study.json").write_text(json.dumps(dict(status="complete", trials=[])))
            self.assertFalse(empty_failed_generation(p))
