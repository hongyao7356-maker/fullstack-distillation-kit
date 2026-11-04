"""Read-only verification and explicit non-overwriting export."""
import sys
sys.dont_write_bytecode=True
import argparse
import ast
import datetime as dt
import json
from pathlib import Path
import shutil
import uuid
from verify_pack import verify as verify_pack
from security import redact,sanitize
from evidence_engine import digest

def verify(project):
    project=Path(project).resolve();kit=project/'fullstack-kit'
    errors=verify_pack(kit)
    for path in (kit/'scripts').glob('*.py'):
        try:ast.parse(path.read_text(encoding='utf-8-sig'),filename=path.name)
        except (SyntaxError,UnicodeError,OSError):errors.append('Invalid Python: '+path.name)
    profile=project/'.fullstack/profile.json'
    if profile.exists():
        try:
            if not isinstance(json.loads(profile.read_text(encoding='utf-8')),dict):errors.append('Profile must be object')
        except (ValueError,OSError):errors.append('Invalid profile JSON')
    manifest=project/'EXPORT_MANIFEST.json'
    if manifest.exists():
        try:
            values=json.loads(manifest.read_text(encoding='utf-8'))
            for name,expected in values.items():
                p=(project/name).resolve()
                if not p.is_relative_to(project) or digest(p.read_bytes())!=expected:errors.append('Export mismatch: '+name)
        except (ValueError,OSError,AttributeError):errors.append('Invalid export manifest')
    return {'schema_version':2,'operation':'verify','status':'FAIL' if errors else 'PASS','scope':'tool_structure','errors':errors,'business_acceptance':'NOT_EVALUATED','runtime_tests':'NOT_EXECUTED_BY_READ_ONLY_VERIFIER'}

def export(project,destination):
    project=Path(project).resolve();target=Path(destination).resolve()
    if verify(project)['errors']:raise ValueError('Source verification failed')
    if target.exists():raise ValueError('Destination exists; export never overwrites')
    if target==project or project.is_relative_to(target) or any(target.is_relative_to(project/name) for name in ['fullstack-kit','.agents']):raise ValueError('Invalid export destination')
    target.mkdir(parents=True,exist_ok=False)
    for name in ['fullstack-kit','.agents/skills']:
        shutil.copytree(project/name,target/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    entry=project/'work/verify_delivery.py'
    if entry.is_file():
        (target/'work').mkdir();shutil.copyfile(entry,target/'work/verify_delivery.py')
    manifest={p.relative_to(target).as_posix():digest(p.read_bytes()) for p in target.rglob('*') if p.is_file()}
    (target/'EXPORT_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return {'operation':'export','status':'PASS','destination':str(target),'files':len(manifest)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',nargs='?',choices=['verify','export'],default='verify')
    p.add_argument('--project',default='.')
    p.add_argument('--destination')
    p.add_argument('--report-root',help='Optional explicit unique report directory; omitted verify is read-only')
    a=p.parse_args()
    try:
        if a.operation=='export':
            if not a.destination:raise ValueError('Export requires --destination')
            result=export(a.project,a.destination)
        else:result=verify(a.project)
        text=json.dumps(sanitize(result),ensure_ascii=False,indent=2)
        if a.report_root:
            directory=Path(a.report_root)/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
            directory.mkdir(parents=True,exist_ok=False)
            (directory/'verification.json').write_text(text+'\n',encoding='utf-8')
        print(text)
        return 0 if result['status']=='PASS' else 2
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print('ERROR:',redact(str(exc)));return 2

if __name__=='__main__':raise SystemExit(main())
