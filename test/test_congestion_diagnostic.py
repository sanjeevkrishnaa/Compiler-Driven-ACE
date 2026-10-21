import json
from pathlib import Path
import tempfile
import unittest

from congestion_diagnostic import Request, audit, load_traffic, xy_path


class CongestionDiagnosticTests(unittest.TestCase):
    def test_xy_path_is_horizontal_then_vertical(self):
        self.assertEqual(
            xy_path((0, 0), (2, 1)),
            [((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (2, 1))],
        )

    def test_endpoint_and_link_accounting_are_independent_and_exact(self):
        report = audit(
            "small", 2, 3, 1,
            [Request(0, (0, 0), (2, 0)), Request(0, (0, 0), (1, 0))],
            capacities=[1, 2],
        )
        self.assertEqual(report["workload"]["requests"], 2)
        self.assertEqual(report["endpoint_pressure"]["peak_demand"], 2)
        self.assertEqual(report["route_link_pressure"]["peak_link_demand"], 2)
        self.assertEqual(report["capacity_sweep"]["1"], {
            "overloaded_layers": 1,
            "overloaded_layer_percent_of_active": 100.0,
            "affected_requests": 2,
            "affected_request_percent": 100.0,
            "endpoint_demand_excess": 1,
        })
        self.assertEqual(report["capacity_sweep"]["2"]["overloaded_layers"], 0)

    def test_traffic_loader_preserves_trailing_empty_layers(self):
        payload = {
            "circuit_type": "test", "num_rows": 2, "num_cols": 2,
            "layers": [[[0, "router_0_0", "router_1_0"]], [], []],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "traffic.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            name, rows, columns, source_layers, requests = load_traffic(path)
        self.assertEqual((name, rows, columns, source_layers), ("test:traffic", 2, 2, 3))
        self.assertEqual(requests, [Request(0, (0, 0), (1, 0))])


if __name__ == "__main__":
    unittest.main()
