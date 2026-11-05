"""Explicit local environment measurement; trusted platform proof is separate."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import sysconfig
import tempfile

from command_executor import resolve
from security import SECRET_NAME, known_secrets

POLICY = 'controlled-environment-v2'
RESERVED = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP',
            'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'NODE_OPTIONS', 'NODE_PATH',
            'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT', 'LD_PRELOAD',
            'LD_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES', 'DYLD_LIBRARY_PATH'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tree_digest(root, excluded=()):
    """Measure installed bytes, including undeclared packages and native binaries."""
    root = Path(root)
    if not root.exists():
        return None
    rows = []
    for folder, dirs, files in os.walk(root, onerror=lambda error: (_ for _ in ()).throw(error)):
        dirs[:] = [name for name in dirs if name not in excluded]
        for name in sorted(dirs + files):
            item = Path(folder) / name
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise ValueError('Linked runtime dependency requires trusted platform proof')
            if item.is_file():
                rows.append((item.relative_to(root).as_posix(), file_hash(item)))
    return digest(sorted(rows))


def configured_keys(project, check_id):
    path = project / '.fullstack/checks.json'
    if not path.exists():
        return []
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Invalid environment configuration')
    matches = [item for items in config.values() if isinstance(items, list)
               for item in items if isinstance(item, dict) and item.get('check_id') == check_id]
    if len(matches) > 1:
        raise ValueError('Ambiguous environment configuration')
    settings = matches[0].get('environment', {}) if matches else {}
    if not isinstance(settings, dict) or set(settings) - {'keys', 'mode'}:
        raise ValueError('Invalid environment configuration')
    keys = settings.get('keys', [])
    if settings.get('mode', 'CURRENT_ENV_CHECK') not in {'CURRENT_ENV_CHECK', 'ATTESTED_BUILD_ARTIFACT'}:
        raise ValueError('Invalid environment evidence mode')
    if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
        raise ValueError('Environment keys must be a list')
    if len(set(key.upper() for key in keys)) != len(keys):
        raise ValueError('Duplicate environment keys')
    for key in keys:
        if (not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', key) or SECRET_NAME.search(key)
                or key in RESERVED or key.startswith(('PYTHON', 'NPM_', 'NODE_', 'LD_', 'DYLD_'))):
            raise ValueError('Secret or loader environment configuration rejected')
    return sorted(keys)


def capture_environment(project, command, check_id):
    project = Path(project).resolve()
    resolved = resolve(command, project)
    executable = Path(resolved[0]).resolve()
    name = Path(command[0]).stem.lower()
    if name not in {"python", "python3", "node", "npm", "npx"}:
        raise ValueError("Unsupported controlled toolchain")
    if name == "py" or (name.startswith("python") and executable != Path(sys.executable).resolve()):
        raise ValueError("Unbound Python installation")
    tool_paths = {Path(sys.executable).resolve(), executable}
    cli = Path(resolved[1]) if len(resolved) > 1 else None
    npm_root = None
    if cli is not None and cli.name in {'npm-cli.js', 'npx-cli.js'}:
        tool_paths.add(cli.resolve())
        npm_root = cli.parent.parent
    paths = [str(executable.parent), str(Path(sys.executable).resolve().parent)]
    # npm lifecycle scripts use the bound Node installation through PATH.
    if npm_root is not None:
        paths.append(str(npm_root.parent.parent))
    disabled_userconfig = Path(__file__).with_name('.npm-userconfig-disabled')
    if disabled_userconfig.exists():
        raise ValueError('Disabled npm user config path must be absent')
    env = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
           'PYTHONNOUSERSITE': '1', 'TEMP': tempfile.gettempdir(), 'TMP': tempfile.gettempdir(),
           'NPM_CONFIG_USERCONFIG': str(disabled_userconfig), 'NPM_CONFIG_GLOBALCONFIG': os.devnull,
           'NPM_CONFIG_UPDATE_NOTIFIER': 'false', 'NPM_CONFIG_AUDIT': 'false'}
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if not ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer)):
            raise OSError('Windows directory unavailable')
        windows = Path(buffer.value)
        env.update(SYSTEMROOT=str(windows), WINDIR=str(windows),
                   COMSPEC=str(windows/'System32/cmd.exe'), PATHEXT='.COM;.EXE;.BAT;.CMD')
        paths.extend([str(windows/'System32'), str(windows)])
        tool_paths.add(windows/'System32/cmd.exe')
    else:
        paths.extend(['/usr/bin', '/bin'])
    env['PATH'] = os.pathsep.join(dict.fromkeys(paths))
    selected = {}
    for key in configured_keys(project, check_id):
        value = os.environ.get(key)
        if value is not None:
            if any(secret in value for secret in known_secrets()) or len(value) > 4096:
                raise ValueError('Unsafe environment value')
            env[key] = value
        selected[key] = value
    # System-derived values are not user-configurable and contain no credentials.
    dependencies = {name: tree_digest(project/name) for name in ['node_modules', '.venv', 'venv']}
    toolchain = [{'path': str(path), 'sha256': file_hash(path)} for path in sorted(tool_paths)]
    if npm_root is not None:
        toolchain.append({'path': str(npm_root), 'tree_sha256': tree_digest(npm_root)})
    # Controlled workers and Python checks use -S, so implicit global and user
    # site-packages are unavailable. Bind the standard runtime they can load.
    runtime = Path(sysconfig.get_path("stdlib"))
    toolchain.append({"path": str(runtime), "tree_sha256": tree_digest(
        runtime, excluded=("site-packages", "dist-packages"))})
    libraries = Path(sys.base_prefix) / "DLLs"
    if libraries.exists():
        toolchain.append({"path": str(libraries), "tree_sha256": tree_digest(libraries)})
    for library in sorted(Path(sys.base_prefix).glob("*.dll")):
        toolchain.append({"path": str(library), "sha256": file_hash(library)})
    for archive in sorted(Path(sys.base_prefix).glob("python*.zip")):
        toolchain.append({"path": str(archive), "sha256": file_hash(archive)})
    # npm scripts can invoke the host interpreter without -S. Bind its global
    # packages too, and refuse startup hooks that introduce unmeasured roots.
    for site in sorted({Path(sysconfig.get_path("purelib")), Path(sysconfig.get_path("platlib"))}):
        for hook in [*site.glob("*.pth"), *site.glob("*customize.py")]:
            if any(line.strip() and not line.lstrip().startswith("#")
                   for line in hook.read_text(encoding="utf-8").splitlines()):
                raise ValueError("Uncontrolled Python startup hook")
        toolchain.append({"path": str(site), "tree_sha256": tree_digest(site)})
    manifest = {'schema_version': '1.3', 'environment_policy': POLICY, 'assurance': 'local_measurement',
                'configuration': selected, 'effective_environment': env,
                'toolchain': toolchain, 'installed_dependencies': dependencies,
                'direct_python_startup': 'no-site',
                'nested_python_startup': 'bound-global-site-packages'}
    manifest['digest'] = digest(manifest)
    return env, manifest


def environment_matches(project, command, check_id, manifest):
    try:
        return capture_environment(project, command, check_id)[1] == manifest
    except (OSError, ValueError, TypeError, KeyError):
        return False
