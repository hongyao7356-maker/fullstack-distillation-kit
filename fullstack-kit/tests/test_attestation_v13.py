import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'scripts'))
import gate_policy
from run_check import run
from workflow import policy, requirements


class LegacyAttestationTests(unittest.TestCase):
    def test_old_signature_never_authorizes_production(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / 'project'
            meta = root / '.fullstack'
            (meta / 'docs').mkdir(parents=True)
            (meta / 'origin').mkdir()
            for name in policy()['P6']['docs']:
                (meta / 'docs' / name).write_text('Synthetic phase document. ' * 12)
            (meta / 'profile.json').write_text(json.dumps(dict(
                evidence_origin='real_project', production_deploy_authorized=True)))
            cmd = ['npm', 'run', 'build']
            (meta / 'checks.json').write_text(json.dumps({'P6': [dict(
                check_id='build', kind='build', command=cmd)]}))
            (root / 'package.json').write_text(json.dumps({'scripts': {'build': 'node qa.js'}}))
            (root / 'qa.js').write_text("console.log('fixture');")
            receipt, _ = run(root, 'P6', 'build', cmd, check_id='build', scope='production_release')
            self.assertEqual(0, receipt['exit_code'])
            key = base / 'legacy'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
            signers = base / 'allowed_signers'
            signers.write_text('reviewer ' + key.with_suffix('.pub').read_text())
            payload = base / 'payload'
            payload.write_bytes(gate_policy.attestation_payload(root, 'P6'))
            subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n',
                            'fullstack-origin-v1', str(payload)], check=True, capture_output=True)
            Path(str(payload) + '.sig').replace(meta / 'origin/P6.sig')
            with patch.object(gate_policy, 'SIGNERS', signers):
                self.assertTrue(requirements(root, 'P6'), 'legacy signature authorized production')
