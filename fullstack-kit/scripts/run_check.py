#!/usr/bin/env python3
"""Run explicitly supplied local QA commands (no shell) and record hashed logs.
Does not run deployment, migrations or commands taken from untrusted source pages.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import sys
import uuid
from command_executor import execute, resolve
from security import secure_command,redact
from evidence_engine import begin, finish, file_lock, atomic_write, managed_path, snapshot

ALLOW = {"py", "python", "python3", "pytest", "npm", "npx", "pnpm", "node", "uv", "ruff", "mypy", "tsc"}
KINDS = {"test", "lint", "build", "security"}


def check_configuration(project, phase, check_id):
    path = project / ".fullstack/checks.json"
    if not path.exists():
        return {}
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Invalid checks configuration")
    items = config.get(phase, [])
    if not isinstance(items, list):
        raise ValueError("Invalid phase configuration")
    matches = [item for item in items if isinstance(item, dict) and item.get("check_id") == check_id]
    if len(matches) > 1:
        raise ValueError("Duplicate check identity")
    item = matches[0] if matches else {}
    if not isinstance(item.get("environment", {}), dict):
        raise ValueError("Invalid environment configuration")
    return item


def allowed_command(cmd:list[str])->bool:
    if not cmd: return False
    exe = Path(cmd[0]).name.lower().removesuffix(".exe").removesuffix(".cmd")
    if exe not in ALLOW: return False
    # Never run shell wrappers, install, deploy, publish or remote execution via this helper.
    forbidden={"install","uninstall","deploy","publish","db:push","migrate","prisma","-c","--eval","exec","dlx","add","remove","init","create"}
    args=[x.lower() for x in cmd[1:]]
    if any(x in forbidden for x in args): return False
    if any(x.startswith("http://") or x.startswith("https://") for x in args): return False
    if exe in {"py","python","python3"}:
        # Only module/test-file execution, not arbitrary Python snippets.
        if not args: return False
        if exe=="py" and args[0] == "-3": args=args[1:]
        if args[:2]==["-m", "unittest"] or args[:2]==["-m","pytest"] or args[:2]==["-m","compileall"] or args[:2]==["-m","mypy"]: return True
        return False
    if exe in {"npm","pnpm"}:
        return len(args)>1 and args[0]=="run" and args[1] in {"test","test:unit","test:integration","test:e2e","lint","build","check","validate","typecheck"}
    if exe == "node": return bool(args) and Path(cmd[1]).is_absolute() and Path(cmd[1]).suffix in {".js",".cjs",".mjs"}
    if exe == "npx": return len(args)>1 and args[0]=="--no-install" and args[1] in {"tsc","eslint","vitest","playwright"}
    if exe == "uv": return args[:2]==["run","pytest"] or args[:2]==["run","ruff"]
    return True


def _run(project:Path,phase:str,kind:str,command:list[str],timeout:int=120,check_id=None,scope="tool_selftest")->tuple[dict,Path]:
    project=project.resolve()
    if not project.is_dir(): raise ValueError("Missing project")
    if not re.fullmatch(r"P[0-7]",phase): raise ValueError("Invalid phase")
    if kind not in KINDS: raise ValueError("Invalid check kind")
    safe_command,secret_rejected=secure_command(command)
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    (project/".fullstack"/"checks").mkdir(parents=True,exist_ok=True)
    (project/".fullstack"/"evidence").mkdir(parents=True,exist_ok=True)
    execution=begin(project,phase,kind,safe_command,check_id,scope)
    now=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag=f"{phase}-{kind}-{now}-{uuid.uuid4().hex[:8]}"
    log=project/".fullstack"/"checks"/(tag+".log")
    metadata=project/".fullstack"/"evidence"/(tag+".json")
    image_unchanged = False
    result_image_hash = None
    environment = None
    artifact = None
    configuration = {}
    if secret_rejected or not allowed_command(command):
        stdout,returncode,timed_out="[COMMAND REJECTED: secret arguments or unsupported command]",126,False
    else:
        try:
            configuration = check_configuration(project, phase, execution["check_id"])
            controlled = scope != "tool_selftest" or "environment" in configuration
            if controlled:
                from execution_environment import capture_environment
                child_env, environment = capture_environment(project, command, execution["check_id"])
            else:
                child_env = None
            # Validate the tool against the original project before changing cwd.
            resolve(command, project)
            with tempfile.TemporaryDirectory(prefix="fullstack-input-") as temp:
                image = Path(temp).resolve()
                if image.is_relative_to(project):
                    raise ValueError("Execution image must be outside project")
                original_entries = {}
                before = snapshot(project, destination=image, project_entries=original_entries)
                if before != execution["source_hash"]:
                    raise ValueError("Input changed during image creation")
                args = [command[0]]
                for arg in command[1:]:
                    path = Path(arg)
                    if path.is_absolute():
                        relative = path.resolve().relative_to(project)
                        if managed_path(relative):
                            raise ValueError("Managed runtime input")
                        arg = str(image / relative)
                    elif ".." in path.parts or managed_path(path):
                        raise ValueError("Outside execution image")
                    args.append(arg)
                stdout, returncode, timed_out = execute(args, image, timeout, env=child_env)
                result_entries = {}
                result_image_hash = snapshot(image, identity=project, project_entries=result_entries)
                image_unchanged = before == result_image_hash
                if kind == "build" and not image_unchanged:
                    # Additional build outputs may live only beneath these roots.
                    # Existing inputs (including existing dist files) remain bound.
                    added = result_entries.keys() - original_entries.keys()
                    image_unchanged = (
                        bool(added)
                        and original_entries.items() <= result_entries.items()
                        and all(name.startswith(("dist/", "build/")) for name in added)
                    )
                if controlled:
                    from execution_environment import environment_matches
                    image_unchanged = image_unchanged and environment_matches(
                        project, command, execution["check_id"], environment)
                if returncode == 0 and not timed_out and image_unchanged and configuration.get("outputs"):
                    from artifacts import publish
                    if kind != "build":
                        raise ValueError("Only build checks publish artifacts")
                    artifact = publish(project, image, execution["run_id"], configuration["outputs"])
        except (ValueError, OSError):
            stdout, returncode, timed_out = "[COMMAND FAILED TO START: unsafe or unavailable input]", 127, False
    # The command output may contain sensitive data; redact obvious token/password pairs.
    stdout=redact(stdout)
    atomic_write(log,stdout.encode("utf-8"))
    digest=hashlib.sha256(log.read_bytes()).hexdigest()
    record={"result_image_hash":result_image_hash,"input_assurance":"local_image_only","image_unchanged":image_unchanged,"schema_version":1,"phase":phase,"kind":kind,"command":safe_command,"run_at_utc":now,
            "log":log.relative_to(project).as_posix(),"log_sha256":digest,"exit_code":returncode,"timed_out":timed_out,
            "warning":"Log hash proves local file consistency only, not command authenticity or business correctness."}
    record.update(contract_version="1.3", environment=environment, artifact=artifact,
                  candidate_id=configuration.get("candidate_id", "default"),
                  environment_mode=configuration.get("environment", {}).get("mode", "CURRENT_ENV_CHECK"),
                  started_utc=started_utc,
                  finished_utc=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"))
    metadata=finish(project,execution,record)
    return record,metadata


def run(project,phase,kind,command,timeout=120,check_id=None,scope="tool_selftest"):
    project=Path(project).resolve()
    if not project.is_dir(): raise ValueError("Missing project")
    if not 1 <= timeout <= 3600: raise ValueError("Invalid timeout")
    lock_id=hashlib.sha256((check_id or phase+"."+kind).encode()).hexdigest()
    with file_lock(project/".fullstack/locks"/(lock_id+".lock"), timeout+30):
        return _run(project,phase,kind,command,timeout,check_id,scope)


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can embed any supplied value, including unlabeled secrets.
        self.print_usage(sys.stderr)
        self.exit(2, "Invalid QA runner arguments. See run_check.py --help.\n")


def main():
    p=SafeArgumentParser(prog="run_check.py", allow_abbrev=False,
                         description="Restricted QA command runner with evidence receipts")
    p.add_argument("--project",default=".")
    p.add_argument("--phase",required=True,choices=[f"P{i}" for i in range(8)])
    p.add_argument("--kind",required=True,choices=sorted(KINDS))
    p.add_argument("--check-id")
    p.add_argument("--scope",choices=["tool_selftest","project_acceptance","production_release"],default="tool_selftest")
    p.add_argument("--timeout",type=int,default=120)
    p.add_argument("cmd",nargs=argparse.REMAINDER,help="after --, QA command")
    a=p.parse_args()
    if len(a.cmd) < 2 or a.cmd[0] != "--":
        p.error("Expected -- followed by a command")
    command=a.cmd[1:]
    if not 1 <= a.timeout <= 3600: p.error("timeout must be 1..3600 seconds")
    if a.check_id is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", a.check_id):
        p.error("Invalid check identity")
    try: receipt,path=run(Path(a.project),a.phase,a.kind,command,a.timeout,a.check_id,a.scope)
    except (ValueError,OSError): p.error("QA runner rejected the request")
    print("Exit code:",receipt["exit_code"],"evidence:",redact(str(path)))
    print("Log: ",receipt["log"])
    raise SystemExit(0 if receipt["exit_code"]==0 else 2)


if __name__=="__main__": main()
