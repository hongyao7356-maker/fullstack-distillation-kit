"""Ephemeral independent reviewer for orchestration integration fixtures only."""
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import gate_policy


def fixture_reviewer(case):
    temp = tempfile.TemporaryDirectory()
    case.addCleanup(temp.cleanup)
    base = Path(temp.name)
    key = base/"reviewer"
    subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
    signers = base/"allowed_signers"
    signers.write_text("reviewer "+key.with_suffix(".pub").read_text())
    override = patch.object(gate_policy, "SIGNERS", signers)
    override.start()
    case.addCleanup(override.stop)

    def sign(project, phase):
        origin = project/".fullstack/origin"
        origin.mkdir(exist_ok=True)
        payload = base/(phase+".payload")
        payload.write_bytes(gate_policy.attestation_payload(project,phase))
        subprocess.run(["ssh-keygen","-Y","sign","-f",str(key),"-n","fullstack-origin-v1",str(payload)],check=True,capture_output=True)
        Path(str(payload)+".sig").replace(origin/(phase+".sig"))
    return sign
