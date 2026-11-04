# F01—F05 修复报告

日期：2026-11-05。所有下面列出的回归均实际执行；最终完整套件38项、退出0。测试均为工具级隔离fixture，不是业务验收。

## F01

根因：任意历史成功即可通过，缺少检查身份和当前输入绑定。

修改文件：evidence_engine.py、check_gate.py、run_check.py、workflow.py

关键修改：事务序号选取每个check_id最新记录；running/失败/超时/损坏/v1阻断；快照及精确配置命令绑定。

回归测试：test_pass_fail_pass_latest_only；test_source_change_invalidates；test_corrupt_latest_never_falls_back；test_concurrent_same_check_serialized_no_partial_receipts；test_interrupted_execution_blocks_old_pass_and_recovers；test_required_command_cannot_be_substituted

实际结果：PASS，最终完整套件中通过；原反例重跑恢复预期拒绝/成功行为。

日志：evidence/F01-red.log→F01-green.log；concurrency.log；independent-fixes-final.log

残余风险：本地同账户可直接篡改数据库；依赖安装目录/解释器缓存不逐文件快照。生成物变化保守失效，需要稳定产物后重跑。

## F02

根因：Windows CreateProcess无法把npm名称当作原生可执行文件；普通subprocess超时只处理直接进程。

修改文件：command_executor.py、command_worker.py、run_check.py

关键修改：解析可信npm-cli.js交由Node；参数数组无shell；握手前纳入Job，关闭Job终止后代；启动失败127、超时124。

回归测试：test_real_npm_test_build_and_cmd；test_node_absolute_local_script；test_timeout_kills_descendant

实际结果：PASS，最终完整套件中通过；原反例重跑恢复预期拒绝/成功行为。

日志：evidence/F02-red.log→F02-green.log；final-suite.log

残余风险：本次Windows实测；POSIX实现未运行。非标准第三方wrapper默认拒绝，npm项目脚本仍是可信执行输入。

## F03

根因：校验前直接调用dict/set操作；provenance用str强转掩盖类型错误。

修改文件：validate_cards.py

关键修改：先验证根类型和字段类型，再做枚举/来源检查；无效输入统一2、可定位诊断，不打印输入值。

回归测试：test_invalid_inputs_have_located_errors_and_exit_two

实际结果：PASS，最终完整套件中通过；原反例重跑恢复预期拒绝/成功行为。

日志：evidence/F03-red.log→F03-green.log；final-suite.log

残余风险：结构正确不证明卡片观点真实；不开展来源在线核验。

## F04

根因：只对日志有限字段做替换，命令元数据明文保存，缺少已知环境秘密及private_key策略。

修改文件：security.py、run_check.py、delivery.py、workflow.py

关键修改：拒绝秘密参数；统一known-value/字段/Bearer/引号脱敏；结构化序列化保持JSON合法；历史只读扫描。

回归测试：test_secret_argument_not_persisted；test_known_environment_secret_stdout_stderr_redacted；test_private_key_output_redacted；test_quoted_and_bearer_secret_output_redacted；test_sanitized_json_remains_parseable

实际结果：PASS，最终完整套件中通过；原反例重跑恢复预期拒绝/成功行为。

日志：evidence/F04-red.log→F04-green.log；redaction-extra-red.log→independent-fixes-final.log

残余风险：不能识别所有未标注且未知的任意秘密；历史已存在的合成哨兵保留并报告，未删除证据。

## F05

根因：验证与一次性导出混合、固定Downloads输入、已有输出触发异常。

修改文件：delivery.py、work/verify_delivery.py

关键修改：默认只读verify；显式export检测冲突；唯一可选报告目录；portable manifest；拒绝递归导出。

回归测试：test_repeat_verify_is_read_only；test_export_conflict_and_portable_verify；test_export_inside_source_rejected

实际结果：PASS，最终完整套件中通过；原反例重跑恢复预期拒绝/成功行为。

日志：evidence/F05-red.log→F05-green.log；independent-fixes-final.log

残余风险：只读verify不运行测试；完整测试需另行执行。导出不是原项目的备份，不带业务证据/凭据。

## 独立审查补修

独立Agent发现R01工作目录快照遗漏、R02命令替换、R03 private_key泄露；已各自先复现失败，再修复并回归通过。原独立报告保持原样。独立诊断脚本仅替换隔离输出目录后重跑：snapshot_unchanged=false、evidence_after_test_change=false、替代smoke仍有阻断项、sentinel_persisted=false。补修由实施者执行回归关闭，未进行第二次独立审查。
