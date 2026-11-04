# v1.1 架构与信任边界

## 组件

| 组件 | 文件 | 职责 |
|---|---|---|
| Evidence Engine | scripts/evidence_engine.py | 快照、检查身份、事务序号、原子文件、只读有效性校验 |
| Command Executor | scripts/command_executor.py、command_worker.py | 可信工具解析、无shell启动、Windows进程树生命周期 |
| QA Runner | scripts/run_check.py | 保留CLI入口，记录执行、scope、结果和安全日志 |
| Quality Gate | scripts/check_gate.py | 静态阶段文档与当前有效检查；不宣称业务批准 |
| Workflow Orchestrator | scripts/workflow.py | P0→P7依赖、人工批准、状态与生产条件 |
| Audit / Security | workflow事件库、scripts/security.py | 事务审计链、脱敏、历史只读扫描 |
| Delivery | scripts/delivery.py、work/verify_delivery.py | 可重复只读验证、显式非覆盖导出 |

## 证据生命周期

check_id默认是phase.kind；多个同类检查应显式提供不同ID。一个ID固定所属阶段和种类。相同ID以OS文件锁串行执行；SQLite自增seq定义启动顺序，墙钟时间不承担排序职责。锁由OS在进程结束时释放。

执行前先持久化running记录，再启动子进程。崩溃后running继续阻断，下一次明确重跑才能恢复。日志和收据先写同目录临时文件、flush/fsync后replace；最后事务更新索引为complete。索引保存收据哈希，收据保存日志哈希；最新记录不合法时不回退历史成功。

收据v2绑定phase/kind/check_id/scope、源码快照、命令参数哈希、运行ID与seq。运行前后快照必须相同。快照默认纳入work、outputs、build、dist及普通文件；只排除Git、证据运行区、依赖目录和解释器缓存。profile.json与checks.json显式纳入；所有检查器Python模块也参与版本指纹。目录链接拒绝，不静默跳过。生成物改变会保守地使证据过期；生成式构建需在产物稳定后重跑，不应通过排除真实源文件绕过检查。

旧格式JSON不会自动成为v2证据。损坏SQLite、缺失最新日志、部分收据、变更源码和新失败均阻断。SQLite和文件哈希提供本地完整性，不抵抗有同账户写权限的恶意篡改。

## 阶段与批准

static门禁保留原v1语义，仅说明文档和所需记录齐备。workflow另要求checks.json给出每阶段至少一个实际检查，精确command参数、check_id和kind必须匹配；缺配置拒绝。P0还要求目标/用户明确、未决决策清空。阶段顺序不可跳跃。

P0—P5要求project_acceptance证据；P6/P7要求production_release证据、profile.evidence_origin=real_project、production_deploy_authorized=true及独立生产授权。tool_selftest默认不能满足这些要求，synthetic来源不能生产放行。数据来源真实性仍由本地所有者负责，软件不具有鉴别虚假人为声明的能力。

批准绑定当前源码、阶段文档、政策和最新证据。源码、文档或检查结果变化后批准变stale。CLI批准要求真实交互终端，输入包含阶段和完整上下文哈希的确认短语。内部API的human_confirmed是可信调用方接口，不是对恶意本地Python调用的权限隔离。完成状态仅代表流程记录，程序不含部署操作。

## 执行与安全

Windows通过Job Object的KILL_ON_JOB_CLOSE管理后代。worker先等待stdin握手，父进程成功分配Job后才发送命令；失败则不启动业务检查。Python、Node和npm均使用参数数组，npm.cmd不通过shell拼接。无法识别的shell wrapper拒绝。npm run仍会执行项目定义的脚本，项目脚本是用户明确选择的可信代码，不构成沙箱。

持久化前拒绝敏感参数并脱敏输出；不保存完整环境。未标注且不在已知环境秘密集合中的任意文本无法被可靠自动识别为秘密。扫描器报告路径、行号、类别，不返回秘密值。

Windows已实测。POSIX分支使用进程组终止，在本次Windows环境未执行；新Codex会话自动发现Skill未验证。
