"""Read-only signed release check, optionally against the actual delivery tree."""
import argparse
import json
from pathlib import Path
import sys
import sqlite3
from contextlib import closing

from artifacts import verify_delivery
from evidence_engine import connect
from workflow import requirements, context_hash
from attestation_v13 import payload, canonical
from run_check import SafeArgumentParser


def main():
    parser = SafeArgumentParser(prog="verify_release.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=["verify", "payload"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--phase", choices=[f"P{i}" for i in range(8)], required=True)
    parser.add_argument("--issued-utc")
    parser.add_argument("--expires-utc")
    parser.add_argument("--delivery-root", type=Path,
                        help="Contains one subdirectory per build run_id, each with its output files")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        if args.action == "payload":
            sys.stdout.buffer.write(canonical(payload(project, args.phase, args.issued_utc, args.expires_utc)))
            return 0
        initial_context = context_hash(project, args.phase)
        issues = requirements(project, args.phase)
        if not issues and args.delivery_root:
            config = json.loads((project/".fullstack/checks.json").read_text(encoding="utf-8"))[args.phase]
            builds = [item for item in config if item["kind"] == "build"]
            if not builds:
                issues.append("NO_DELIVERABLE_BUILD")
            with closing(connect(project, readonly=True)) as db:
                for item in builds:
                    row = db.execute("SELECT receipt FROM executions WHERE check_id=? ORDER BY seq DESC LIMIT 1",
                                     (item["check_id"],)).fetchone()
                    receipt = json.loads((project/row["receipt"]).read_bytes())
                    if not verify_delivery(project, receipt["artifact"], args.delivery_root/receipt["run_id"]):
                        issues.append("DELIVERY_ARTIFACT_MISMATCH")
        # Verify again after file reads to detect ordinary concurrent state changes.
        if not issues:
            issues = requirements(project, args.phase)
        if not issues and context_hash(project, args.phase) != initial_context:
            issues.append("RELEASE_CANDIDATE_CHANGED")
        print(json.dumps({"status": "BLOCKED" if issues else "TOOLING_READY_FOR_HUMAN_REVIEW",
                          "issues": issues}))
        return 2 if issues else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
        print('{"status":"BLOCKED","issues":["INVALID_RELEASE_INPUT"]}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
