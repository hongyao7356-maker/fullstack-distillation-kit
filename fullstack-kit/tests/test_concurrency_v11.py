from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
KIT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(KIT/'scripts'))
from evidence_engine import connect,db_path
from check_gate import evidence_ok
from run_check import run

class EvidenceConcurrencyIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'tests').mkdir()
        self.command=[sys.executable,'-m','unittest','discover','-s','tests']

    def source(self,delay):
        (self.root/'tests/test_slow.py').write_text('import unittest,time\nclass T(unittest.TestCase):\n def test_it(self): time.sleep('+str(delay)+')\n')

    def cli(self):
        return [sys.executable,str(KIT/'scripts/run_check.py'),'--project',str(self.root),'--phase','P4','--kind','test','--',*self.command]

    def test_concurrent_same_check_serialized_no_partial_receipts(self):
        self.source(.2)
        processes=[subprocess.Popen(self.cli(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT) for _ in range(3)]
        for p in processes:
            output,_=p.communicate(timeout=30);self.assertEqual(0,p.returncode,output)
        with closing(connect(self.root,True)) as db:
            rows=db.execute('SELECT seq,state,run_id FROM executions ORDER BY seq').fetchall()
        self.assertEqual([1,2,3],[r['seq'] for r in rows])
        self.assertEqual(3,len({r['run_id'] for r in rows}))
        self.assertTrue(all(r['state']=='complete' for r in rows))
        self.assertTrue(evidence_ok(self.root,'P4','test'))
        self.assertFalse(list((self.root/'.fullstack/evidence').glob('*.tmp')))

    def test_interrupted_execution_blocks_old_pass_and_recovers(self):
        self.source(0);run(self.root,'P4','test',self.command)
        self.source(3)
        p=subprocess.Popen(self.cli(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with closing(connect(self.root,True)) as db:
                    row=db.execute('SELECT seq,state FROM executions ORDER BY seq DESC LIMIT 1').fetchone()
                if row['seq']==2 and row['state']=='running':break
                time.sleep(.02)
            else:self.fail('execution did not reach persisted running state')
            p.kill();p.communicate(timeout=10)
            self.assertFalse(evidence_ok(self.root,'P4','test'))
            self.source(0);run(self.root,'P4','test',self.command)
            self.assertTrue(evidence_ok(self.root,'P4','test'))
        finally:
            if p.poll() is None:p.kill();p.communicate()

    def test_damaged_index_fails_closed(self):
        self.source(0);run(self.root,'P4','test',self.command)
        db_path(self.root).write_bytes(b'not a database')
        self.assertFalse(evidence_ok(self.root,'P4','test'))
