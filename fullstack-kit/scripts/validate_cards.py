#!/usr/bin/env python3
"""Validate traceability fields. Does not independently verify truth of claims."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = {"id", "title", "source_id", "source_url", "claim", "classification", "status", "confidence", "conditions", "anti_patterns", "verify", "phase", "provenance"}
STATUSES = {"verified", "candidate", "contradicted"}
CLASSIFICATIONS = {"author_statement", "repository_observation", "engineering_inference"}


def validate_card(card: dict, source_ids: set) -> list[str]:
    errors=[]
    for field in sorted(REQUIRED - card.keys()):
        errors.append("missing field: " + field)
    if errors: return errors
    if not isinstance(card["id"],str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}",card["id"]): errors.append("invalid card id")
    if card["source_id"] not in source_ids: errors.append("unknown source_id")
    parsed=urlparse(str(card["source_url"]))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password: errors.append("source_url must be an uncredentialed HTTPS URL")
    for f in ("title","claim"):
        if not isinstance(card[f],str) or len(card[f].strip()) < (6 if f=="title" else 20): errors.append(f"{f} too short")
    if card["classification"] not in CLASSIFICATIONS: errors.append("invalid classification")
    if card["status"] not in STATUSES: errors.append("invalid status")
    if card["confidence"] not in set("ABCD"): errors.append("invalid confidence")
    if card["phase"] not in {"P0","P1","P2","P3","P4","P5","P6","P7"}: errors.append("invalid phase")
    for f in ("conditions","anti_patterns","verify"):
        if not isinstance(card[f],list) or not card[f] or any(not isinstance(x,str) or not x.strip() for x in card[f]): errors.append(f"{f} must be a nonempty list of strings")
    prov=card["provenance"]
    if not isinstance(prov,dict) or any(not str(prov.get(x,"")).strip() for x in ("observed_at","revision","locator")):
        errors.append("incomplete provenance")
    if card["status"] == "verified" and card["confidence"] == "D": errors.append("D confidence cannot be verified")
    return errors


def validate_all(kit:Path, cards_dir:Path) -> tuple[int,list[str]]:
    registry=json.loads((kit/"sources"/"source_registry.json").read_text(encoding="utf-8"))
    sources={x["id"] for x in registry["sources"]}
    problems=[]
    seen=set()
    count=0
    for p in sorted(cards_dir.glob("*.json")):
        count+=1
        try: c=json.loads(p.read_text(encoding="utf-8"))
        except (ValueError,UnicodeDecodeError) as exc:
            problems.append(f"{p}: invalid JSON {exc}")
            continue
        if c.get("id") in seen: problems.append(f"{p}: duplicate id")
        seen.add(c.get("id"))
        for err in validate_card(c,sources): problems.append(f"{p.name}: {err}")
    if not count: problems.append("no cards found")
    return count,problems


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cards",help="Custom cards directory (default: packaged cards)")
    a=p.parse_args()
    kit=Path(__file__).resolve().parents[1]
    n,errors=validate_all(kit,Path(a.cards) if a.cards else kit/"cards")
    for e in errors: print("ERROR:",e)
    if errors: raise SystemExit(2)
    print(f"OK: {n} cards structurally valid (truth still needs independent review)")


if __name__=="__main__": main()
