"""Validate configured identities and independently attested production origin."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from evidence_engine import connect, snapshot, valid_evidence

if os.name == "nt":
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
        raise OSError("Cannot locate system directory")
    SYSTEM = Path(buffer.value)
    SSH = SYSTEM / "OpenSSH/ssh-keygen.exe"
    SIGNERS = SYSTEM / "fullstack-kit/allowed_signers"
else:
    SSH = Path("/usr/bin/ssh-keygen")
    SIGNERS = Path("/etc/fullstack-kit/allowed_signers")

POLICY = Path(__file__).resolve().parents[1] / "templates/phase_policy.json"


def attestation_payload(project, phase):
    """Canonical bytes a trusted reviewer signs after inspecting this exact run."""
    project = Path(project).resolve()
    if not re.fullmatch(r"P[0-7]",phase):
        raise ValueError("Expected a workflow phase")
    with closing(connect(project, readonly=True)) as db:
        rows = db.execute("SELECT check_id,run_id,receipt_hash FROM executions "
                          "WHERE seq IN (SELECT MAX(seq) FROM executions GROUP BY check_id) "
                          "AND phase=? ORDER BY check_id", (phase,)).fetchall()
    statement = dict(version=1, origin="reviewed_real_project" if phase in {"P6","P7"} else "reviewed_project_check",
                     inputs="reviewer_verified_execution_input_closure", project=str(project),
                     phase=phase, source=snapshot(project), runs=[list(r) for r in rows],
                     policy=hashlib.sha256(POLICY.read_bytes()).hexdigest())
    return json.dumps(statement, sort_keys=True, separators=(",",":")).encode()


def trusted_origin(project, phase):
    signature = project / ".fullstack/origin" / (phase + ".sig")
    if not SIGNERS.is_file() or not signature.is_file():
        return False
    # System binary and administrator-managed keyring, never project PATH/config.
    cmd = [str(SSH), "-Y", "verify", "-n", "fullstack-origin-v1", "-I", "reviewer",
           "-f", str(SIGNERS), "-s", str(signature)]
    try:
        result = subprocess.run(cmd, input=attestation_payload(project,phase),
                                capture_output=True, timeout=10, cwd=SSH.parent)
        return result.returncode == 0
    except (OSError, ValueError, sqlite3.Error, subprocess.TimeoutExpired):
        return False


def command_kind(command):
    exe = Path(command[0]).stem.lower()
    args = command[1:]
    if any(arg in {"-h","-V","--help","--version","--collect-only","--co","--fixtures","--fixtures-per-test","--markers","--show-config","--show-settings","--show-files","--generate-config-file"} or arg.startswith("--help") for arg in args):
        return None
    if exe in {"python", "python3", "py"}:
        if exe == "py" and args[:1] == ["-3"]:
            args = args[1:]
        if args[:1] == ["-m"] and len(args) >= 2:
            return {"unittest":"test","pytest":"test","mypy":"lint","compileall":"build"}.get(args[1])
    if exe in {"npm","pnpm"} and len(args) == 2 and args[0] == "run":
        return dict.fromkeys(("test","test:unit","test:integration","test:e2e"),"test").get(
            args[1], {"lint":"lint","typecheck":"lint","build":"build","security":"security"}.get(args[1]))
    if exe == "ruff" and args[:1] == ["check"]:
        return "lint"
    return {"mypy":"lint","pytest":"test"}.get(exe)


def policy_issues(project, phase, required, require_config=False):
    production = phase in {"P6","P7"}
    scope = "production_release" if production else "project_acceptance"
    path = project / ".fullstack/checks.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        items = config.get(phase, [])
        if not isinstance(items,list):
            return ["INVALID_CHECK_CONFIG"]
        kinds, ids, issues = set(), set(), []
        for item in items:
            if not isinstance(item,dict):
                return ["INVALID_CHECK_CONFIG"]
            identity, kind, command = (item.get(k) for k in ("check_id","kind","command"))
            if (not isinstance(identity,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",identity)
                    or identity in ids or kind not in {"test","lint","build","security"}
                    or not isinstance(command,list) or not command
                    or not all(isinstance(s,str) for s in command)):
                return ["INVALID_CHECK_CONFIG"]
            ids.add(identity)
            kinds.add(kind)
            if item.get("scope",scope) != scope or command_kind(command) != kind:
                issues.append("INVALID_CHECK_CONFIG: " + identity)
            elif not valid_evidence(project,phase,kind,scope=scope,check_id=identity,expected_command=command):
                issues.append("INVALID_CHECK_EVIDENCE: " + identity)
        issues.extend("MISSING_REQUIRED_CHECK_CONFIG: " + kind for kind in sorted(set(required)-kinds))
        if (production or require_config) and not items:
            issues.append("MISSING_PHASE_CHECK_CONFIG")
        if production:
            profile = json.loads((project/".fullstack/profile.json").read_text(encoding="utf-8"))
            if profile.get("evidence_origin") != "real_project" or profile.get("production_deploy_authorized") is not True:
                issues.append("PRODUCTION_AUTHORIZATION_REQUIRED")
        if items and not issues:
            if production or any(item.get('contract_version') == '1.3' for item in items):
                from attestation_v13 import trusted_phase
                trusted = trusted_phase(project, phase)
            else:
                trusted = trusted_origin(project, phase)
            if not trusted:
                issues.append("UNVERIFIED_PRODUCTION_ORIGIN" if production else "UNVERIFIED_EXECUTION_INPUTS")
        return issues
    except (OSError,ValueError,TypeError,AttributeError):
        return ["INVALID_CHECK_CONFIG"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Emit the exact reviewer statement for SSH signing")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=[f"P{i}" for i in range(8)])
    options = parser.parse_args()
    sys.stdout.buffer.write(attestation_payload(options.project, options.phase))
