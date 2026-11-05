import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
from evidence_engine import valid_evidence
from run_check import run


class ExecutionInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def check(self, directory):
        return run(self.root, "P4", "test", [
            sys.executable, "-m", "unittest", "discover", "-s", directory])[0]

    def test_excluded_discovery_and_transitive_inputs(self):
        for folder in (".fullstack/local-tests", ".fullstack/checks/local-tests", "node_modules/nested", ".venv/config"):
            with self.subTest(folder=folder):
                directory = self.root / folder
                directory.mkdir(parents=True)
                test = directory / "test_rule.py"
                test.write_text("import unittest\nclass T(unittest.TestCase):\n def test_rule(self): self.assertTrue(True)\n")
                self.check(folder)
                test.write_text(test.read_text().replace("True)", "False)"))
                self.assertFalse(valid_evidence(self.root, "P4", "test"))

    def test_indirect_project_module_and_runtime_config(self):
        tests = self.root / "tests"
        tests.mkdir()
        helper = self.root / ".fullstack" / "helpers" / "decision.py"
        helper.parent.mkdir(parents=True)
        helper.write_text("allowed = True")
        (tests / "test_rule.py").write_text("import runpy, unittest\nclass T(unittest.TestCase):\n def test_rule(self): self.assertTrue(runpy.run_path('.fullstack/helpers/decision.py')['allowed'])\n")
        self.assertEqual(0, self.check("tests")["exit_code"])
        self.assertTrue(valid_evidence(self.root, "P4", "test"))
        helper.write_text("allowed = False")
        self.assertFalse(valid_evidence(self.root, "P4", "test"))
        self.assertEqual(1, self.check("tests")["exit_code"])

    def test_link_into_excluded_directory_fails_closed(self):
        target = self.root / "node_modules" / "suite"
        target.mkdir(parents=True)
        link = self.root / ".fullstack" / "linked"
        link.parent.mkdir()
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.check(".fullstack/linked")

    def test_npm_build_creates_dist_without_changing_project_inputs(self):
        (self.root / "package.json").write_text(json.dumps({"scripts": {"build": "node build.js"}}))
        (self.root / "build.js").write_text("const fs=require('fs');fs.mkdirSync('dist');fs.writeFileSync('dist/app.js','hello')")
        receipt, _ = run(self.root, "P6", "build", ["npm", "run", "build"])
        self.assertEqual(0, receipt["exit_code"])
        self.assertTrue(valid_evidence(self.root, "P6", "build"))
        self.assertFalse((self.root / "dist").exists())

    def test_build_must_preserve_preexisting_outputs(self):
        (self.root / "dist").mkdir()
        (self.root / "dist/app.js").write_text("input")
        (self.root / "package.json").write_text(json.dumps({"scripts": {"build": "node build.js"}}))
        (self.root / "build.js").write_text("require('fs').writeFileSync('dist/app.js','changed')")
        receipt, _ = run(self.root, "P6", "build", ["npm", "run", "build"])
        self.assertEqual(0, receipt["exit_code"])
        self.assertFalse(valid_evidence(self.root, "P6", "build"))
