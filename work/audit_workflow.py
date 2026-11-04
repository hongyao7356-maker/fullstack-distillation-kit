"""Review the installed workflow in isolated fixtures, without fixing package files."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TAG = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
AREA = ROOT / 'work' / ('workflow-audit-' + TAG)
AREA.mkdir()
LOGS = ROOT / '.fullstack/checks' / ('workflow-audit-' + TAG)
LOGS.mkdir()
PY = sys.executable
SCRIPTS = ROOT / 'fullstack-kit/scripts'
sys.path.insert(0, str(SCRIPTS))
from check_gate import check_gate, evidence_ok
from run_check import allowed_command

ENV = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
COMMANDS = []
CHECKS = []
FINDINGS = []
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
protected = list((ROOT / 'fullstack-kit').rglob('*')) + list((ROOT / '.agents').rglob('*'))
protected += list((ROOT / 'outputs').glob('*')) + list((ROOT / '.fullstack/docs').glob('*'))
protected += list((ROOT / '.fullstack/reviews').glob('*')) + [ROOT / '.fullstack/profile.json']
BEFORE = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected if p.is_file() and '__pycache__' not in p.parts}


def command(label, args, cwd=ROOT):
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding='utf-8', errors='replace', timeout=90, check=False)
    log = LOGS / (f'{len(COMMANDS):02}-' + label + '.log')
    log.write_text(result.stdout, encoding='utf-8')
    record = dict(label=label, command=[str(arg) for arg in args], cwd=str(cwd),
                  exit_code=result.returncode, stdout=result.stdout,
                  log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log))
    COMMANDS.append(record)
    print(f"COMMAND {label}: exit={result.returncode}; log={record['log']}", flush=True)
    return record


def check(label, condition, detail=''):
    CHECKS.append(dict(label=label, passed=bool(condition), detail=detail))
    print(('PASS ' if condition else 'UNEXPECTED_FAILURE ') + label + ': ' + detail, flush=True)


def fixture(name):
    target = AREA / name
    target.mkdir()
    result = command(name + '-init', [PY, SCRIPTS / 'init_project.py', '--project', target, '--profile', 'generic'])
    assert result['exit_code'] == 0
    return target


def gate(label, project, phase):
    return command(label, [PY, SCRIPTS / 'check_gate.py', '--project', project, '--phase', phase])


def write_test(project, passing=True, sleep=False):
    tests = project / 'cases'
    tests.mkdir(exist_ok=True)
    code = 'import unittest\n'
    if sleep:
        code += 'import time\ntime.sleep(3)\n'
    code += 'class AuditFixture(unittest.TestCase):\n    def test_audit(self):\n        self.assertTrue(' + str(passing) + ')\n'
    (tests / 'test_audit.py').write_text(code, encoding='utf-8')


def run_test(label, project, timeout=20, extra=None):
    prior = set((project / '.fullstack/evidence').glob('*.json'))
    args = [PY, SCRIPTS / 'run_check.py', '--project', project, '--phase', 'P4', '--kind', 'test',
            '--timeout', str(timeout), '--', PY, '-m', 'unittest', 'discover', '-s', 'cases', '-v']
    if extra:
        args += extra
    result = command(label, args)
    added = set((project / '.fullstack/evidence').glob('*.json')) - prior
    assert len(added) == 1
    path = added.pop()
    receipt = json.loads(path.read_text(encoding='utf-8'))
    log = project / receipt['log']
    print(log.read_text(encoding='utf-8'), flush=True)
    return result, receipt, path


def finding(identifier, severity, title, location, reproduction, observed, recommendation):
    FINDINGS.append(dict(id=identifier, severity=severity, title=title, location=location,
                         reproduction=reproduction, observed=observed, recommendation=recommendation))
    print(f'FINDING {identifier} {severity}: {title}', flush=True)


for label, args in [
    ('package', [PY, SCRIPTS / 'verify_pack.py']),
    ('cards', [PY, SCRIPTS / 'validate_cards.py']),
    ('unit-tests', [PY, '-m', 'unittest', 'discover', '-s', 'fullstack-kit/tests', '-v']),
    ('syntax', [PY, '-m', 'compileall', '-q', 'fullstack-kit/scripts', 'fullstack-kit/tests']),
]:
    result = command(label, args)
    check(label, result['exit_code'] == 0, result['stdout'].strip())
current = gate('current-P0', ROOT, 'P0')
check('Current P0 static gate', current['exit_code'] == 0)
result = command('current-init-again', [PY, SCRIPTS / 'init_project.py', '--project', ROOT, '--profile', 'generic'])
check('Current initialization preserves profile', result['exit_code'] == 0 and sha(ROOT / '.fullstack/profile.json') == BEFORE['.fullstack/profile.json'])

fresh = fixture('fresh')
check('Fresh initialization creates required workspace', all((fresh / '.fullstack' / name).is_dir() for name in ['docs', 'checks', 'evidence', 'reviews', 'sources', 'cards']))
for phase in [f'P{i}' for i in range(8)]:
    result = gate('missing-docs-' + phase, fresh, phase)
    check(phase + ' blocks missing deliverables', result['exit_code'] == 2 and 'BLOCKED' in result['stdout'])
digital = AREA / 'digital'
digital.mkdir()
result = command('digital-profile', [PY, SCRIPTS / 'init_project.py', '--project', digital, '--profile', 'digital-employee'])
check('Digital profile initialization', result['exit_code'] == 0 and (digital / '.fullstack/profile.json').is_file())

flow = fixture('test-flow')
write_test(flow)
result, receipt, receipt_path = run_test('record-success', flow)
check('Successful test produces valid receipt', result['exit_code'] == 0 and receipt['exit_code'] == 0 and evidence_ok(flow, 'P4', 'test'))
log_path = flow / receipt['log']
check('Test log SHA256 matches receipt', sha(log_path) == receipt['log_sha256'])
log_path.write_text(log_path.read_text(encoding='utf-8') + '\nAUDIT_TAMPER\n', encoding='utf-8')
check('Tampered log rejected', not evidence_ok(flow, 'P4', 'test'))

stale = fixture('stale-receipt')
write_test(stale, True)
first, good, good_path = run_test('stale-first-pass', stale)
write_test(stale, False)
failed, bad, bad_path = run_test('stale-latest-failure', stale)
assert first['exit_code'] == 0 and failed['exit_code'] == 2 and bad['exit_code'] == 1
accepted = evidence_ok(stale, 'P4', 'test')
check('Latest failed test recorded accurately', bad['exit_code'] == 1 and 'FAILED' in (stale / bad['log']).read_text(encoding='utf-8'))
lint_fixture = command('stale-syntax-check-receipt', [PY, SCRIPTS / 'run_check.py', '--project', stale,
                       '--phase', 'P4', '--kind', 'lint', '--', PY, '-m', 'compileall', '-q', 'cases'])
assert lint_fixture['exit_code'] == 0
(stale / '.fullstack/docs/04_test_plan.md').write_text('# ISOLATED GATE COMPOSITION FIXTURE\n' +
    'Syntax compilation is used only to exercise receipt composition, not to attest product lint quality. ' * 4, encoding='utf-8')
stale_gate = gate('stale-full-P4-gate', stale, 'P4')
if accepted:
    finding('F01', 'HIGH', '新测试失败后仍认可旧成功收据', 'fullstack-kit/scripts/check_gate.py:23-33',
            '在隔离stale-receipt目录运行一次成功测试，再把同一测试改为失败并再次记录，随后调用evidence_ok(project,"P4","test")。',
            '首次退出0；最新测试退出1、runner退出2；evidence_ok仍返回True。隔离目录补齐门禁文档和语法检查lint收据后，完整P4门禁也退出' + str(stale_gate['exit_code']) + '。语法检查仅用于门禁组合复现，不作为业务lint验收。未比较最新执行记录，也未绑定源码快照。',
            '按检查身份选取最新收据，最新失败或超时须阻断；将收据绑定到受检源码快照，源码变化后要求重新执行。')

timed = fixture('timeout')
write_test(timed, sleep=True)
result, receipt, _ = run_test('timeout-record', timed, timeout=1)
check('Timeout blocks evidence and records 124', result['exit_code'] == 2 and receipt['exit_code'] == 124 and receipt['timed_out'] and not evidence_ok(timed, 'P4', 'test'))
check('Dangerous direct commands rejected by guard', all(not allowed_command(cmd) for cmd in [['git', 'reset', '--hard'], ['npm', 'run', 'deploy'], ['powershell', '-c', 'echo audit']]))

npm_fixture = fixture('npm')
(npm_fixture / 'audit.js').write_text('console.log("AUDIT_LOCAL_NPM_OK");\n', encoding='utf-8')
(npm_fixture / 'package.json').write_text(json.dumps({'name': 'isolated-audit-fixture', 'version': '1.0.0', 'private': True, 'scripts': {'test': 'node audit.js'}}), encoding='utf-8')
npm_attempt = command('npm-via-runner', [PY, SCRIPTS / 'run_check.py', '--project', npm_fixture, '--phase', 'P4', '--kind', 'test', '--', 'npm', 'run', 'test'])
npm_receipts = list((npm_fixture / '.fullstack/evidence').glob('*.json'))
npm_receipt = json.loads(npm_receipts[0].read_text(encoding='utf-8'))
npm_log = (npm_fixture / npm_receipt['log']).read_text(encoding='utf-8')
print('NPM_RUNNER_LOG:', npm_log, flush=True)
# A trusted, local JS entry proves the fixture itself works, without network or installs.
node_attempt = command('npm-fixture-node-direct', ['node', 'audit.js'], cwd=npm_fixture)
check('Local JavaScript fixture is runnable', node_attempt['exit_code'] == 0 and 'AUDIT_LOCAL_NPM_OK' in node_attempt['stdout'])
npm_cli_path = Path(shutil.which('node')).parent / 'node_modules/npm/bin/npm-cli.js'
npm_cli_attempt = command('npm-cli-direct-control', ['node', npm_cli_path, 'run', 'test'], cwd=npm_fixture)
check('Installed npm executes the same local package script', npm_cli_attempt['exit_code'] == 0 and 'AUDIT_LOCAL_NPM_OK' in npm_cli_attempt['stdout'])
if npm_attempt['exit_code'] != 0 and npm_receipt['exit_code'] == 127 and node_attempt['exit_code'] == 0:
    finding('F02', 'HIGH', 'Windows下npm检查无法经runner启动', 'fullstack-kit/scripts/run_check.py:22-23,35-38,56-68',
            '隔离npm目录只含本地audit.js及test脚本，执行run_check.py --project <目录> --phase P4 --kind test -- npm run test；另用node audit.js验证同一代码。',
            'Node本地脚本及已安装npm的node npm-cli.js run test对照均退出0，runner退出2，收据退出127；原始日志：' + npm_log.strip(),
            '在Windows显式解析可信npm/npx入口并安全启动；同时补充Windows下npm run test/build的集成回归检查，不能仅测allowed_command返回值。')
else:
    check('Npm runner execution', npm_attempt['exit_code'] == 0, npm_log)

invalid = AREA / 'invalid-cards'
invalid.mkdir()
(invalid / 'list.json').write_text('[]\n', encoding='utf-8')
result = command('invalid-card-root', [PY, SCRIPTS / 'validate_cards.py', '--cards', invalid])
if 'Traceback' in result['stdout']:
    finding('F03', 'MEDIUM', '不合格式的JSON卡片导致校验器异常退出', 'fullstack-kit/scripts/validate_cards.py:46-52',
            '在隔离卡片目录写入合法JSON数组[]，执行validate_cards.py --cards <目录>。',
            f"退出{result['exit_code']}，出现AttributeError traceback；没有返回正常的结构诊断。",
            '先验证JSON根节点是对象、字段类型符合schema，再执行字典和集合操作；错误卡片应报告文件路径与字段错误并退出2。')

secret_fixture = fixture('sentinel-redaction')
write_test(secret_fixture)
marker = 'AUDIT_NOT_A_REAL_SECRET_' + uuid.uuid4().hex
result, receipt, receipt_path = run_test('synthetic-secret-argument', secret_fixture, extra=['--api-key=' + marker])
raw_log = (secret_fixture / receipt['log']).read_text(encoding='utf-8')
log_redacted = marker not in raw_log
receipt_leaks = marker in receipt_path.read_text(encoding='utf-8')
check('Synthetic token removed from command output log', log_redacted)
if receipt_leaks and log_redacted:
    finding('F04', 'MEDIUM', '命令参数中的敏感值仍原样写入JSON收据', 'fullstack-kit/scripts/run_check.py:70-77',
            '仅以随机无效哨兵值作为--api-key=<哨兵>参数运行隔离测试；比较日志与收据，不使用真实凭据。',
            '文本日志已脱敏，但record.command保留完整哨兵参数。收据被共享或入库时可能泄露通过参数传入的真实凭据。',
            '持久化前对命令参数应用敏感字段脱敏，优先通过安全环境变量传参；增加日志和元数据一致的脱敏回归检查。')

clone = AREA / 'legacy-rerun'
clone.mkdir()
for directory in ['fullstack-kit', '.agents', '.fullstack', 'outputs']:
    shutil.copytree(ROOT / directory, clone / directory, ignore=shutil.ignore_patterns('__pycache__', 'workflow-audit-*'))
shutil.copyfile(ROOT / 'FULLSTACK_DISTILL_使用说明.md', clone / 'FULLSTACK_DISTILL_使用说明.md')
(clone / 'work').mkdir()
shutil.copyfile(ROOT / 'work/verify_delivery.py', clone / 'work/verify_delivery.py')
result = command('legacy-verifier-rerun', [PY, clone / 'work/verify_delivery.py'], cwd=clone)
if result['exit_code'] != 0 and 'Export has no pre-existing conflict' in result['stdout']:
    finding('F05', 'MEDIUM', '首次交付的辅助验收脚本不能重复运行', 'work/verify_delivery.py:109-112,179-180,192',
            '把当前工具包、画像、文档和已存在的outputs复制到隔离legacy-rerun目录，再执行其中work/verify_delivery.py。',
            '前置包检查及测试执行成功后，因为已有导出文件触发AssertionError而退出1。绝对Downloads路径也是迁移依赖。',
            '将验证和首次导出分离：验证模式只读核对既有结果；报告采用唯一运行目录，重复检查不应因已有交付而失败。')

new_project = fixture('static-P0')
for filename in ['00_requirements.md', '00_acceptance.md']:
    (new_project / '.fullstack/docs' / filename).write_text('# ISOLATED AUDIT FIXTURE\n' + 'This synthetic text is only for testing static gate boundaries. ' * 5, encoding='utf-8')
result = gate('static-P0-with-pending-profile', new_project, 'P0')
check('Documented static-only P0 behavior reproduced', result['exit_code'] == 0,
      'Generic profile still has unresolved fields; length-only documents are accepted. This is a documented limitation, not business approval.')

check('All original package, profile, docs and outputs remain unchanged', all((ROOT / name).is_file() and sha(ROOT / name) == value for name, value in BEFORE.items()))
for record in COMMANDS:
    assert sha(ROOT / record['log']) == record['log_sha256']

failed_checks = [item for item in CHECKS if not item['passed']]
summary = {'run_id': TAG, 'created_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'scope': 'Isolated diagnostic workflow audit; no business phase advanced',
           'checks': CHECKS, 'unexpected_failures': failed_checks, 'findings': FINDINGS,
           'commands': COMMANDS, 'protected_originals': BEFORE,
           'fixture_root': AREA.relative_to(ROOT).as_posix(),
           'limitations': ['No business implementation supplied', 'No live external services or deployments tested',
                           'No fresh Codex session launched to test automatic skill discovery',
                           'Review only; original package files not fixed']}
json_path = ROOT / 'outputs' / ('工作流审查证据_' + TAG + '.json')
json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
table = '\n'.join(f"| {r['label']} | {r['exit_code']} | `{r['log']}` |" for r in COMMANDS)
details = '\n\n'.join(f"### {f['id']} / {f['severity']}：{f['title']}\n\n定位：`{f['location']}`。\n\n复现：{f['reproduction']}\n\n实测：{f['observed']}\n\n建议：{f['recommendation']}" for f in FINDINGS)
report = f'''# 工作区工作流运行审查

日期：2026-11-05（Asia/Shanghai）；运行编号：{TAG}。

结论：**当前Python工具包的初始化、现有自测、日志收据及P0静态门禁可以运行；整套流程尚不能判定为可靠闭环。** 实际复现{len(FINDINGS)}项问题，其中{sum(f['severity']=='HIGH' for f in FINDINGS)}项HIGH。此次是审查，没有修改原包脚本或现有交付，也没有进入任何业务阶段。

## 通过的检查

包结构、2张示例卡结构、原有10项自测和Python语法编译均退出0。当前P0静态门禁退出0；重复初始化保留当前画像。generic与digital-employee均能在隔离目录初始化。P0—P7在各自资料缺失时均退出2；真实隔离测试能生成退出码与哈希收据；篡改日志被拒绝；超时记录124并阻断；常见直接危险命令被拒绝。

以上是实际工具检查。隔离目录中的合成文档、测试及收据仅用于验证工具本身，不是当前项目完成P1—P7的证据，也不代表存在可运行的业务系统。

## 按严重程度排序的发现

{details}

## 流程边界

P0只验证最低文档规则，不读取业务未决决策；隔离测试确认即使画像仍是草稿、文档仅为一般性长文本，也会返回READY_FOR_HUMAN_REVIEW。这与包中声明的静态边界一致。生命周期Skill规定的业务判断、阶段顺序和人工授权依赖执行者遵守，当前没有独立自动编排器来保证这些动作。

本次直接读取并应用fullstack-review，按systematic-debugging复现原因，并按verification-before-completion执行检查。未开启独立代理或新Codex会话，无法确认新会话技能自动发现。没有业务源码，业务鉴权、注入、并发、恢复、真实数据库和部署均未验证；Git仍无仓库。示例卡真实性与外部研究未复核。

## 命令与证据

共执行{len(COMMANDS)}条本地命令，诊断断言{len(CHECKS)}项，其中意外失败{len(failed_checks)}项。特意构造的失败、超时、缺失资料和旧脚本重跑均保留实际非零退出码；这些不计作检查工具未执行。

| 操作 | 实际退出码 | 完整日志 |
|---|---|---|
{table}

详细命令参数、工作目录、完整输出、日志哈希、问题复现和原文件哈希见同名审查证据JSON。隔离复现文件保留于`{AREA.relative_to(ROOT).as_posix()}`。新增审查报告镜像保存于`.fullstack/reviews/`；旧报告不覆盖。

## 后续优先级

优先修复F01的过期成功记录误放行及F02的Windows npm启动；再处理F03输入校验、F04收据脱敏和F05重复验收。修复后应以本次隔离复现作为回归用例重跑。HIGH问题未处理前，不建议把此流程当作自动放行保障。
'''
report_path = ROOT / 'outputs' / ('工作流审查报告_' + TAG + '.md')
report_path.write_text(report, encoding='utf-8')
review_path = ROOT / '.fullstack/reviews' / report_path.name
review_path.write_text(report, encoding='utf-8')
assert report_path.read_bytes() == review_path.read_bytes()
assert json.loads(json_path.read_text(encoding='utf-8'))['run_id'] == TAG
print('REPORT:', str(report_path), flush=True)
print('EVIDENCE:', str(json_path), flush=True)
print(f'AUDIT_COMPLETE: {len(FINDINGS)} findings; {len(CHECKS)} checks; {len(failed_checks)} unexpected failures', flush=True)
raise SystemExit(1 if failed_checks else 0)
