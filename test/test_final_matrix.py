import csv
import json
from pathlib import Path
import tempfile
import unittest
from tools import run_final_matrix as runner


class FinalMatrixTests(unittest.TestCase):
    def fixture(self, folder):
        row=dict(strategy='dynamic',seed=60,requests=10,completed_requests=10,
                 average_request_latency_ms=1,end_to_end_latency_ms=10,
                 average_delivered_epr_fidelity=.94,generated_compiler_pairs=10,
                 utilized_compiler_pairs=6,expired_compiler_pairs=1,
                 cancelled_compiler_pairs=2,remaining_compiler_pairs=1)
        with (folder/'summary.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
        runner.save(folder/'audit_dynamic_60.json',dict(violations=[],completed_requests=10,total_requests=10))
        runner.save(folder/'pair_lifecycle.json',dict(generated=10,statuses={},ready_requests=5,observed_requests=10))

    def test_cancellation_is_waste(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.fixture(folder)
            r=runner.result(folder,'ghz','xy','CD-8',60,None)
            self.assertEqual((r['wastage'],r['coverage'],r['cancelled_pairs']),(.4,.5,2))

    def test_reject_incomplete_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.fixture(folder)
            runner.save(folder/'audit_dynamic_60.json',dict(violations=[],completed_requests=9,total_requests=10))
            with self.assertRaisesRegex(ValueError,'audit'):runner.result(folder,'ghz','xy','CD-8',60,None)

    def test_reject_unaccounted_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.fixture(folder)
            text=(folder/'summary.csv').read_text().replace('1,2,1','1,2,0')
            (folder/'summary.csv').write_text(text)
            with self.assertRaisesRegex(ValueError,'conservation'):runner.result(folder,'ghz','xy','CD-8',60,None)

    def test_no_pregeneration_is_not_zero_waste_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.fixture(folder)
            runner.save(folder/'pair_lifecycle.json',dict(generated=0,statuses={},ready_requests=0,observed_requests=10))
            r=runner.result(folder,'ghz','xy','ODG-8',60,None)
            self.assertEqual(r['wastage'],'')
            self.assertEqual(r['coverage'],0)


if __name__=='__main__':unittest.main()
