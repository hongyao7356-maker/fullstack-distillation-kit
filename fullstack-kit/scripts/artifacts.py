"""Durable, bounded build output sets. Trust in the producer is verified separately."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid

from evidence_engine import file_lock


def _digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid artifact path')
    parts = value.split('/')
    for part in parts:
        if (not part or part in {'.', '..'} or part[-1] in {' ', '.'}
                or any(ord(c) < 32 or c in ':*?"<>|' for c in part)
                or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)):
            raise ValueError('Invalid artifact path')
    return PurePosixPath(value)


def _regular(path, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Artifact links and reparse points forbidden')
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('Unexpected artifact object type')


@contextmanager
def _pinned_directory(path):
    """Prevent Windows parent renames while paths below the directory are used."""
    _regular(path, True)
    if os.name != 'nt':
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0, 3, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), 'Cannot pin artifact directory')
    try:
        _regular(path, True)
        yield
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def _parents(path):
    with ExitStack() as stack:
        for directory in reversed([path, *path.parents]):
            stack.enter_context(_pinned_directory(directory))
        yield


def _read(path, limit):
    _regular(path)
    if os.name == 'nt':
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        # Deny concurrent writers/deletion and open a link itself rather than its target.
        handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), 'Cannot lock artifact input')
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    else:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or getattr(before, 'st_file_attributes', 0) & 0x400):
            raise ValueError('Artifact links or special files forbidden')
        if before.st_size > limit:
            raise ValueError('Artifact size limit exceeded')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    _regular(path)
    current = path.stat()
    if (len(data) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns) or before.st_ino != current.st_ino
            or before.st_mtime_ns != current.st_mtime_ns):
        raise ValueError('Artifact changed while copying')
    return data


def _entries(image, outputs):
    if not isinstance(outputs, list) or not outputs:
        raise ValueError('Explicit artifact outputs required')
    selected, total = {}, 0
    for output in outputs:
        if not isinstance(output, dict) or set(output) != {'path', 'type', 'max_bytes', 'max_files'}:
            raise ValueError('Invalid artifact output declaration')
        relative = _relative(output['path'])
        if output['type'] not in {'file', 'directory'}:
            raise ValueError('Invalid artifact type')
        if any(type(output[k]) is not int or output[k] < 1 for k in ('max_bytes','max_files')):
            raise ValueError('Invalid artifact limits')
        root = image / relative
        with _parents(root.parent):
            _regular(root, output['type'] == 'directory')
        paths = [root] if output['type'] == 'file' else sorted(root.rglob('*'))
        size, count = 0, 0
        for path in paths:
            with _parents(path.parent):
                if path.is_dir():
                    _regular(path, True)
                    continue
                name = _relative(path.relative_to(image).as_posix()).as_posix()
                key = name.casefold()
                if key in selected:
                    raise ValueError('Overlapping or case-colliding artifact paths')
                data = _read(path, output['max_bytes'] - size)
                size += len(data)
                count += 1
                total += len(data)
                if count > output['max_files'] or total > 1024 * 1024 * 1024:
                    raise ValueError('Artifact set limit exceeded')
                selected[key] = (name, data)
        if count == 0:
            raise ValueError('Artifact declaration matched no files')
    return sorted(selected.values())


def _commit(staging, target):
    if target.exists():
        raise FileExistsError('Artifact run already exists')
    staging.rename(target)


def publish(project, image, run_id, outputs):
    if not isinstance(run_id, str) or not re.fullmatch('[0-9a-f]{32}', run_id):
        raise ValueError('Invalid artifact run identity')
    project, image = Path(project).absolute(), Path(image).absolute()
    # Resolve neither path before validating their ancestors for reparse points.
    with _parents(project), _parents(image), ExitStack() as parents:
        entries = _entries(image, outputs)
        metadata = project / ".fullstack"
        metadata.mkdir(exist_ok=True)
        parents.enter_context(_parents(metadata))
        store = project / '.fullstack/artifacts'
        store.mkdir(exist_ok=True)
        with _parents(store):
            target = store / run_id
            with file_lock(store / ('.' + run_id + '.lock')):
                if target.exists():
                    raise FileExistsError('Artifact run already exists')
                staging = store / ('.staging-' + run_id + '-' + uuid.uuid4().hex)
                staging.mkdir()
                try:
                    files = []
                    for name, data in entries:
                        path = staging / 'files' / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('xb') as stream:
                            stream.write(data)
                            stream.flush()
                            os.fsync(stream.fileno())
                        if path.read_bytes() != data:
                            raise ValueError('Artifact copy verification failed')
                        files.append(dict(path=name, size=len(data), sha256=_digest(data)))
                    manifest = _json(dict(schema_version='1.3', run_id=run_id, files=files))
                    with (staging / 'artifact-manifest.json').open('xb') as stream:
                        stream.write(manifest)
                        stream.flush()
                        os.fsync(stream.fileno())
                    _commit(staging, target)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)
                return dict(schema_version='1.3', run_id=run_id,
                            location=target.relative_to(project).as_posix(), manifest_digest=_digest(manifest))


def verify(project, descriptor):
    try:
        if set(descriptor) != {'schema_version','run_id','location','manifest_digest'} or descriptor['schema_version'] != '1.3':
            return False
        run_id = descriptor['run_id']
        if not isinstance(run_id,str) or not re.fullmatch('[0-9a-f]{32}',run_id):
            return False
        if descriptor['location'] != '.fullstack/artifacts/' + run_id:
            return False
        root = Path(project).absolute() / descriptor['location']
        with _parents(root):
            raw = _read(root/'artifact-manifest.json', 10 * 1024 * 1024)
            if _digest(raw) != descriptor['manifest_digest']:
                return False
            manifest = json.loads(raw)
            if set(manifest) != {'schema_version','run_id','files'} or manifest['schema_version'] != '1.3' or manifest['run_id'] != run_id:
                return False
            if not isinstance(manifest['files'],list) or not manifest['files']:
                return False
            expected, folded = {'artifact-manifest.json'}, set()
            for item in manifest['files']:
                if set(item) != {'path','size','sha256'} or type(item['size']) is not int or item['size'] < 0:
                    return False
                name = _relative(item['path']).as_posix()
                if name.casefold() in folded:
                    return False
                folded.add(name.casefold())
                relative = 'files/' + name
                path = root / relative
                with _parents(path.parent):
                    data = _read(path, item['size'])
                if len(data) != item['size'] or _digest(data) != item['sha256']:
                    return False
                expected.add(relative)
            actual = set()
            for path in root.rglob('*'):
                _regular(path, path.is_dir())
                if path.is_file():
                    actual.add(path.relative_to(root).as_posix())
            return actual == expected
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def verify_delivery(project, descriptor, destination):
    """Compare the actual delivered tree with the retained, bound manifest."""
    try:
        if not verify(project, descriptor):
            return False
        stored = Path(project).absolute() / descriptor["location"]
        manifest = json.loads(_read(stored / "artifact-manifest.json", 10 * 1024 * 1024))
        destination = Path(destination).absolute()
        expected = set()
        with _parents(destination):
            for item in manifest["files"]:
                name = _relative(item["path"]).as_posix()
                target = destination / name
                with _parents(target.parent):
                    data = _read(target, item["size"])
                if len(data) != item["size"] or _digest(data) != item["sha256"]:
                    return False
                expected.add(name)
            actual = set()
            for path in destination.rglob("*"):
                _regular(path, path.is_dir())
                if path.is_file():
                    actual.add(path.relative_to(destination).as_posix())
            return actual == expected
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
