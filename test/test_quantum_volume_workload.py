import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"mapper"))
from tools.congestion_study.run_study import load_circuit


class QuantumVolumeWorkloadTests(unittest.TestCase):
    def test_width_depth_seed_and_normalization_are_recorded(self):
        args=SimpleNamespace(circuit_seed=42,optimization_level=0)
        qc,ir,source=load_circuit("quantum_volume",None,4,args,{"quantum_volume":{"depth":2}})
        self.assertEqual(qc.num_qubits,4)
        self.assertEqual(source["factory_options"],{"depth":2,"seed":42})
        self.assertEqual(source["kind"],"qiskit-circuit-library")
        self.assertTrue(set(qc.count_ops()).issubset({"rz","sx","x","cx"}))
        self.assertEqual(ir.n_qubits,4)
