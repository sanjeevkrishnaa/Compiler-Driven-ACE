"""Where the two request managers must agree: a workload with nothing to reorder.

Every GHZ layer is one chain (a qubit moving core to core), so the legacy per-core batches
and the per-qubit release are the same schedule.  Design prediction, tested on the real
simulator over the committed MQT GHZ trace rather than assumed.
"""
import dataclasses
import tempfile
import unittest
import zipfile
from pathlib import Path

from ace.observability.execution_events import canonical
from tools.ace_correctness.audit_trace import audit_trace

ARCHIVE = Path(__file__).resolve().parents[1] / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
GHZ = "mqt_ten_workload_study/ghz/seed_42/requests.txt"


def without_reservation_labels(events):
    """Events as plain tuples, minus the first-seen ordinal given to each reservation object.

    The ordinal numbers reservations by the order they first appear, so two runs that create
    the same reservations in a different order within one instant label them differently while
    doing exactly the same thing.
    """
    stripped = []
    for event in canonical(events):
        fields = dataclasses.asdict(event)
        fields.pop("reservation_id", None)
        stripped.append((type(event).__name__, tuple(sorted(fields.items()))))
    return stripped


@unittest.skipUnless(ARCHIVE.exists(), "committed MQT archive not present")
class GhzEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="ace-ghz-")
        with zipfile.ZipFile(ARCHIVE) as archive:
            cls.trace = Path(archive.extract(GHZ, cls.directory.name))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def both(self, strategy, seed):
        return (audit_trace(self.trace, strategy, seed=seed, scheduler="legacy"),
                audit_trace(self.trace, strategy, seed=seed, scheduler="per-qubit"))

    def test_on_demand_and_dynamic_runs_are_identical_event_for_event(self):
        for strategy in ("on-demand", "dynamic"):
            for seed in (0, 1):
                legacy, per_qubit = self.both(strategy, seed)
                self.assertEqual(canonical(legacy.events), canonical(per_qubit.events), (strategy, seed))
                self.assertEqual(legacy.makespan_ms, per_qubit.makespan_ms)

    def test_fixed_runs_are_identical_apart_from_reservation_labels(self):
        for seed in (0, 1, 2):
            legacy, per_qubit = self.both("fixed", seed)
            self.assertEqual(without_reservation_labels(legacy.events),
                             without_reservation_labels(per_qubit.events), seed)
            self.assertEqual(legacy.makespan_ms, per_qubit.makespan_ms)

    def test_every_run_completes_every_request_with_no_violation(self):
        for strategy in ("on-demand", "fixed", "dynamic"):
            for audit in self.both(strategy, 0):
                self.assertEqual((audit.completed, audit.requested), (audit.requested, audit.requested))
                self.assertEqual(audit.violations, [], strategy)


if __name__ == "__main__":
    unittest.main()
