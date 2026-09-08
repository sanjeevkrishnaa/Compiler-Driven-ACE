from pathlib import Path
import tempfile
import unittest

from compiler_trace import (
    mesh_dimensions,
    parse_compiler_trace,
    plan_preparations,
    to_ace_layers,
    validate_neighbor_requests,
)


TRACE = """// Number of cores
4
// Number of qubit slots per core
2
// Number of qubits
4
// Initial placement: (qubit, core)
(0, 0)
(1, 1)
(2, 2)
(3, 3)
// Inter-core communication requests: (qubit, src, dst)
// Layer 0
// Layer 1
(0, 0, 1)
// Layer 2
(0, 1, 3)
"""


class CompilerTraceTests(unittest.TestCase):
    def parse(self, text=TRACE):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.txt"
            path.write_text(text, encoding="utf-8")
            return parse_compiler_trace(path)

    def test_parse_preserves_empty_layers_and_validates_placement(self):
        trace = self.parse()
        self.assertEqual((trace.core_count, trace.layer_count), (4, 3))
        self.assertEqual(len(trace.requests), 2)
        self.assertEqual(trace.requests[1].source_core, 1)

    def test_trace_converts_to_row_major_ace_router_names(self):
        trace = self.parse()
        rows, columns = mesh_dimensions(trace, "2x2")
        validate_neighbor_requests(trace, rows, columns)
        layers = to_ace_layers(trace, columns=columns)
        self.assertEqual(layers[0], [])
        self.assertEqual(layers[1][0][1:3], ("router_0_0", "router_0_1"))
        self.assertEqual(layers[2][0][1:3], ("router_0_1", "router_1_1"))

    def test_fixed_and_dynamic_plans_obey_capacity(self):
        trace = self.parse()
        fixed, fixed_blocked, fixed_peak = plan_preparations(
            trace, strategy="fixed", compiler_memories_per_core=1,
            generation_capacity_per_core=1, coherence_time_layers=3,
            delta_layers=1,
        )
        dynamic, dynamic_blocked, dynamic_peak = plan_preparations(
            trace, strategy="dynamic", compiler_memories_per_core=1,
            generation_capacity_per_core=1, coherence_time_layers=3,
            dynamic_lookahead_layers=2,
        )
        self.assertEqual([item.generation_layer for item in fixed], [0, 1])
        self.assertEqual([item.generation_layer for item in dynamic], [0, 1])
        self.assertEqual((fixed_blocked, dynamic_blocked), (0, 0))
        self.assertEqual((fixed_peak, dynamic_peak), (1, 1))

    def test_bad_evolving_placement_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not 0"):
            self.parse(TRACE.replace("(0, 1, 3)", "(0, 0, 3)"))

    def test_dynamic_minimum_lead_is_enforced(self):
        trace = self.parse()
        schedule, blocked, _ = plan_preparations(
            trace, strategy="dynamic", compiler_memories_per_core=1,
            generation_capacity_per_core=1, coherence_time_layers=4,
            dynamic_lookahead_layers=3, dynamic_min_lead_layers=2,
        )
        self.assertEqual(
            [(item.request_id, item.generation_layer) for item in schedule],
            [(1, 0)],
        )
        self.assertEqual(blocked, 1)

    def test_dynamic_minimum_lead_must_fit_lookahead(self):
        with self.assertRaisesRegex(ValueError, "minimum lead"):
            plan_preparations(
                self.parse(), strategy="dynamic", compiler_memories_per_core=1,
                generation_capacity_per_core=1, coherence_time_layers=4,
                dynamic_lookahead_layers=2, dynamic_min_lead_layers=3,
            )


if __name__ == "__main__":
    unittest.main()
