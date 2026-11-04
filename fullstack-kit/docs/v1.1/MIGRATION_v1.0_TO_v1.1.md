# v1.0 → v1.1 迁移

## 保护现有数据

先保留当前源码、.fullstack和原始审查记录。只替换工具包脚本与相关新增模块/测试；不要覆盖现有AGENTS.md、Skill、profile、源码或证据。当前工作区已完成受限源码Git基线，历史资料未提交。导出的新包用于新目录或人工对比迁移，不应整包覆盖已有项目。

## 兼容入口

```powershell
python fullstack-kit/scripts/init_project.py --project . --profile generic
python fullstack-kit/scripts/verify_pack.py
python -B work/verify_delivery.py verify --project .
python -B work/verify_delivery.py export --project . --destination <不存在的新目录>
```

初始化保持不覆盖行为。旧verify_delivery.py入口不带子命令时默认只读verify；不再读取Downloads ZIP，不再初始化或导出历史报告。verify验证结构/语法/可读性，不运行测试；实际运行测试必须使用下面命令。需要保存验证报告时加--report-root <目录>，每次创建唯一子目录；不指定则不写文件。

## 新收据

```powershell
python fullstack-kit/scripts/run_check.py --project . --phase P4 --kind test --check-id unit-tests --scope tool_selftest -- python -m unittest discover -s fullstack-kit/tests -v
```

旧收据保留，不补签、不伪造新版本；重新实际执行才产生v2。默认scope为tool_selftest。真实业务项目使用project_acceptance，并在.fullstack/checks.json声明每阶段必需检查。例如（将python替换为实际记录命令中的相同可执行路径或名称，参数须完全一致）：

```json
{"P0":[{"check_id":"requirements-check","kind":"test","command":["python","-m","unittest","discover","-s","tests"]}]}
```

命令、配置或源码变更后必须重新验证。每个阶段配置至少一个检查；多种检查分别注册稳定ID。不要用同ID替换为无关smoke命令。JSON索引损坏时门禁拒绝：保留损坏现场，恢复已验证备份或在新工作区重新收集检查；不要手改DB或旧收据凑通过。

## 阶段编排

```powershell
python fullstack-kit/scripts/workflow.py --project . status
python fullstack-kit/scripts/workflow.py --project . approve --phase P0 --actor <项目所有者>
python fullstack-kit/scripts/workflow.py --project . advance --phase P0
```

approve需要所有者交互终端输入精确确认短语，不能通过管道自动批准。配置/业务决策未明确、前阶段未完成、检查失败/过期时阻断。P6/P7另外要求真实项目来源、生产用途证据、profile的明确授权和--authorize-production。该命令不会部署；真实部署仍需单独授权。

## 平台与回滚

Windows需Python 3.10+和实际安装的Node/npm。npm入口通过安装位置解析npm-cli.js；不支持的第三方wrapper默认拒绝。项目应由可信源码组成。

回滚只恢复工具包代码至基线326c82e或保留的源码副本，不删除v2数据库/收据与审查记录。v1程序看不到v2有效性，不应继续承担自动放行。技术验收不是业务验收。
