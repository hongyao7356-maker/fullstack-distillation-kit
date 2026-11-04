"""Shell-free command resolution and bounded process-tree lifetime."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


def resolve(command, project):
    exe = Path(command[0]).name.lower().removesuffix('.exe').removesuffix('.cmd')
    found = shutil.which(command[0])
    if not found: raise OSError('Executable unavailable')
    target = Path(found).resolve()
    if target.is_relative_to(project): raise ValueError('Project-local executables are not trusted tools')
    if exe in {'npm', 'npx'}:
        node = shutil.which('node')
        if not node: raise OSError('Node unavailable')
        candidates = [target.parent / 'node_modules/npm/bin' / (exe + '-cli.js'),
                      target.parent.parent / 'lib/node_modules/npm/bin' / (exe + '-cli.js')]
        if target.name == exe + '-cli.js': candidates.insert(0, target)
        cli = next((p.resolve() for p in candidates if p.is_file()), None)
        if cli is None: raise ValueError('Cannot resolve trusted npm JavaScript entry')
        return [str(Path(node).resolve()), str(cli), *command[1:]]
    if target.suffix.lower() in {'.cmd', '.bat', '.ps1'}:
        raise ValueError('Unsupported shell wrapper; explicit native executable required')
    if exe == 'node':
        script = Path(command[1]).resolve()
        if not script.is_file() or not script.is_relative_to(project) or script.suffix not in {'.js','.cjs','.mjs'}:
            raise ValueError('Node requires an existing in-project absolute script')
    return [str(target), *command[1:]]


class WindowsJob:
    def __init__(self):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k = k
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]; k.CreateJobObjectW.restype=wintypes.HANDLE
        k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        k.CloseHandle.argtypes=[wintypes.HANDLE]
        class Basic(ctypes.Structure):
            _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),
                      ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),
                      ('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),
                      ('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_=[('BasicLimitInformation',Basic),('IoInfo',ctypes.c_uint64*6),
                      ('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),
                      ('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
        self.handle=k.CreateJobObjectW(None,None)
        if not self.handle: raise OSError('Cannot create process job')
        info=Extended();info.BasicLimitInformation.LimitFlags=0x2000
        if not k.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            self.close();raise OSError('Cannot configure process job')

    def assign(self, process):
        if not self.k.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))):
            raise OSError('Cannot assign process job')

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle); self.handle=None


def execute(command, project, timeout):
    job=None; process=None
    try:
        resolved=resolve(command,project)
        if os.name=='nt': job=WindowsJob()
        env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('command_worker.py'))],
            cwd=project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            start_new_session=os.name!='nt')
        if job: job.assign(process)
        try:
            output,_=process.communicate((json.dumps(resolved)+'\n').encode(),timeout=timeout)
            return output.decode('utf-8',errors='replace'),process.returncode,False
        except subprocess.TimeoutExpired:
            if job: job.close()
            else: os.killpg(process.pid,signal.SIGKILL)
            output,_=process.communicate(timeout=10)
            return output.decode('utf-8',errors='replace')+'\n[TIMEOUT]',124,True
    except (OSError,ValueError,subprocess.SubprocessError):
        return '[COMMAND FAILED TO START: unavailable or unsafe executable]',127,False
    finally:
        if job: job.close()
        if process is not None:
            if os.name!='nt':
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            if process.poll() is None: process.kill()
            process.wait(timeout=10)
