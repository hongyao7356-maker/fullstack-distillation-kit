import json
from pathlib import Path
import sys
import tempfile
import unittest
KIT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(KIT/'scripts'))
from run_check import run
from evidence_engine import valid_evidence
from init_project import initialize
from workflow import requirements
from security import redact

class IndependentReviewRegression(unittest.TestCase):
    def test_work_directory_is_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'work/tests').mkdir(parents=True)
            path=root/'work/tests/test_case.py'
            path.write_text('import unittest\nclass T(unittest.TestCase):\n def test_it(self): self.assertTrue(True)\n')
            run(root,'P4','test',[sys.executable,'-m','unittest','discover','-s','work/tests'])
            self.assertTrue(valid_evidence(root,'P4','test'))
            path.write_text('import unittest\nclass T(unittest.TestCase):\n def test_it(self): self.assertTrue(False)\n')
            self.assertFalse(valid_evidence(root,'P4','test'))

    def test_required_command_cannot_be_substituted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);initialize(root)
            (root/'.fullstack/profile.json').write_text(json.dumps({'goal':'fixture','users':['test'],'owner_decisions_pending':[]}))
            for name in ['00_requirements.md','00_acceptance.md']:
                (root/'.fullstack/docs'/name).write_text('ISOLATED REVIEW TEST. '*20)
            for name,ok in [('required',False),('smoke',True)]:
                (root/name).mkdir()
                (root/name/'test_it.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_it(self): self.assertTrue('+str(ok)+')\n')
            required=[sys.executable,'-m','unittest','discover','-s','required']
            (root/'.fullstack/checks.json').write_text(json.dumps({'P0':[{'check_id':'test','kind':'test','command':required}]}))
            substitute=[sys.executable,'-m','unittest','discover','-s','smoke']
            receipt,_=run(root,'P0','test',substitute,check_id='test',scope='project_acceptance')
            self.assertEqual(0,receipt['exit_code'])
            self.assertTrue(requirements(root,'P0'),'substituted command must not satisfy configured check')

    def test_private_key_output_redacted(self):
        self.assertNotIn('FAKE_REVIEW_VALUE',redact('private_key=FAKE_REVIEW_VALUE'))

    def test_quoted_and_bearer_secret_output_redacted(self):
        for text in ['private_key="FAKE VALUE WITH SPACES"',"private-key='FAKE VALUE WITH SPACES'",'Authorization: Bearer FAKE_TOKEN_VALUE']:
            with self.subTest(text=text):
                self.assertNotIn('VALUE',redact(text))

    def test_sanitized_json_remains_parseable(self):
        from security import sanitize
        obj={'message':'private_key="FAKE VALUE WITH SPACES"'}
        result=json.loads(json.dumps(sanitize(obj)))
        self.assertNotIn('VALUE',result['message'])

    def test_export_inside_source_rejected(self):
        from delivery import export
        # Reject before copying, even when the requested source child does not exist.
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import patch
            root=Path(tmp);(root/'fullstack-kit').mkdir()
            # Only package-shape validation is stubbed; path handling is the behavior under test.
            with patch('delivery.verify',return_value={'errors':[]}):
                with self.assertRaises(ValueError):export(root,root/'fullstack-kit/recursive-output')
