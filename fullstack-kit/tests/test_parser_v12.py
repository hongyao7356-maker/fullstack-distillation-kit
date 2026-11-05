import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


RUNNER = Path(__file__).resolve().parents[1] / "scripts/run_check.py"


class ParserSecurity(unittest.TestCase):
    def test_invalid_arguments_leave_no_trace(self):
        marker = "SENTINEL_" + uuid.uuid4().hex
        options = ["--phase", "P4", "--kind", "test"]
        for case, args in {
            "unknown option": options + ["--api-key=" + marker],
            "invalid phase": ["--phase", marker, "--kind", "test"],
            "invalid kind": ["--phase", "P4", "--kind", marker],
            "invalid timeout": options + ["--timeout", marker],
            "invalid identity": options + ["--check-id", marker + "!", "--", sys.executable, "-m", "unittest"],
            "missing separator": options + [sys.executable, "-m", "unittest", marker],
            "missing option": ["--phase", "P4"],
            "empty command": options + ["--"],
        }.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                result = subprocess.run([sys.executable, "-B", str(RUNNER), "--project", tmp, *args],
                                        capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(marker.encode() in result.stderr + result.stdout, "raw input echoed")
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_valid_command_redacts_and_writes_receipt(self):
        marker = "SENTINEL_" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_demo.py").write_text(
                'import os, unittest\nclass Demo(unittest.TestCase):\n'
                '    def test_print(self): print(os.environ["DEMO_API_KEY"])\n', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--project", tmp, "--phase", "P4",
                 "--kind", "test", "--", sys.executable, "-m", "unittest", "discover"],
                env={**os.environ, "DEMO_API_KEY": marker}, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(marker.encode() in result.stderr + result.stdout)
            receipt_path, = (root / ".fullstack/evidence").glob("*.json")
            record = json.loads(receipt_path.read_bytes())
            self.assertEqual(record["exit_code"], 0)
            self.assertIn("Ran 1 test", (root / record["log"]).read_text(encoding="utf-8"))
            for path in (root / ".fullstack").rglob("*"):
                if path.is_file():
                    self.assertFalse(marker.encode() in path.read_bytes(), path.name)
