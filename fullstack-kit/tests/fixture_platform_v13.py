"""Isolated signing authority for synthetic integration tests only."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import attestation_v13 as attestation


def platform(case):
    temp = tempfile.TemporaryDirectory()
    case.addCleanup(temp.cleanup)
    base = Path(temp.name)
    keys = {}
    for role in ("runner", "reviewer"):
        key = base / role
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        keys[role] = key
    trust = base / "trust.json"
    override = patch.object(attestation, "TRUST", trust)
    override.start()
    case.addCleanup(override.stop)

    def sign(project, phase, lifetime=timedelta(hours=1)):
        now = datetime.now(timezone.utc)
        utc = lambda value: value.isoformat().replace("+00:00", "Z")
        value = attestation.payload(project, phase, utc(now), utc(now + lifetime))
        entries = []
        origin = project / ".fullstack/origin"
        origin.mkdir(exist_ok=True)
        payload = base / (phase + ".json")
        payload.write_bytes(attestation.canonical(value))
        (origin / (phase + ".attestation.json")).write_bytes(payload.read_bytes())
        for role, key in keys.items():
            entries.append(dict(role=role, revoked=False, projects=[str(project.resolve())],
                phases=[phase], scopes=[value["scope"]], runner_ids=[value["runner_id"]],
                not_before=utc(now - timedelta(days=1)), not_after=utc(now + timedelta(days=1)),
                public_key=" ".join(Path(str(key)+".pub").read_text().split()[:2])))
            signature = Path(str(payload) + ".sig")
            if signature.exists():
                signature.unlink()
            subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n",
                "fullstack-v1.3-" + role, str(payload)], check=True, capture_output=True)
            signature.replace(origin / (phase + "." + role + ".sig"))
        trust.write_text(json.dumps(dict(schema_version="1.3", signers=entries)))
        return value
    return sign, trust
