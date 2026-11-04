"""Shared, conservative persistence policy. Never enumerate environment values in reports."""
import argparse
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

SECRET_NAME=re.compile(r'(?i)(password|passwd|secret|token|api[-_]?key|authorization|credential|private[-_]?key)')
PAIR=re.compile(r'''(?i)((?:password|passwd|secret|token|api[-_]?key|authorization|credential|private[-_]?key)[\w-]*["']?\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,"'}]+)''')


def known_secrets():
    return [v for k,v in os.environ.items() if SECRET_NAME.search(k) and v]


def redact(value, secrets=None):
    text=str(value)
    for secret in sorted(secrets if secrets is not None else known_secrets(), key=len, reverse=True):
        for variant in {secret,json.dumps(secret)[1:-1],quote(secret,safe='')}:
            if variant: text=text.replace(variant,'[REDACTED]')
    text=re.sub(r'(?i)(Bearer\s+)\S+',r'\1[REDACTED]',text)
    text=PAIR.sub(lambda m:m.group(1)+'[REDACTED]',text)
    text=re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@',r'\1[REDACTED]@',text)
    return text


def sanitize(value):
    if isinstance(value,str):return redact(value)
    if isinstance(value,list):return [sanitize(v) for v in value]
    if isinstance(value,dict):return {redact(k):sanitize(v) for k,v in value.items()}
    return value


def secure_command(command):
    known=known_secrets()
    reject=False; following=False; clean=[]
    for arg in command:
        sensitive=bool(SECRET_NAME.search(arg.split('=',1)[0])) and arg.startswith('-')
        if following:
            clean.append('[REDACTED]');following=False;reject=True;continue
        if sensitive:
            reject=True
            if '=' in arg: clean.append(arg.split('=',1)[0]+'=[REDACTED]')
            else: clean.append(arg);following=True
            continue
        sanitized=redact(arg,known)
        if sanitized!=arg:reject=True
        clean.append(sanitized)
    return clean,reject


def scan_history(root):
    """Return path/line/category only; preserve all historical bytes."""
    findings=[]
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.suffix.lower() not in {'.json','.log','.md'}:continue
        for number,line in enumerate(path.read_text(encoding='utf-8',errors='replace').splitlines(),1):
            if 'AUDIT_NOT_A_REAL_SECRET_' in line or 'SENTINEL_' in line:
                category='synthetic-test-marker'
            elif redact(line)!=line and '[REDACTED]' not in line:
                category='potential-sensitive-value-review-required'
            else:continue
            findings.append({'path':redact(path.relative_to(root).as_posix()),'line':number,'category':category})
    return findings


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scan',required=True);a=p.parse_args()
    print(json.dumps(scan_history(Path(a.scan)),ensure_ascii=False,indent=2))
