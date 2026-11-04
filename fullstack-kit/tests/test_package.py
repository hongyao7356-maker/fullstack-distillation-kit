import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

KIT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(KIT/"scripts"))
from check_gate import check_gate,evidence_ok,good_doc
from run_check import allowed_command,run
from init_project import initialize
from validate_cards import validate_all,validate_card
from verify_pack import verify

class PackTests(unittest.TestCase):
    def test_pack_structure(self):
        self.assertEqual([],verify(KIT))

    def test_source_cards(self):
        n,errors=validate_all(KIT,KIT/"cards")
        self.assertGreaterEqual(n,2)
        self.assertEqual([],errors)

    def test_bad_card_rejected(self):
        self.assertTrue(validate_card({"id":"x"},{"some-source"}))

    def test_init_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            first=initialize(root,"generic")
            self.assertGreaterEqual(len(first),1)
            profile=root/".fullstack"/"profile.json"
            original=profile.read_text(encoding="utf-8")
            self.assertEqual([],initialize(root,"digital-employee"))
            self.assertEqual(original,profile.read_text(encoding="utf-8"))

    def test_gate_blocks_missing_docs(self):
        with tempfile.TemporaryDirectory() as folder:
            policy=json.loads((KIT/"templates"/"phase_policy.json").read_text(encoding="utf-8"))
            issues=check_gate(Path(folder),"P0",policy)
            self.assertEqual(2,len(issues))

    def test_gate_accepts_real_docs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            initialize(root,"generic")
            docs=root/".fullstack"/"docs"
            for filename in ("00_requirements.md","00_acceptance.md"):
                (docs/filename).write_text("# Real project evidence\n"+"Substantive text about roles, boundaries and test scenarios. "*5,encoding="utf-8")
            policy=json.loads((KIT/"templates"/"phase_policy.json").read_text(encoding="utf-8"))
            self.assertEqual([],check_gate(root,"P0",policy))

    def test_qa_allowlist(self):
        self.assertTrue(allowed_command(["py","-3","-m","unittest","discover"]))
        self.assertTrue(allowed_command(["npm","run","build"]))
        for cmd in (["powershell","-c","echo hi"],["python","-c","print(1)"],["npm","run","deploy"],["git","reset","--hard"],["node","foo.js"]):
            self.assertFalse(allowed_command(list(cmd)))

    def test_run_records_and_tamper_detects(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            testdir=root/"testcases"
            testdir.mkdir()
            (testdir/"test_smoke.py").write_text("import unittest\nclass Smoke(unittest.TestCase):\n    def test_true(self): self.assertTrue(True)\n",encoding="utf-8")
            receipt,p=run(root,"P4","test",["python","-m","unittest","discover","-s","testcases"],timeout=20)
            self.assertEqual(0,receipt["exit_code"])
            self.assertTrue(evidence_ok(root,"P4","test"))
            log=root/receipt["log"]
            log.write_text(log.read_text(encoding="utf-8")+"TAMPERED",encoding="utf-8")
            self.assertFalse(evidence_ok(root,"P4","test"))

    def test_prevent_traversal_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            ev=root/".fullstack"/"evidence"
            ev.mkdir(parents=True)
            record={"phase":"P4","kind":"test","exit_code":0,"timed_out":False,"log":"../../file.txt","log_sha256":"0"*64}
            (ev/"fake.json").write_text(json.dumps(record),encoding="utf-8")
            self.assertFalse(evidence_ok(root,"P4","test"))

    def test_document_placeholder_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"test.md"
            p.write_text("TO_BE_CONFIRMED"+"x"*200,encoding="utf-8")
            self.assertFalse(good_doc(p))

if __name__=="__main__":unittest.main()
