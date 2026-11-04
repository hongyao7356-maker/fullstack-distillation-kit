import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
KIT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(KIT/'scripts'))
from init_project import initialize
from run_check import run

class WorkflowE2E(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);initialize(self.root)

    def cli(self,*args):
        return subprocess.run([sys.executable,str(KIT/'scripts/workflow.py'),'--project',str(self.root),*args],capture_output=True,text=True,encoding='utf-8')

    def test_missing_phases_and_unapproved_transition(self):
        for phase in [f'P{i}' for i in range(8)]:
            with self.subTest(phase=phase):
                r=self.cli('advance','--phase',phase)
                self.assertEqual(2,r.returncode,r.stdout+r.stderr)
                self.assertIn('BLOCKED',r.stdout)

    def test_noninteractive_approval_denied(self):
        r=self.cli('approve','--phase','P0','--actor','tester')
        self.assertEqual(2,r.returncode)
        self.assertIn('interactive',r.stdout)

    def test_real_evidence_approval_and_source_invalidation(self):
        self.assertTrue((KIT/'scripts/workflow.py').is_file(),'workflow implementation missing')
        from workflow import approve,advance,status,context_hash
        from evidence_engine import snapshot
        profile={'project_name':'isolated test fixture','goal':'Exercise orchestration only','users':['fixture operator'],'owner_decisions_pending':[],'evidence_origin':'synthetic'}
        (self.root/'.fullstack/profile.json').write_text(json.dumps(profile))
        policy=json.loads((KIT/'templates/phase_policy.json').read_text(encoding='utf-8'))
        for filename in policy['P0']['docs']:
            (self.root/'.fullstack/docs'/filename).write_text('ISOLATED ORCHESTRATOR FIXTURE. '*10)
        config={'P0':[{'check_id':'requirements-test','kind':'test','command':[sys.executable,'-m','unittest','discover','-s','tests']}]}
        (self.root/'.fullstack/checks.json').write_text(json.dumps(config))
        (self.root/'tests').mkdir();(self.root/'tests/test_case.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_it(self): self.assertEqual(2,1+1)\n')
        cmd=[sys.executable,'-m','unittest','discover','-s','tests']
        run(self.root,'P0','test',cmd,check_id='requirements-test',scope='tool_selftest')
        with self.assertRaises(ValueError):approve(self.root,'P0','fixture',context_hash(self.root,'P0'),human_confirmed=True)
        run(self.root,'P0','test',cmd,check_id='requirements-test',scope='project_acceptance')
        with self.assertRaises(ValueError):advance(self.root,'P0')
        approve(self.root,'P0','fixture',context_hash(self.root,'P0'),human_confirmed=True)
        advance(self.root,'P0')
        self.assertEqual('complete',status(self.root)['P0'])
        with self.assertRaises(ValueError):advance(self.root,'P2')
        (self.root/'changed.py').write_text('changed=True')
        self.assertEqual('stale',status(self.root)['P0'])
        with self.assertRaises(ValueError):advance(self.root,'P1')

    def test_synthetic_never_qualifies_for_production(self):
        self.assertTrue((KIT/'scripts/workflow.py').is_file(),'workflow implementation missing')
        from workflow import approve,context_hash
        with self.assertRaises(ValueError):approve(self.root,'P6','fixture',context_hash(self.root,'P6'),human_confirmed=True,production_authorized=True)

    def test_sequential_p0_to_p5_then_production_blocked(self):
        from workflow import approve,advance,status,context_hash
        rules=json.loads((KIT/'templates/phase_policy.json').read_text(encoding='utf-8'))
        profile={'goal':'isolated workflow engine test','users':['fixture'],'owner_decisions_pending':[],'evidence_origin':'synthetic','production_deploy_authorized':False}
        (self.root/'.fullstack/profile.json').write_text(json.dumps(profile),encoding='utf-8')
        (self.root/'tests').mkdir();(self.root/'tests/test_it.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_it(self): self.assertEqual(2,1+1)\n',encoding='utf-8')
        cmd=[sys.executable,'-m','unittest','discover','-s','tests']
        config={}
        for phase in rules:
            config[phase]=[{'check_id':phase+'.'+kind,'kind':kind,'command':cmd} for kind in (rules[phase]['checks'] or ['test'])]
            for filename in rules[phase]['docs']:
                (self.root/'.fullstack/docs'/filename).write_text('SYNTHETIC ORCHESTRATION FIXTURE. NOT BUSINESS ACCEPTANCE. '*10,encoding='utf-8')
        (self.root/'.fullstack/checks.json').write_text(json.dumps(config),encoding='utf-8')
        for i in range(6):
            phase=f'P{i}'
            for item in config[phase]:run(self.root,phase,item['kind'],cmd,check_id=item['check_id'],scope='project_acceptance')
            approve(self.root,phase,'fixture actor',context_hash(self.root,phase),human_confirmed=True)
            advance(self.root,phase)
        self.assertEqual('complete',status(self.root)['P5'])
        for item in config['P6']:run(self.root,'P6',item['kind'],cmd,check_id=item['check_id'],scope='tool_selftest')
        with self.assertRaises(ValueError):approve(self.root,'P6','fixture actor',context_hash(self.root,'P6'),human_confirmed=True,production_authorized=True)
