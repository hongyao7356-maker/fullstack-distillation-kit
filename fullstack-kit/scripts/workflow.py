"""Local stage orchestration. Approval is a local-owner trust boundary, not deployment."""
import argparse
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import re
import sqlite3
import sys
from check_gate import check_gate
from evidence_engine import connect, digest, file_lock, snapshot, valid_evidence
from security import redact,sanitize

POLICY=Path(__file__).resolve().parents[1]/'templates/phase_policy.json'


def policy():return json.loads(POLICY.read_text(encoding='utf-8'))


def validate_phase(phase):
    if not re.fullmatch(r'P[0-7]',phase):raise ValueError('Invalid phase')


def context_hash(project,phase):
    validate_phase(phase);project=Path(project).resolve()
    rows=[]
    try:
        with closing(connect(project,readonly=True)) as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM executions WHERE seq IN (SELECT MAX(seq) FROM executions GROUP BY check_id) AND phase=? ORDER BY check_id',(phase,))]
    except sqlite3.OperationalError:pass
    docs={name:digest((project/'.fullstack/docs'/name).read_bytes()) if (project/'.fullstack/docs'/name).is_file() else None for name in policy()[phase]['docs']}
    return digest(json.dumps({'source':snapshot(project),'policy':digest(POLICY.read_bytes()),'docs':docs,'evidence':rows},sort_keys=True).encode())


def events(project):
    path=Path(project)/'.fullstack/workflow.sqlite3'
    if not path.exists():return []
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            rows=db.execute('SELECT payload,previous,hash FROM events ORDER BY seq').fetchall()
        previous=''
        result=[]
        for payload,parent,hashed in rows:
            if parent!=previous or digest((parent+payload).encode())!=hashed:raise ValueError('Audit chain damaged')
            result.append(json.loads(payload));previous=hashed
        return result
    except (sqlite3.Error,ValueError):raise ValueError('Workflow audit damaged; refusing transition')


def append(project,event):
    path=Path(project)/'.fullstack/workflow.sqlite3'
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(sanitize(dict(event,at=dt.datetime.now(dt.timezone.utc).isoformat())),sort_keys=True)
    with closing(sqlite3.connect(path,timeout=30)) as db:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL,previous TEXT NOT NULL,hash TEXT NOT NULL)')
            last=db.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            previous=last[0] if last else ''
            db.execute('INSERT INTO events(payload,previous,hash) VALUES (?,?,?)',(payload,previous,digest((previous+payload).encode())))


def requirements(project,phase):
    validate_phase(phase);project=Path(project).resolve();rules=policy()
    issues=check_gate(project,phase,rules,require_config=True)
    try:
        profile=json.loads((project/'.fullstack/profile.json').read_text(encoding='utf-8'))
        if phase=='P0':
            if profile.get('owner_decisions_pending') or not profile.get('users') or not profile.get('goal') or profile.get('goal')=='TO_BE_CONFIRMED':
                issues.append('Business requirements unresolved')
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        issues.append('Invalid/missing project configuration: '+redact(str(exc)))
    return issues


def status(project):
    history=events(project);result={}
    for i in range(8):
        phase=f'P{i}';matches=[e for e in history if e.get('phase')==phase]
        if not matches:result[phase]='pending';continue
        latest=matches[-1]
        fresh=latest.get('context')==context_hash(project,phase) and not requirements(project,phase)
        if i and result[f'P{i-1}']!='complete':fresh=False
        result[phase]=latest['state'] if fresh else 'stale'
    return result


def prerequisites(project,phase):
    issues=requirements(project,phase)
    states=status(project)
    for i in range(int(phase[1])):
        if states[f'P{i}']!='complete':issues.append(f'Predecessor P{i} is not complete/current')
    if issues:raise ValueError('; '.join(issues))


def approve(project,phase,actor,expected_context,human_confirmed=False,production_authorized=False):
    project=Path(project).resolve();validate_phase(phase)
    if not human_confirmed or not actor.strip():raise ValueError('Explicit human confirmation required')
    if phase in {'P6','P7'} and not production_authorized:raise ValueError('Separate production authorization required')
    with file_lock(project/'.fullstack/locks/workflow.lock'):
        if context_hash(project,phase)!=expected_context:raise ValueError('Approval context changed')
        prerequisites(project,phase)
        if context_hash(project,phase)!=expected_context:raise ValueError('Approval context changed')
        append(project,{'phase':phase,'state':'approved','actor':redact(actor),'context':expected_context,
                        'production_authorized':production_authorized})


def advance(project,phase):
    project=Path(project).resolve();validate_phase(phase)
    with file_lock(project/'.fullstack/locks/workflow.lock'):
        context=context_hash(project,phase)
        prerequisites(project,phase)
        if status(project)[phase]!='approved':raise ValueError('Current human approval required')
        if context_hash(project,phase)!=context or requirements(project,phase):raise ValueError('Approval context changed')
        append(project,{'phase':phase,'state':'complete','context':context})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',default='.')
    p.add_argument('action',choices=['status','approve','advance'])
    p.add_argument('--phase',choices=[f'P{i}' for i in range(8)])
    p.add_argument('--actor',default='');p.add_argument('--authorize-production',action='store_true')
    a=p.parse_args();project=Path(a.project).resolve()
    try:
        if a.action=='status':print(json.dumps(status(project),indent=2));return 0
        if not a.phase:raise ValueError('--phase required')
        if a.action=='approve':
            if not sys.stdin.isatty():raise ValueError('Approval requires an interactive owner terminal')
            context=context_hash(project,a.phase)
            phrase='APPROVE '+a.phase+' '+context
            print('Review scope, checks and snapshot. This does not deploy anything.\nType: '+phrase)
            if input().strip()!=phrase:raise ValueError('Approval not confirmed')
            approve(project,a.phase,a.actor,context,True,a.authorize_production)
        else:advance(project,a.phase)
        print('OK:',a.action,a.phase);return 0
    except (ValueError,OSError,sqlite3.Error) as exc:
        print('BLOCKED:',redact(str(exc)));return 2

if __name__=='__main__':raise SystemExit(main())
