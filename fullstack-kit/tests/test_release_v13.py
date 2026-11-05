import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts")]
from run_check import run
from workflow import policy, requirements
from fixture_platform_v13 import platform
import attestation_v13


class ReleaseV13(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "project"
        self.meta = self.root / ".fullstack"
        (self.meta / "docs").mkdir(parents=True)
        for name in policy()["P6"]["docs"]:
            (self.meta/"docs"/name).write_text("Synthetic integration fixture. " * 12)
        (self.meta/"profile.json").write_text(json.dumps({
            "evidence_origin": "real_project", "production_deploy_authorized": True}))
        (self.root/"package.json").write_text(json.dumps({"scripts": {"build": "node build.js"}}))
        (self.root/"build.js").write_text(
            "if(process.env.REVIEW_BUILD_MODE!=='pass')process.exit(1);"
            "const fs=require('fs');fs.mkdirSync('dist');fs.writeFileSync('dist/app.js','built');")
        self.cmd = ["npm", "run", "build"]
        self.sign, self.trust = platform(self)

    def configure(self, mode="CURRENT_ENV_CHECK"):
        (self.meta/"checks.json").write_text(json.dumps({"P6": [{
            "check_id": "build", "kind": "build", "command": self.cmd,
            "candidate_id": "release-1", "runner_id": "fixture-runner",
            "environment": {"keys": ["REVIEW_BUILD_MODE"], "mode": mode},
            "outputs": [{"path": "dist", "type": "directory", "max_bytes": 1024, "max_files": 10}]
        }]}))

    def build(self):
        return run(self.root, "P6", "build", self.cmd, check_id="build",
                   scope="production_release")[0]

    def test_current_environment_signed_pass_then_drift_and_failure(self):
        self.configure()
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            self.assertEqual(0, self.build()["exit_code"])
            self.sign(self.root, "P6")
            self.assertEqual([], requirements(self.root, "P6"))
        with patch.dict(os.environ, REVIEW_BUILD_MODE="fail"):
            self.assertTrue(requirements(self.root, "P6"))
            self.assertEqual(1, self.build()["exit_code"])
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            self.assertTrue(requirements(self.root, "P6"), "latest failure was hidden by old success")

    def test_historical_artifact_survives_environment_drift_but_not_mutation(self):
        self.configure("ATTESTED_BUILD_ARTIFACT")
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            receipt = self.build()
            self.assertEqual(0, receipt["exit_code"])
            self.sign(self.root, "P6")
        with patch.dict(os.environ, REVIEW_BUILD_MODE="fail"):
            self.assertEqual([], requirements(self.root, "P6"))
            artifact = self.root / receipt["artifact"]["location"] / "files/dist/app.js"
            artifact.write_text("altered")
            self.assertTrue(requirements(self.root, "P6"))
            artifact.unlink()
            self.assertTrue(requirements(self.root, "P6"))

    def test_revocation_stage_authorization_and_expiry(self):
        self.configure("ATTESTED_BUILD_ARTIFACT")
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            self.assertEqual(0, self.build()["exit_code"])
            original = self.sign(self.root, "P6")
        self.assertEqual([], requirements(self.root, "P6"))
        trusted = json.loads(self.trust.read_text())
        for field, value in (("revoked", True), ("phases", ["P4"]),
                             ("scopes", ["project_acceptance"]),
                             ("runner_ids", ["other-platform"]),
                             ("projects", ["other-project"]),
                             ("not_after", "2000-01-01T00:00:00Z")):
            changed = json.loads(json.dumps(trusted))
            changed["signers"][0][field] = value
            self.trust.write_text(json.dumps(changed))
            with self.subTest(field=field):
                self.assertTrue(requirements(self.root, "P6"))
        self.trust.write_text(json.dumps(trusted))
        path = self.meta/"origin/P6.attestation.json"
        changed = dict(original, schema_version="1.2")
        path.write_text(json.dumps(changed))
        self.assertTrue(requirements(self.root, "P6"))
        path.write_text(json.dumps(original))
        self.assertEqual([], requirements(self.root, "P6"))
        with patch.object(attestation_v13, "utcnow",
                          return_value=attestation_v13.timestamp(original["expires_utc"])):
            self.assertTrue(requirements(self.root, "P6"))

    def test_external_proof_required_for_mutable_local_execution(self):
        self.configure()
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            self.assertEqual(0, self.build()["exit_code"])
            self.assertTrue(requirements(self.root, "P6"))
            (self.meta/"origin").mkdir(exist_ok=True)
            (self.meta/"origin/P6.attestation.json").write_text('{"schema_version":"1.3"}')
            self.assertTrue(requirements(self.root, "P6"))

    def test_delivery_entrypoint_validates_actual_files(self):
        import contextlib
        import io
        import shutil
        from verify_release import main
        self.configure("ATTESTED_BUILD_ARTIFACT")
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            receipt = self.build()
            self.assertEqual(0, receipt["exit_code"])
            self.sign(self.root, "P6")
        with tempfile.TemporaryDirectory() as folder:
            delivery = Path(folder)
            files = self.root/receipt["artifact"]["location"]/"files"
            shutil.copytree(files, delivery/receipt["run_id"])
            args = ["verify_release.py", "verify", "--project", str(self.root),
                    "--phase", "P6", "--delivery-root", str(delivery)]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main())
                (delivery/receipt["run_id"]/"dist/app.js").write_text("wrong artifact")
                self.assertEqual(2, main())
