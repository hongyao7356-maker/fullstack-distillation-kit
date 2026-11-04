#!/usr/bin/env python3
"""Validate pack shape, example cards and basic phase configuration."""
import json
import sys
from pathlib import Path


def verify(kit:Path)->list[str]:
    errors=[]
    root=kit.parent
    for name in ("fullstack-lifecycle","fullstack-distillation","fullstack-review"):
        p=root/".agents"/"skills"/name/"SKILL.md"
        if not p.is_file(): errors.append("missing skill "+str(p))
        elif not p.read_text(encoding="utf-8").startswith("---\nname: "):
            errors.append("invalid frontmatter: "+str(p))
    policy_file=kit/"templates"/"phase_policy.json"
    try:
        policy=json.loads(policy_file.read_text(encoding="utf-8"))
        if set(policy)!={f"P{i}" for i in range(8)}: errors.append("phase policy must contain P0...P7")
        for phase in policy:
            if not policy[phase].get("docs"): errors.append("missing docs policy for "+phase)
            if not list((kit/"references").glob(phase+"_*.md")): errors.append("missing phase guide for "+phase)
    except (ValueError,OSError) as e:
        errors.append("bad phase policy: "+str(e))
    registry_file=kit/"sources"/"source_registry.json"
    try:
        registry=json.loads(registry_file.read_text(encoding="utf-8"))
        if len(registry["sources"])<4: errors.append("source registry too small")
    except (ValueError,OSError,KeyError) as e:
        errors.append("bad registry: "+str(e))
    sys.path.insert(0,str(kit/"scripts"))
    from validate_cards import validate_all
    _,card_errors=validate_all(kit,kit/"cards")
    errors.extend(card_errors)
    for name in ("BOOTSTRAP_CODEX.md", "references/DISTILLATION_PROTOCOL.md","references/QUALITY_AND_TRUST.md"):
        if not (kit/name).is_file(): errors.append("missing "+name)
    return errors


def main():
    kit=Path(__file__).resolve().parents[1]
    errors=verify(kit)
    for err in errors: print("ERROR:",err)
    if errors: raise SystemExit(2)
    print("OK: pack structure, references, policy and sample cards verified")
    print("NOTE: does NOT prove external sources were thoroughly studied or any project was tested")


if __name__=="__main__": main()
