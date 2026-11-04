import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_check import run

class SecurityIntegration(unittest.TestCase):
    def test_secret_argument_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); marker='SENTINEL_'+uuid.uuid4().hex
            receipt,_=run(root,'P4','test',[sys.executable,'-m','unittest','--api-key='+marker])
            self.assertNotEqual(0,receipt['exit_code'])
            for path in (root/'.fullstack').rglob('*'):
                if path.is_file(): self.assertNotIn(marker.encode(),path.read_bytes(),str(path))

    def test_known_environment_secret_stdout_stderr_redacted(self):
        marker='SENTINEL_'+uuid.uuid4().hex
        name='FULLSTACK_AUDIT_API_KEY'
        original=os.environ.get(name);os.environ[name]=marker
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'tests').mkdir()
                (root/'tests/test_output.py').write_text('import unittest,os,sys\nclass T(unittest.TestCase):\n def test_output(self):\n  print(os.environ["'+name+'"]);print(os.environ["'+name+'"],file=sys.stderr)\n')
                receipt,_=run(root,'P4','test',[sys.executable,'-m','unittest','discover','-s','tests'])
                self.assertEqual(0,receipt['exit_code'])
                for path in (root/'.fullstack').rglob('*'):
                    if path.is_file():self.assertNotIn(marker.encode(),path.read_bytes(),str(path))
        finally:
            if original is None:os.environ.pop(name,None)
            else:os.environ[name]=original
