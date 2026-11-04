"""Private executor handshake: launch nothing before the parent owns the process tree."""
import json
import subprocess
import sys

if __name__ == '__main__':
    try:
        command = json.loads(sys.stdin.readline())
        result = subprocess.run(command, stdin=subprocess.DEVNULL, shell=False, check=False)
        raise SystemExit(result.returncode)
    except (OSError, ValueError):
        print('[COMMAND FAILED TO START]', flush=True)
        raise SystemExit(127)
