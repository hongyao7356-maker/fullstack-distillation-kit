import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_check import run
from evidence_engine import valid_evidence


class RunnerV13(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/".fullstack").mkdir()
        (self.root/"package.json").write_text(json.dumps({"scripts": {"build": "node build.js"}}))
        (self.root/"build.js").write_text(
            "const fs=require('fs');if(process.env.REVIEW_BUILD_MODE!=='pass')process.exit(1);"
            "fs.mkdirSync('dist');fs.writeFileSync('dist/app.js','compiled');")
        self.cmd = ["npm", "run", "build"]
        (self.root/".fullstack/checks.json").write_text(json.dumps({"P6": [{
            "check_id": "build", "kind": "build", "command": self.cmd,
            "environment": {"keys": ["REVIEW_BUILD_MODE"]},
            "outputs": [{"path": "dist", "type": "directory", "max_bytes": 1024, "max_files": 10}]
        }]}))

    def test_environment_change_invalidates_current_evidence(self):
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            rec, _ = run(self.root, "P6", "build", self.cmd, check_id="build")
            self.assertEqual(0, rec["exit_code"])
            self.assertTrue(valid_evidence(self.root, "P6", "build"))
        with patch.dict(os.environ, REVIEW_BUILD_MODE="fail"):
            self.assertFalse(valid_evidence(self.root, "P6", "build"))
            rec, _ = run(self.root, "P6", "build", self.cmd, check_id="build")
            self.assertEqual(1, rec["exit_code"])

    def test_real_build_preserved_and_tampering_invalidates(self):
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"):
            rec, _ = run(self.root, "P6", "build", self.cmd, check_id="build")
            self.assertEqual(0, rec["exit_code"])
            outputs = list((self.root/".fullstack/artifacts").rglob("app.js"))
            self.assertEqual(1, len(outputs))
            self.assertEqual("compiled", outputs[0].read_text())
            self.assertTrue(valid_evidence(self.root, "P6", "build"))
            outputs[0].write_text("tampered")
            self.assertFalse(valid_evidence(self.root, "P6", "build"))

    def test_concurrent_source_change_cannot_validate_success(self):
        import concurrent.futures
        import time
        signal = self.root.parent / (self.root.name + "-signal")
        self.addCleanup(lambda: signal.unlink(missing_ok=True))
        (self.root/"build.js").write_text(
            "const fs=require('fs');fs.writeFileSync(" + json.dumps(str(signal)) + ",'ready');"
            "setTimeout(()=>{fs.mkdirSync('dist');fs.writeFileSync('dist/app.js','built');},500);")
        with patch.dict(os.environ, REVIEW_BUILD_MODE="pass"), concurrent.futures.ThreadPoolExecutor() as pool:
            task = pool.submit(run, self.root, "P6", "build", self.cmd, check_id="build")
            deadline = time.monotonic() + 30
            while not signal.exists() and not task.done() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(signal.exists(), "build did not start")
            (self.root/"changed-config.json").write_text('{"changed":true}')
            task.result(timeout=30)
            self.assertFalse(valid_evidence(self.root, "P6", "build"))
