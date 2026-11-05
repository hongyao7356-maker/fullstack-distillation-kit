import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
from check_gate import check_gate
from workflow import requirements, policy
from run_check import run


class PolicyGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "project"
        self.meta = self.root / ".fullstack"
        (self.meta / "docs").mkdir(parents=True)
        self.rules = policy()
        for phase in ("P4","P6"):
            for name in self.rules[phase]["docs"]:
                (self.meta / "docs" / name).write_text("Fixture document. " * 12)
        (self.meta / "profile.json").write_text(json.dumps(dict(evidence_origin="real_project", production_deploy_authorized=True)))
        (self.root / "package.json").write_text(json.dumps({"scripts": {k: "node qa.js" for k in ("test","lint","build")}}))
        (self.root / "qa.js").write_text("console.log('fixture');")
    
    def config(self,phase,*kinds):
        checks = [dict(check_id=phase+"."+k,kind=k,command=["npm","run",k]) for k in kinds]
        (self.meta / "checks.json").write_text(json.dumps({phase:checks}))

    def execute(self,phase,kind,scope,check_id=None,script=None):
        rec,_ = run(self.root,phase,kind,["npm","run",script or kind],check_id=check_id or phase+"."+kind,scope=scope)
        self.assertEqual(0,rec["exit_code"])

    def both(self,phase,issue):
        for result in (check_gate(self.root,phase,self.rules),requirements(self.root,phase)):
            self.assertTrue(any(issue in msg for msg in result),result)

    def test_missing_kind_and_mixed_scopes(self):
        for phase,kind,scope in (("P4","lint","project_acceptance"),("P6","build","production_release")):
            self.config(phase,"test")
            self.execute(phase,"test",scope)
            self.execute(phase,kind,"tool_selftest")
            self.both(phase,"MISSING_REQUIRED_CHECK_CONFIG")

    def test_current_identity_and_command_and_snapshot(self):
        from fixture_reviewer import fixture_reviewer
        sign=fixture_reviewer(self)
        (self.meta/"origin").mkdir()
        self.config("P4","lint","test")
        self.execute("P4","test","project_acceptance")
        self.execute("P4","lint","project_acceptance","different")
        self.both("P4","INVALID_CHECK_EVIDENCE")
        self.execute("P4","lint","project_acceptance",script="test")
        self.both("P4","INVALID_CHECK_EVIDENCE")
        self.execute("P4","lint","project_acceptance")
        self.both("P4","UNVERIFIED_EXECUTION_INPUTS")
        sign(self.root,"P4")
        self.assertEqual([],requirements(self.root,"P4"))
        (self.root/"qa.js").write_text("process.exit(1)")
        self.both("P4","INVALID_CHECK_EVIDENCE")

    def test_help_exit_zero_is_not_build_evidence(self):
        cmd = [sys.executable, "-m", "compileall", "--help"]
        (self.meta / "checks.json").write_text(json.dumps({
            "P6": [dict(check_id="P6.build", kind="build", command=cmd)]}))
        rec, _ = run(self.root, "P6", "build", cmd, scope="production_release")
        self.assertEqual(0, rec["exit_code"])
        self.both("P6", "INVALID_CHECK_CONFIG")

    def test_production_scope_needs_independent_signature(self):
        (self.meta/"origin").mkdir()
        self.config("P6","build")
        config=json.loads((self.meta/"checks.json").read_text())
        config["P6"][0].update(candidate_id="candidate",runner_id="test-platform",
            outputs=[dict(path="dist",type="directory",max_bytes=1024,max_files=10)])
        (self.meta/"checks.json").write_text(json.dumps(config))
        (self.root/"qa.js").write_text("const fs=require('fs'); fs.mkdirSync('dist'); fs.writeFileSync('dist/app.js','built');")
        self.execute("P6","build","production_release")
        self.both("P6","UNVERIFIED_PRODUCTION_ORIGIN")
        from fixture_platform_v13 import platform
        sign, _ = platform(self)
        sign(self.root, "P6")
        self.assertEqual([],requirements(self.root,"P6"))
        self.execute("P6","build","production_release")
        self.both("P6","UNVERIFIED_PRODUCTION_ORIGIN")
