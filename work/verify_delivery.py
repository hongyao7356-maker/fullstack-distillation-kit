"""Local delivery checks; record real commands without changing packaged code."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path('C:/Users/hp/Downloads/Codex_%E5%85%A8%E6%A0%88%E5%B7%A5%E7%A8%8B%E8%92%B8%E9%A6%8F%E6%95%99%E7%A8%8B%E5%8C%85_v1.0 (1).zip')
INSTRUCTIONS = Path('C:/Users/hp/Downloads/FULLSTACK_DISTILL_使用说明.md')
STAMP = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
RECORDS = []
CHECKS = []
ENV = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    CHECKS.append(message)
    print('PASS:', message, flush=True)


def run(label, args, expected=0):
    result = subprocess.run(args, cwd=ROOT, env=ENV, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                            timeout=120, check=False)
    print('COMMAND:', subprocess.list2cmdline(args), flush=True)
    print(result.stdout, end='' if result.stdout.endswith('\n') else '\n', flush=True)
    print('EXIT_CODE:', result.returncode, flush=True)
    log = ROOT / '.fullstack' / 'checks' / f'delivery-{STAMP}-{label}.log'
    with log.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(result.stdout)
    record = dict(label=label, command=args, exit_code=result.returncode,
                  expected_exit_code=expected, log=log.relative_to(ROOT).as_posix(),
                  log_sha256=digest(log), run_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    RECORDS.append(record)
    require(result.returncode == expected, f'{label}: actual exit {result.returncode}, expected {expected}')
    return result


with zipfile.ZipFile(ARCHIVE) as package:
    entries = [entry for entry in package.infolist() if not entry.is_dir()]
    require(len(entries) == 35, 'ZIP contains 35 files')
    manifest = []
    for entry in entries:
        path = (ROOT / entry.filename).resolve()
        require(path.is_relative_to(ROOT), f'Archive path contained: {entry.filename}')
        actual = path.read_bytes()
        require(actual == package.read(entry), f'Installed bytes match ZIP: {entry.filename}')
        manifest.append(dict(path=entry.filename, sha256=hashlib.sha256(actual).hexdigest()))
require((ROOT / 'FULLSTACK_DISTILL_使用说明.md').read_bytes() == INSTRUCTIONS.read_bytes(),
        'Standalone instructions equal packaged instructions')

profile_path = ROOT / '.fullstack' / 'profile.json'
profile = json.loads(profile_path.read_text(encoding='utf-8'))
require(profile['production_deploy_authorized'] is False and profile['external_write_authorized'] is False,
        'Profile retains false production and external-write authorization')
require(len(profile['owner_decisions_pending']) == 5 and profile['users'] == [],
        'Profile records five pending business decisions and no invented users')
require('TO_BE_CONFIRMED' not in profile_path.read_text(encoding='utf-8'),
        'Profile contains observed facts and explicit unresolved decisions instead of template placeholders')

req = (ROOT / '.fullstack/docs/00_requirements.md').read_text(encoding='utf-8', errors='strict')
acc = (ROOT / '.fullstack/docs/00_acceptance.md').read_text(encoding='utf-8', errors='strict')
require(all(f'R{i:02}' in req and f'AC{i:02}' in req and f'AC{i:02} / R{i:02}' in acc for i in range(1, 7)),
        'All six requirements map to executable acceptance criteria')
require(all(name in req for name in ['事实与依据', '角色、事件与边界', '非目标', '风险与反例', '未决业务']),
        'Requirements include facts, roles, exclusions, risks and unresolved decisions')
require(all(name in acc for name in ['Given / When / Then', '可复现命令', '负面与幂等', '业务P0的后续放行条件']),
        'Acceptance document includes scenarios, actual commands, negative checks and business gate limits')

python = sys.executable
run('python-version', [python, '--version'])
run('git-status', ['git', 'status', '--short', '--branch'], expected=128)
run('verify-pack', [python, 'fullstack-kit/scripts/verify_pack.py'])
run('validate-cards', [python, 'fullstack-kit/scripts/validate_cards.py'])
before = digest(profile_path)
run('init-idempotence', [python, 'fullstack-kit/scripts/init_project.py', '--project', '.', '--profile', 'generic'])
require(digest(profile_path) == before, 'Repeated initialization preserves the actual completed profile bytes')
run('unit-tests', [python, 'fullstack-kit/scripts/run_check.py', '--project', '.', '--phase', 'P0', '--kind', 'test',
                   '--', python, '-m', 'unittest', 'discover', '-s', 'fullstack-kit/tests', '-v'])
receipts = []
for path in (ROOT / '.fullstack/evidence').glob('P0-test-*.json'):
    receipt = json.loads(path.read_text(encoding='utf-8'))
    log = ROOT / receipt['log']
    require(receipt['exit_code'] == 0 and receipt['timed_out'] is False and digest(log) == receipt['log_sha256'],
            f'Actual test receipt and log hash valid: {path.name}')
    full_log = log.read_text(encoding='utf-8')
    print('FULL TEST LOG:', full_log, flush=True)
    require('Ran 10 tests' in full_log and '\nOK\n' in full_log, 'Full test log confirms 10 tests, zero failures')
    receipts.append(dict(receipt_file=path.relative_to(ROOT).as_posix(), **receipt))
require(bool(receipts), 'At least one real P0 unit-test receipt exists')
run('compile-python', [python, '-m', 'compileall', '-q', 'fullstack-kit/scripts', 'fullstack-kit/tests'])
run('gate-P0', [python, 'fullstack-kit/scripts/check_gate.py', '--project', '.', '--phase', 'P0'])

out = ROOT / 'outputs'
exports = {'00_需求与现状.md': ROOT / '.fullstack/docs/00_requirements.md',
           '00_验收标准.md': ROOT / '.fullstack/docs/00_acceptance.md',
           '项目画像.json': profile_path}
for name, source in exports.items():
    target = out / name
    require(not target.exists(), f'Export has no pre-existing conflict: {name}')
    shutil.copyfile(source, target)
    require(target.read_bytes() == source.read_bytes(), f'Export opens as identical UTF-8 source: {name}')
    target.read_text(encoding='utf-8', errors='strict')

table = '\n'.join(f"| {record['label']} | `{subprocess.list2cmdline(record['command'])}` | {record['exit_code']} |"
                  for record in RECORDS)
report = f'''# 全栈工程方法包：首次执行与验收报告

执行日期：2026-11-05（Asia/Shanghai）。最终检查时间：{dt.datetime.now(dt.timezone.utc).isoformat()}。

## 结论

已在 `C:/Users/hp/Documents/Codex/2026-11-05/du` 安装项目级方法包并整理P0资料。35个包文件均与输入ZIP逐字节一致，没有覆盖既有项目文件。包结构检查、2张示例卡结构校验、10项工具包测试、Python语法编译及当前画像重复初始化检查通过。

P0静态门禁结果为 **READY_FOR_HUMAN_REVIEW**，退出码0。它只表示两份文档通过包内最低规则。**实际业务需求仍未确认，不宣称业务P0完成，不进入P1。**

## 修改文件

- 新增ZIP原样内容35个文件：`.agents/skills/`的3个项目技能、`fullstack-kit/`及包内使用说明。
- 初始化`.fullstack/`证据工作区；补齐`.fullstack/profile.json`的事实、环境、约束、风险、5项未决决策，保留两项外部/部署授权为false。
- 新增`.fullstack/docs/00_requirements.md`、`.fullstack/docs/00_acceptance.md`，共6项需求与6项可执行验收标准。
- 新增真实命令日志、单元测试收据、验证辅助脚本和本交付目录中的副本；未修改原包脚本、测试、来源登记或示例卡。
- Python运行生成了正常的`__pycache__`缓存；没有业务源码、Git初始化、全局技能安装或配置修改。

安装前当前目录只有空的work、outputs目录，没有既有项目文件需要备份。原始ZIP保留于用户下载目录，SHA256：`{digest(ARCHIVE)}`。

## 最终实际命令与退出码

| 检查 | 命令 | 实际退出码 |
|---|---|---|
{table}

Git退出128是已记录的环境缺口，含义为此目录不是Git仓库；没有把它算作测试成功。`py`启动器不存在，使用说明允许的`python`替代方式。初始化首次执行退出0；首次文档生成前P0门禁输出BLOCKED并指出两份文档缺失；上表是最终改动后的重新验收结果。

每条命令的完整输出、退出码和SHA256可在`.fullstack/checks/delivery-{STAMP}-*.log`及`验收证据.json`中定位；工具包的run_check另生成`.fullstack/evidence/P0-test-*.json`与对应完整测试日志。所有命令均实际运行，未使用模拟日志。

## 验收覆盖

- AC01：安装路径范围、无覆盖、35个文件原样一致，且两份使用说明内容一致。
- AC02：结构/卡片/10项自测/语法编译退出0；卡片的真实性不在结构校验范围。
- AC03：画像严格JSON可读；授权保持false；当前业务未知如实记录；重复初始化后画像哈希不变。
- AC04：两份Markdown以UTF-8打开、内容已逐节阅读；6项需求均映射验收，包含范围、反例、风险、责任与未决问题。没有PDF/Office排版交付，未声称图形渲染检查。
- AC05：最终P0门禁退出0，明确只达到静态人工审阅状态。
- AC06：操作停在P0；没有外部研究、元数据采集、付费、部署、数据库修改、客户触达或删除。

10项自测包含缺文档阻断、占位符拒绝、篡改日志拒绝、路径越界拒绝、危险命令拒绝、重复初始化和无效卡片等负面场景。它们针对工具包，不能替代业务负面测试。

## 审查结果、缺口与限制

本次读取并按fullstack-lifecycle执行，使用verification-before-completion进行交付验收；同时以fullstack-review的审查视角核对范围和证据，没有声称由另一名代理独立审查。

最高优先缺口：没有实际业务仓库与业务目标。因此不能验证业务构建、API、权限、并发、失败恢复、业务端到端流程、生产运行或上线条件。没有Git历史，无法提供提交差异与Git回退证据。

当前3个项目技能文件的内容与格式检查通过，本次已直接读取相关流程；**新会话自动发现/加载未验证**。未安装到全局技能目录。若目标是另一现有项目，需要在该项目重新检查约束与安全安装，不能把本目录的结果套用过去。

未执行专家资料深度研究或外部网址复核；示例卡中的verified和来源登记中的entry_verified是原包自带标记，不代表本次已独立核验。研究队列仍未完成。

## 进入P1前需由用户作出的决策

1. 确定实际项目根目录：沿用当前空工作区新建，或提供现有业务仓库。
2. 确定主要用户、首版核心场景、必须功能和非目标。
3. 确定数据来源、敏感数据、角色及认证授权要求。
4. 确定运行环境、外部系统、预算、性能与可用性目标。
5. 审阅P0文档与上述决策，再决定是否继续P1。

上述未决项保持未决，不会自动变成开发任务。生产部署、外部写入、数据变更、付费、客户触达和删除仍需另行明确授权。
'''
report_path = out / '首次执行与验收报告.md'
with report_path.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(report)
require(report_path.read_text(encoding='utf-8') == report, 'Final report reopens with complete UTF-8 content')
for record in RECORDS:
    require(digest(ROOT / record['log']) == record['log_sha256'], f"Final log integrity: {record['label']}")
evidence = dict(root=str(ROOT), verified_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                archive_sha256=digest(ARCHIVE), package_manifest=manifest, commands=RECORDS,
                test_receipts=receipts, acceptance_checks=CHECKS,
                outputs={p.name: digest(p) for p in out.iterdir() if p.is_file()},
                static_gate='READY_FOR_HUMAN_REVIEW', business_requirements='PENDING_OWNER_DECISIONS',
                limitations=['No business project supplied', 'Not a Git repository',
                             'No external source research', 'Future-session skill discovery unverified'])
with (out / '验收证据.json').open('x', encoding='utf-8') as stream:
    json.dump(evidence, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
json.loads((out / '验收证据.json').read_text(encoding='utf-8'))
print('DELIVERY_VERIFICATION_OK; business P0 pending owner decisions; P1 not started', flush=True)
