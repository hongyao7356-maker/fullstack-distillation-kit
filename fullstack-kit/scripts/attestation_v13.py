"""Detached SSH execution/review proofs with administrator-owned authorization.

This adapter verifies external proofs. It never supplies execution isolation or
creates an execution-platform identity from untrusted project configuration.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

from evidence_engine import connect, snapshot, valid_evidence

if os.name == 'nt':
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
        raise OSError('Cannot locate system directory')
    SYSTEM = Path(buffer.value)
    SSH = SYSTEM / 'OpenSSH/ssh-keygen.exe'
    TRUST = SYSTEM / 'fullstack-kit/trust-v13.json'
else:
    SSH = Path('/usr/bin/ssh-keygen')
    TRUST = Path('/etc/fullstack-kit/trust-v13.json')

POLICY = Path(__file__).resolve().parents[1] / 'templates/phase_policy.json'
SCOPES = {'project_acceptance', 'production_release'}
KINDS = {'test', 'lint', 'build', 'security'}
MODES = {'CURRENT_ENV_CHECK', 'ATTESTED_BUILD_ARTIFACT'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def timestamp(value):
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('UTC timestamp required')
    return datetime.fromisoformat(value[:-1] + '+00:00')


def utcnow():
    return datetime.now(timezone.utc)


def configuration(project, phase):
    data = json.loads((project / '.fullstack/checks.json').read_text(encoding='utf-8'))
    items = data[phase]
    if not isinstance(items, list) or not items:
        raise ValueError('Missing configured checks')
    candidates = {item.get('candidate_id') for item in items}
    runners = {item.get('runner_id') for item in items}
    if len(candidates) != 1 or len(runners) != 1:
        raise ValueError('A phase must identify one candidate and execution platform')
    candidate, runner = next(iter(candidates)), next(iter(runners))
    if not all(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', value)
               for value in (candidate, runner)):
        raise ValueError('Missing candidate or execution platform identity')
    return items, candidate, runner


def execution_subject(project, phase):
    """Reconstruct the exact current configured runs; never select an older pass."""
    project = Path(project).resolve()
    if not re.fullmatch(r'P[0-7]', phase):
        raise ValueError('Invalid phase')
    items, candidate, runner = configuration(project, phase)
    scope = 'production_release' if phase in {'P6', 'P7'} else 'project_acceptance'
    runs = []
    with closing(connect(project, readonly=True)) as db:
        for item in sorted(items, key=lambda entry: entry['check_id']):
            if not valid_evidence(project, phase, item["kind"], scope=scope,
                                  check_id=item["check_id"], expected_command=item["command"]):
                raise ValueError("Invalid latest check evidence")
            row = db.execute('SELECT * FROM executions WHERE check_id=? ORDER BY seq DESC LIMIT 1',
                             (item['check_id'],)).fetchone()
            if row is None or row['state'] != 'complete' or row['phase'] != phase or row['scope'] != scope:
                raise ValueError('Missing current execution')
            path = (project / row['receipt']).resolve()
            if not path.is_relative_to(project / '.fullstack/evidence'):
                raise ValueError('Invalid receipt location')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != row['receipt_hash']:
                raise ValueError('Receipt changed')
            receipt = json.loads(data)
            if (receipt.get('contract_version') != '1.3' or receipt.get('exit_code') != 0
                    or receipt.get('timed_out') is not False or receipt.get('kind') not in KINDS
                    or receipt.get('scope') != scope):
                raise ValueError('Execution is not successful v1.3 evidence')
            environment = receipt.get('environment')
            if not isinstance(environment, dict) or not environment:
                raise ValueError('Missing environment identity')
            from execution_environment import digest as environment_digest, POLICY as ENV_POLICY
            if (environment.get("schema_version") != "1.3"
                    or environment.get("environment_policy") != ENV_POLICY
                    or environment.get("digest") != environment_digest(
                        {key: value for key, value in environment.items() if key != "digest"})):
                raise ValueError("Invalid environment manifest")
            mode = item.get('environment', {}).get('mode', 'CURRENT_ENV_CHECK')
            if mode not in MODES:
                raise ValueError('Invalid verification mode')
            if receipt.get("environment_mode") != mode or receipt.get("candidate_id") != candidate:
                raise ValueError("Execution belongs to a different candidate or mode")
            started, finished = timestamp(receipt["started_utc"]), timestamp(receipt["finished_utc"])
            if finished < started:
                raise ValueError("Invalid execution times")
            artifact = receipt.get('artifact')
            if artifact is not None and artifact.get("run_id") != row["run_id"]:
                raise ValueError("Artifact belongs to another run")
            if (scope == 'production_release' and item['kind'] == 'build') or mode == 'ATTESTED_BUILD_ARTIFACT':
                if not isinstance(artifact, dict) or not artifact:
                    raise ValueError('Persisted build artifact required')
            runs.append(dict(check_id=item['check_id'], kind=receipt['kind'], scope=scope,
                             command_hash=row['command_hash'], run_id=row['run_id'],
                             receipt_digest=row['receipt_hash'], environment_digest=digest(environment),
                             mode=mode, artifact_digest=digest(artifact) if artifact else None,
                             exit_code=receipt["exit_code"], status="success",
                             started_utc=receipt["started_utc"], finished_utc=receipt["finished_utc"],
                             log_digest=receipt["log_sha256"]))
    return dict(schema_version='1.3', project=str(project), phase=phase, scope=scope,
                candidate_id=candidate, runner_id=runner, source_digest=snapshot(project),
                policy_digest=hashlib.sha256(POLICY.read_bytes()).hexdigest(), runs=runs)


def payload(project, phase, issued_utc, expires_utc):
    result = execution_subject(project, phase)
    result.update(issued_utc=issued_utc, expires_utc=expires_utc)
    validate_payload(result)
    return result


def validate_payload(value):
    if not isinstance(value, dict) or value.get('schema_version') != '1.3':
        raise ValueError('Unsupported attestation schema')
    expected = {'schema_version', 'project', 'phase', 'scope', 'candidate_id', 'runner_id',
                'source_digest', 'policy_digest', 'runs', 'issued_utc', 'expires_utc'}
    if set(value) != expected or value['scope'] not in SCOPES:
        raise ValueError('Invalid attestation fields')
    if not re.fullmatch(r'P[0-7]', value['phase']):
        raise ValueError('Invalid attestation phase')
    expected_scope = "production_release" if value["phase"] in {"P6", "P7"} else "project_acceptance"
    if value["scope"] != expected_scope or not isinstance(value["project"], str):
        raise ValueError("Invalid phase scope")
    for name in ("candidate_id", "runner_id"):
        if not isinstance(value[name], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value[name]):
            raise ValueError("Invalid subject identity")
    for name in ("source_digest", "policy_digest"):
        if not isinstance(value[name], str) or not re.fullmatch("[0-9a-f]{64}", value[name]):
            raise ValueError("Invalid subject digest")
    issued, expires = timestamp(value['issued_utc']), timestamp(value['expires_utc'])
    if expires <= issued or expires - issued > timedelta(hours=24):
        raise ValueError('Invalid attestation lifetime')
    if not isinstance(value['runs'], list) or not value['runs']:
        raise ValueError('Missing executions')
    identities = set()
    for run in value['runs']:
        if (not isinstance(run, dict) or run.get('kind') not in KINDS
                or run.get('scope') != value['scope'] or run.get('mode') not in MODES
                or not isinstance(run.get('check_id'), str) or run['check_id'] in identities):
            raise ValueError('Invalid execution subject')
        identities.add(run['check_id'])
        fields = {"check_id", "kind", "scope", "command_hash", "run_id", "receipt_digest",
                  "environment_digest", "mode", "artifact_digest", "exit_code", "status",
                  "started_utc", "finished_utc", "log_digest"}
        if set(run) != fields or type(run["exit_code"]) is not int or run["exit_code"] != 0 or run["status"] != "success":
            raise ValueError("Invalid execution outcome")
        if not re.fullmatch("[0-9a-f]{32}", run["run_id"]):
            raise ValueError("Invalid execution identity")
        for name in ("command_hash", "receipt_digest", "environment_digest", "log_digest"):
            if not isinstance(run[name], str) or not re.fullmatch("[0-9a-f]{64}", run[name]):
                raise ValueError("Invalid execution digest")
        if timestamp(run["finished_utc"]) < timestamp(run["started_utc"]) or timestamp(run["finished_utc"]) > issued:
            raise ValueError("Invalid execution time ordering")
        if (run['mode'] == 'ATTESTED_BUILD_ARTIFACT' or
                value['scope'] == 'production_release' and run['kind'] == 'build'):
            if not isinstance(run.get('artifact_digest'), str) or not re.fullmatch('[0-9a-f]{64}', run['artifact_digest']):
                raise ValueError('Missing artifact binding')


def authorized(entry, role, value, now):
    if not isinstance(entry, dict):
        return False
    for field in ("projects", "phases", "scopes", "runner_ids"):
        if not isinstance(entry.get(field), list) or not all(isinstance(x, str) for x in entry[field]):
            return False
    return (entry.get('role') == role and entry.get('revoked') is False
            and value['project'] in entry.get('projects', [])
            and value['phase'] in entry.get('phases', [])
            and value['scope'] in entry.get('scopes', [])
            and value['runner_id'] in entry.get('runner_ids', [])
            and timestamp(entry['not_before']) <= timestamp(value['issued_utc']) <= now
            and now < timestamp(value['expires_utc']) <= timestamp(entry['not_after']))


def trusted_phase(project, phase):
    """Require separate authorized execution and review signatures on exact bytes."""
    try:
        project = Path(project).resolve()
        origin = project / '.fullstack/origin'
        value = json.loads((origin / (phase + '.attestation.json')).read_text(encoding='utf-8'))
        validate_payload(value)
        now = utcnow()
        if not timestamp(value['issued_utc']) <= now < timestamp(value['expires_utc']):
            return False
        expected = execution_subject(project, phase)
        if {key: value[key] for key in expected} != expected:
            return False
        trust = json.loads(TRUST.read_text(encoding='utf-8'))
        if trust.get('schema_version') != '1.3' or not isinstance(trust.get('signers'), list):
            return False
        accepted = {}
        for role in ('runner', 'reviewer'):
            for entry in trust['signers']:
                if not authorized(entry, role, value, now):
                    continue
                key = entry.get('public_key', '')
                if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}', key):
                    continue
                with tempfile.TemporaryDirectory(prefix='fullstack-trust-') as temporary:
                    signers = Path(temporary) / 'allowed_signers'
                    signers.write_text(role + ' ' + key + '\n', encoding='ascii')
                    cmd = [str(SSH), '-Y', 'verify', '-n', 'fullstack-v1.3-' + role,
                           '-I', role, '-f', str(signers), '-s', str(origin / (phase + '.' + role + '.sig'))]
                    result = subprocess.run(cmd, input=canonical(value), capture_output=True,
                                            timeout=10, cwd=SSH.parent)
                if result.returncode == 0:
                    accepted[role] = key
                    break
        return (len(accepted) == 2 and accepted['runner'] != accepted['reviewer']
                and execution_subject(project, phase) == expected)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error, subprocess.TimeoutExpired):
        return False
