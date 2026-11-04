import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_check import run
from check_gate import evidence_ok


class EvidenceRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'tests').mkdir()
        self.cmd = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests']

    def write_case(self, ok):
        (self.root / 'tests/test_case.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_it(self): self.assertTrue(' + str(ok) + ')\n')

    def test_pass_fail_pass_latest_only(self):
        self.write_case(True)
        run(self.root, 'P4', 'test', self.cmd)
        self.assertTrue(evidence_ok(self.root, 'P4', 'test'))
        self.write_case(False)
        receipt, _ = run(self.root, 'P4', 'test', self.cmd)
        self.assertEqual(1, receipt['exit_code'])
        self.assertFalse(evidence_ok(self.root, 'P4', 'test'))
        self.write_case(True)
        run(self.root, 'P4', 'test', self.cmd)
        self.assertTrue(evidence_ok(self.root, 'P4', 'test'))

    def test_source_change_invalidates(self):
        self.write_case(True)
        run(self.root, 'P4', 'test', self.cmd)
        (self.root / 'package.json').write_text('{"changed":true}')
        self.assertFalse(evidence_ok(self.root, 'P4', 'test'))

    def test_corrupt_latest_never_falls_back(self):
        self.write_case(True)
        run(self.root, 'P4', 'test', self.cmd)
        _, path = run(self.root, 'P4', 'test', self.cmd)
        path.write_text('{broken')
        self.assertFalse(evidence_ok(self.root, 'P4', 'test'))

    def test_legacy_receipt_rejected(self):
        self.write_case(True)
        receipt, path = run(self.root, 'P4', 'test', self.cmd)
        receipt['schema_version'] = 1
        path.write_text(json.dumps(receipt))
        self.assertFalse(evidence_ok(self.root, 'P4', 'test'))

    def test_source_changes_during_execution_invalidates(self):
        self.write_case(True)
        (self.root/'tests/test_mutation.py').write_text('import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_mutate(self): Path("new_source.py").write_text("changed=1")\n')
        receipt,_=run(self.root,'P4','test',self.cmd)
        self.assertEqual(0,receipt['exit_code'])
        self.assertFalse(receipt['source_unchanged'])
        self.assertFalse(evidence_ok(self.root,'P4','test'))

    def test_command_rejection_supersedes_previous_pass(self):
        self.write_case(True);run(self.root,'P4','test',self.cmd)
        receipt,_=run(self.root,'P4','test',['powershell','-c','echo blocked'])
        self.assertEqual(126,receipt['exit_code'])
        self.assertFalse(evidence_ok(self.root,'P4','test'))


if __name__ == '__main__': unittest.main()
