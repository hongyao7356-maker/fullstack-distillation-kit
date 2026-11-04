#!/usr/bin/env python3
"""Check documented deliverables and locally recorded, hashed QA logs.
Pass means 'READY_FOR_HUMAN_REVIEW', never permission to deploy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PLACEHOLDERS=("TO_BE_CONFIRMED", "TODO: FILL", "待填写", "请在这里填写")


def good_doc(path:Path)->bool:
    if not path.is_file(): return False
    txt=path.read_text(encoding="utf-8",errors="replace")
    return len(txt.strip())>=120 and not any(x in txt for x in PLACEHOLDERS)


def evidence_ok(project:Path,phase:str,kind:str)->bool:
    from evidence_engine import valid_evidence
    return valid_evidence(project,phase,kind)


def check_gate(project:Path,phase:str,policy:dict)->list[str]:
    project=project.resolve()
    if phase not in policy: raise ValueError("invalid phase")
    issues=[]
    for name in policy[phase]["docs"]:
        p=project/".fullstack"/"docs"/name
        if not good_doc(p): issues.append("Missing/short/placeholder document: "+p.relative_to(project).as_posix())
    for kind in policy[phase]["checks"]:
        if not evidence_ok(project,phase,kind): issues.append("Missing/failed/tampered QA receipt: "+kind)
    return issues


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--project",default=".")
    p.add_argument("--phase",required=True,choices=[f"P{i}" for i in range(8)])
    a=p.parse_args()
    kit=Path(__file__).resolve().parents[1]
    policy=json.loads((kit/"templates"/"phase_policy.json").read_text(encoding="utf-8"))
    issues=check_gate(Path(a.project),a.phase,policy)
    if issues:
        print("BLOCKED:",a.phase)
        for item in issues: print("-",item)
        raise SystemExit(2)
    print("READY_FOR_HUMAN_REVIEW:",a.phase)
    print("Documentation and required QA log integrity checks passed.")
    print("This is not an attestation of functional correctness, security or production approval.")


if __name__=="__main__": main()
