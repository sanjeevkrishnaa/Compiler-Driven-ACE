import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from tools import run_final_matrix as runner


class FinalMatrixTests(unittest.TestCase):
    def test_capacity_matches_finite_memory_budget(self):
        for case in runner.CASES:
            expected = 8 if case.endswith('-8') else 4
            self.assertEqual(runner.routing_capacity(case), expected)
        out = Path('output')
        self.assertEqual(runner.trace_path(out,'qaoa','history','CD-8'),
                         out/'routed-c8/traces/qaoa/seed_42/history/requests.txt')
        self.assertEqual(runner.trace_path(out,'qaoa','history','CD-4'),
                         out/'routed/traces/qaoa/seed_42/history/requests.txt')

    def test_prepare_passes_capacity_and_checks_cached_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            mapping=out/'inputs/ghz/seed_42'
            mapping.mkdir(parents=True)
            (mapping/'mapping_summary.json').write_text('{}')
            router=Mock()
            with patch.object(runner.matrix,'OUT',out), patch.dict('sys.modules',heavy_routing=router):
                runner.matrix.prepare('ghz',capacity=8)
                router.build.assert_called_once_with(out/'routed-c8',out/'inputs',
                                                     ('xy','history'),('ghz',),capacity=8)
                marker=out/'routed-c8/routing_specification.json'
                self.assertEqual(json.loads(marker.read_text())['capacity'],8)
                marker.write_text('{"capacity":4}')
                with self.assertRaisesRegex(ValueError,'Routing specification changed'):
                    runner.matrix.prepare('ghz',capacity=8)

    def test_eight_slot_selection_is_240_runs(self):
        args=runner.parser().parse_args(['--cases','ODG-8','CGP-8','ACGP-8','CD-8',
                                         '--seeds','60,61,62','--jobs','4'])
        self.assertEqual(len(args.workloads)*len(args.routes)*len(args.cases)*len(args.seeds.split(',')),240)
        self.assertEqual({runner.routing_capacity(c) for c in args.cases},{8})

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
