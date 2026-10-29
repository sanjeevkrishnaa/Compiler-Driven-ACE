import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import mechanism as m                                                          # noqa: E402


class VariantTests(unittest.TestCase):
    def test_a_cutoff_ratio_written_by_the_tool_reaches_every_memory(self):
        from ace.topology.router_net_topo_adaptive import RouterNetTopoAdaptive
        from sequence.topology.router_net_topo import RouterNetTopo
        with tempfile.TemporaryDirectory() as tmp:
            path = m.variant_config(Path(tmp), {"cutoff_ratio": 0.02})
            topo = RouterNetTopoAdaptive(str(path))
        for router in topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
            for memory in router.get_components_by_type("MemoryArray")[0]:
                self.assertAlmostEqual(memory.cutoff_ratio * memory.coherence_time, 0.02)

    def test_the_default_leaves_the_cutoff_at_the_coherence_time(self):
        from ace.topology.router_net_topo_adaptive import RouterNetTopoAdaptive
        from sequence.topology.router_net_topo import RouterNetTopo
        topo = RouterNetTopoAdaptive(str(m.DEFAULT_CONFIG))
        memory = topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER)[0].get_components_by_type("MemoryArray")[0][0]
        self.assertEqual(memory.cutoff_ratio, 1)

    def test_a_case_with_no_discard_reports_no_cutoff_reset(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(m.ARCHIVE) as z:
            trace = Path(z.extract(f"{m.PREFIX}/ghz/seed_42/requests.txt", tmp))
            row = m.run_case(trace, "ghz", "default", {}, 1000, 4, "per-qubit")
        self.assertEqual((row["memory_expiry_resets"], row["released_reservation_expired"], row["violations"]), (0, 0, 0))
        self.assertEqual(row["completed"], row["requested"])


if __name__ == "__main__":
    unittest.main()
