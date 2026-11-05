"""v2 evidence: ordered executions, atomic receipts and fail-closed validation."""
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

SCOPES = {'tool_selftest', 'project_acceptance', 'production_release'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


INPUT_POLICY = "project-image-v1"
_GIT = Path(".git")
_CONTROL = Path(".fullstack")
_STATE_DIRS = {_CONTROL / name for name in ("checks", "evidence", "evidence-v2", "locks", "origin")}
_STATE_FILES = {(_CONTROL / "workflow.sqlite3"), (_CONTROL / "evidence-v2/index.sqlite3")}
_DATABASE_FILES = {path.with_name(path.name + suffix) for path in _STATE_FILES
                   for suffix in ("", "-wal", "-shm", "-journal")}
_SIGNATURES = {_CONTROL / "origin" / f"P{i}.sig" for i in range(8)}
_OUTPUT_NAMES = {
    _CONTROL / "locks": re.compile(r"(?:workflow|[0-9a-f]{64})[.]lock"),
    _CONTROL / "evidence": re.compile(r"P[0-7]-(?:test|build|lint|security)-[0-9a-f]{32}[.]json"),
    _CONTROL / "checks": re.compile(r"P[0-7]-(?:test|build|lint|security)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}[.]log"),
}


def managed_path(relative):
    if relative in _DATABASE_FILES or relative in _SIGNATURES or relative == _GIT or _GIT in relative.parents:
        return True
    pattern = _OUTPUT_NAMES.get(relative.parent)
    if pattern:
        # atomic_write uses a target-specific temporary sibling.
        target = re.sub(r"[.][0-9a-f]{32}[.]tmp$", "", relative.name)
        return bool(pattern.fullmatch(target))
    return False


def _raise_walk_error(error):
    raise error


def snapshot(project, *, destination=None, identity=None, project_entries=None):
    """Hash exactly the project tree made available in the execution image."""
    project = Path(project).resolve()
    rows = [("policy", INPUT_POLICY), ("project", str(identity or project))]
    for folder, dirs, files in os.walk(project, onerror=_raise_walk_error):
        base = Path(folder)
        relative = base.relative_to(project)
        for name in dirs + files:
            entry = base / name
            if entry.is_symlink() or getattr(entry, "is_junction", lambda: False)():
                raise ValueError("Project input links require explicit review")
        dirs[:] = sorted(name for name in dirs if not managed_path(relative / name))
        if relative != Path("."):
            if relative not in _STATE_DIRS:
                rows.append((relative.as_posix() + "/", None))
            if destination is not None:
                (destination / relative).mkdir()
        for name in sorted(files):
            path = relative / name
            if managed_path(path):
                continue
            data = (project / path).read_bytes()
            rows.append((path.as_posix(), digest(data)))
            if destination is not None:
                copied = destination / path
                copied.write_bytes(data)
                copied.chmod((project / path).stat().st_mode)
    if project_entries is not None:
        project_entries.update(rows[2:])
    scripts = Path(__file__).parent
    for path in sorted(scripts.glob("*.py")):
        rows.append(("engine/" + path.name, digest(path.read_bytes())))
    policy = scripts.parent / "templates" / "phase_policy.json"
    rows.append(("engine/phase_policy.json", digest(policy.read_bytes())))
    return digest(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode())


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


@contextmanager
def file_lock(path, timeout=120):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        # Windows permits locking beyond EOF. Initializing a byte here races
        # another process that has already locked that byte.
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline: raise ValueError('Check lock timeout')
                time.sleep(.05)
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def db_path(project): return Path(project) / '.fullstack/evidence-v2/index.sqlite3'


def connect(project, readonly=False):
    path = db_path(project)
    if readonly:
        conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('''CREATE TABLE IF NOT EXISTS executions (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT UNIQUE NOT NULL,
            check_id TEXT NOT NULL, phase TEXT NOT NULL, kind TEXT NOT NULL,
            scope TEXT NOT NULL, command_hash TEXT NOT NULL, source_hash TEXT NOT NULL,
            state TEXT NOT NULL, receipt TEXT, receipt_hash TEXT)''')
        conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def begin(project, phase, kind, command, check_id=None, scope='tool_selftest'):
    check_id = check_id or phase + '.' + kind
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', check_id): raise ValueError('Invalid check_id')
    if scope not in SCOPES: raise ValueError('Invalid scope')
    row = dict(run_id=uuid.uuid4().hex, check_id=check_id, phase=phase, kind=kind,
               scope=scope, command_hash=digest(json.dumps(command, separators=(',', ':')).encode()),
               source_hash=snapshot(project), state='running')
    with closing(connect(project)) as conn:
        with conn:
            previous = conn.execute('SELECT phase,kind FROM executions WHERE check_id=? LIMIT 1', (check_id,)).fetchone()
            if previous and (previous['phase'], previous['kind']) != (phase, kind):
                raise ValueError('check_id already belongs to another phase/kind')
            cur = conn.execute('INSERT INTO executions(run_id,check_id,phase,kind,scope,command_hash,source_hash,state) VALUES (:run_id,:check_id,:phase,:kind,:scope,:command_hash,:source_hash,:state)', row)
            row['seq'] = cur.lastrowid
    return row


def finish(project, row, receipt):
    receipt.update({k: row[k] for k in ['run_id', 'check_id', 'seq', 'scope', 'command_hash', 'source_hash']})
    receipt['schema_version'] = 2
    receipt['input_policy'] = INPUT_POLICY
    receipt['source_unchanged'] = receipt.get('image_unchanged') is True and snapshot(project) == row['source_hash']
    path = Path(project) / '.fullstack/evidence' / (row['phase'] + '-' + row['kind'] + '-' + row['run_id'] + '.json')
    data = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()
    atomic_write(path, data)
    with closing(connect(project)) as conn:
        with conn:
            conn.execute('UPDATE executions SET state=?,receipt=?,receipt_hash=? WHERE run_id=?',
                         ('complete', path.relative_to(project).as_posix(), digest(data), row['run_id']))
    return path


def valid_evidence(project, phase, kind, scope=None, check_id=None, expected_command=None):
    project = Path(project).resolve()
    try:
        with closing(connect(project, readonly=True)) as conn:
            rows = conn.execute('SELECT * FROM executions WHERE seq IN (SELECT MAX(seq) FROM executions GROUP BY check_id) AND phase=? AND kind=?', (phase, kind)).fetchall()
        if check_id is not None: rows = [r for r in rows if r['check_id'] == check_id]
        if not rows: return False
        current = snapshot(project)
        for row in rows:
            if row['state'] != 'complete' or row['source_hash'] != current: return False
            if scope is not None and row['scope'] != scope: return False
            if expected_command is not None and row['command_hash'] != digest(json.dumps(expected_command,separators=(',', ':')).encode()): return False
            path = (project / row['receipt']).resolve()
            if not path.is_relative_to(project / '.fullstack/evidence'): return False
            data = path.read_bytes()
            if digest(data) != row['receipt_hash']: return False
            receipt = json.loads(data)
            for field in ['run_id','check_id','seq','phase','kind','scope','source_hash','command_hash']:
                if receipt.get(field) != row[field]: return False
            if receipt.get('input_policy') != INPUT_POLICY or receipt.get('schema_version') != 2 or receipt.get('exit_code') != 0 or receipt.get('timed_out') is not False or receipt.get('source_unchanged') is not True: return False
            log = (project / receipt['log']).resolve()
            if not log.is_relative_to(project / '.fullstack/checks'): return False
            if digest(log.read_bytes()) != receipt['log_sha256']: return False
        return True
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        return False
