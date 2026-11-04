import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_check import run

class ExecutorIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='中文 space ')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    @unittest.skipUnless(shutil.which('node') and shutil.which('npm'), 'Node/npm unavailable')
    def test_real_npm_test_build_and_cmd(self):
        (self.root/'check.js').write_text('console.log("REAL_NPM_OK")',encoding="utf-8")
        (self.root/'package.json').write_text(json.dumps({'private':True,'scripts':{'test':'node check.js','build':'node check.js'}}))
        for executable,script in [('npm','test'),('npm','build')]+([('npm.cmd','test')] if os.name=='nt' else []):
            with self.subTest(executable=executable,script=script):
                try: receipt,_=run(self.root,'P4','test',[executable,'run',script])
                except ValueError as e: self.fail(str(e))
                self.assertEqual(0,receipt['exit_code'])
                self.assertIn('REAL_NPM_OK',(self.root/receipt['log']).read_text())

    @unittest.skipUnless(shutil.which('node'), 'Node unavailable')
    def test_node_absolute_local_script(self):
        script=self.root/'hello world.js';script.write_text('console.log("NODE_OK")')
        try: receipt,_=run(self.root,'P4','test',['node',str(script)])
        except ValueError as e: self.fail(str(e))
        self.assertEqual(0,receipt['exit_code'])

    def test_timeout_kills_descendant(self):
        tests=self.root/'tests';tests.mkdir()
        heartbeat=self.root/'.fullstack/checks/heartbeat'
        child='import time; from pathlib import Path; p=Path('+repr(str(heartbeat))+'); '+"\nfor _ in range(80):\n p.write_text(str(time.time())); time.sleep(.05)"
        code='import unittest,subprocess,sys,time\nclass T(unittest.TestCase):\n def test_tree(self):\n  subprocess.Popen([sys.executable,"-c",'+repr(child)+'])\n  time.sleep(10)\n'
        (tests/'test_tree.py').write_text(code,encoding="utf-8")
        started=time.monotonic()
        receipt,_=run(self.root,'P4','test',[sys.executable,'-m','unittest','discover','-s','tests'],timeout=2)
        self.assertLess(time.monotonic()-started,3.5,'runner waited for descendant natural exit instead of terminating it')
        self.assertEqual(124,receipt['exit_code'])
        self.assertTrue(heartbeat.exists())
        first=heartbeat.read_text();time.sleep(.3)
        self.assertEqual(first,heartbeat.read_text(),'descendant continues writing after timeout')

if __name__=='__main__':unittest.main()
