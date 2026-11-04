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
import sys
import uuid

ALLOW = {"py", "python", "python3", "pytest", "npm", "npx", "pnpm", "node", "uv", "ruff", "mypy", "tsc"}
KINDS = {"test", "lint", "build", "security"}


def allowed_command(cmd:list[str])->bool:
    if not cmd: return False
    exe = Path(cmd[0]).name.lower().removesuffix(".exe")
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
    if exe == "node": return False
    if exe == "npx": return len(args)>1 and args[0]=="--no-install" and args[1] in {"tsc","eslint","vitest","playwright"}
    if exe == "uv": return args[:2]==["run","pytest"] or args[:2]==["run","ruff"]
    return True


def run(project:Path,phase:str,kind:str,command:list[str],timeout:int=120)->tuple[dict,Path]:
    project=project.resolve()
    if not project.is_dir(): raise ValueError("Missing project")
    if not re.fullmatch(r"P[0-7]",phase): raise ValueError("Invalid phase")
    if kind not in KINDS: raise ValueError("Invalid check kind")
    if not allowed_command(command): raise ValueError("Command rejected; run deploy/migration/unknown commands manually only with authorization")
    (project/".fullstack"/"checks").mkdir(parents=True,exist_ok=True)
    (project/".fullstack"/"evidence").mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag=f"{phase}-{kind}-{now}-{uuid.uuid4().hex[:8]}"
    log=project/".fullstack"/"checks"/(tag+".log")
    metadata=project/".fullstack"/"evidence"/(tag+".json")
    try:
        p=subprocess.run(command,cwd=project,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,errors="replace",shell=False,check=False)
        stdout=p.stdout
        returncode=p.returncode
        timed_out=False
    except subprocess.TimeoutExpired as exc:
        stdout=(exc.stdout or b"")
        if isinstance(stdout,bytes): stdout=stdout.decode(errors="replace")
        stdout+="\n[TIMEOUT: configured maximum exceeded]"
        returncode=124
        timed_out=True
    except OSError as exc:
        stdout="[COMMAND FAILED TO START] "+str(exc)
        returncode=127
        timed_out=False
    # The command output may contain sensitive data; redact obvious token/password pairs.
    stdout=re.sub(r"(?i)(password|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*\S+",r"\1=[REDACTED]",stdout)
    log.write_text(stdout,encoding="utf-8")
    digest=hashlib.sha256(log.read_bytes()).hexdigest()
    record={"schema_version":1,"phase":phase,"kind":kind,"command":command,"run_at_utc":now,
            "log":log.relative_to(project).as_posix(),"log_sha256":digest,"exit_code":returncode,"timed_out":timed_out,
            "warning":"Log hash proves local file consistency only, not command authenticity or business correctness."}
    metadata.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return record,metadata


def main():
    p=argparse.ArgumentParser(description="Restricted QA command runner with evidence receipts")
    p.add_argument("--project",default=".")
    p.add_argument("--phase",required=True,choices=[f"P{i}" for i in range(8)])
    p.add_argument("--kind",required=True,choices=sorted(KINDS))
    p.add_argument("--timeout",type=int,default=120)
    p.add_argument("cmd",nargs=argparse.REMAINDER,help="after --, QA command")
    a=p.parse_args()
    command=a.cmd[1:] if a.cmd and a.cmd[0]=="--" else a.cmd
    if not 1 <= a.timeout <= 3600: p.error("timeout must be 1..3600 seconds")
    try: receipt,path=run(Path(a.project),a.phase,a.kind,command,a.timeout)
    except ValueError as exc: p.error(str(exc))
    print("Exit code:",receipt["exit_code"],"evidence:",path)
    print("Log: ",receipt["log"])
    raise SystemExit(0 if receipt["exit_code"]==0 else 2)


if __name__=="__main__": main()
