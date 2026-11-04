import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
KIT=Path(__file__).resolve().parents[1]

class CardInputIntegration(unittest.TestCase):
    def test_invalid_inputs_have_located_errors_and_exit_two(self):
        original=json.loads((KIT/'cards/01_t3_typesafety.json').read_text(encoding='utf-8'))
        bad_type=dict(original,source_id=[])
        bad_enum=dict(original,status='INVALID')
        bad_provenance=dict(original,provenance={'observed_at':[], 'revision':{}, 'locator':None})
        inputs=['[]','null','{}','{bad',json.dumps(bad_type),json.dumps(bad_enum),json.dumps(bad_provenance)]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'invalid.json'
            for data in inputs:
                with self.subTest(data=data[:40]):
                    path.write_text(data,encoding='utf-8')
                    r=subprocess.run([sys.executable,str(KIT/'scripts/validate_cards.py'),'--cards',tmp],capture_output=True,text=True)
                    self.assertEqual(2,r.returncode,r.stdout+r.stderr)
                    self.assertNotIn('Traceback',r.stderr)
                    self.assertIn('invalid.json',r.stdout)
                    self.assertIn('ERROR',r.stdout)
