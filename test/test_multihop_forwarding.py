"""End-to-end requests over several hops: relayed classical messages must keep their original sender.

The 4x4 mesh has classical channels between neighbours only, so a message between two cores that are not
neighbours is relayed hop by hop.  A swap at a relay that is not next to an end node needs such a message
(its resource-manager handshake with that end).  If the receiver took the last relay for the sender, it would
reply to the relay, the relay would release the end's protocol, and the swap would never start: requests over
three or more hops never completed.  One- and two-hop requests only talk to neighbours and must not change.

Core numbering is row major on the 4x4 mesh.  Background generation is off (``adaptive_max_memory = 0``).
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from compiler_trace import CompilerRequest, router_name
from execution_events import ListRecorder, RequestSubmitted
from parallel_core import run_parallel_experiment

CONFIG = Path(__file__).resolve().parents[1] / "config" / "final_config" / "grid_4x4_ace_3.json"


def run_one(source: int, destination: int, seed: int = 0):
    """Run a single end-to-end request and return (completed, latency_ms, submissions)."""
    layered = [[(0, router_name(source, 4), router_name(destination, 4), 1, 0.01, 1)]]
    plan = [CompilerRequest(0, 0, 0, 0, source, destination)]
    recorder = ListRecorder()
    with tempfile.TemporaryDirectory(prefix="ace-multihop-") as tmp:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["templates"]["adaptive_protocol"]["adaptive_max_memory"] = 0
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_parallel_experiment(
                str(path), False, False, layered, 5.3, 50, "multihop", seed=seed, compiler_spec=None,
                total_memories_per_core=4, simulation_stop_time_s=1.0, recorder=recorder,
                scheduler="per-qubit", request_plan=plan, scheduler_options={"admission": "event"})
    stats = result["stats"]
    submissions = sum(1 for e in recorder.events if isinstance(e, RequestSubmitted))
    return stats["completed_requests"], stats["individual_latencies"].get(0), submissions


class MultiHopForwardingTests(unittest.TestCase):
    def test_requests_over_three_or_more_hops_complete_on_the_first_submission(self):
        for source, destination in [(13, 11), (13, 7), (13, 3), (0, 15)]:      # 3, 4, 5 and 6 hops
            with self.subTest(source=source, destination=destination):
                completed, latency_ms, submissions = run_one(source, destination)
                self.assertEqual(completed, 1)
                self.assertEqual(submissions, 1)
                self.assertLess(latency_ms, 50)

    def test_one_and_two_hop_requests_are_unchanged(self):
        """Values measured before the change (2026-10-25, seed 0)."""
        self.assertEqual(run_one(13, 14)[:2], (1, 0.80002526))
        self.assertEqual(run_one(13, 15)[:2], (1, 1.50003851))


if __name__ == "__main__":
    unittest.main()
