import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class DeliveryIntegration(unittest.TestCase):
    def test_repeat_verify_is_read_only(self):
        protected=list((ROOT/'fullstack-kit').rglob('*.py'))
        protected += [p for p in [ROOT/'.fullstack/profile.json',ROOT/'outputs/首次执行与验收报告.md'] if p.exists()]
        before={p:p.read_bytes() for p in protected}
        for _ in range(2):
            result=subprocess.run([sys.executable,str(ROOT/'work/verify_delivery.py'),'verify','--project',str(ROOT)],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertEqual(before,{p:p.read_bytes() for p in protected})

    def test_export_conflict_and_portable_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'portable kit'
            entry=ROOT/'work/verify_delivery.py'
            args=[sys.executable,str(entry),'export','--project',str(ROOT),'--destination',str(target)]
            first=subprocess.run(args,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(0,first.returncode,first.stdout+first.stderr)
            second=subprocess.run(args,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(2,second.returncode)
            result=subprocess.run([sys.executable,str(target/'fullstack-kit/scripts/delivery.py'),'verify','--project',str(target)],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
