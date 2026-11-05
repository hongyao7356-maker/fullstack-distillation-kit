# v1.2 工具验收

**TOOLING_READY_FOR_HUMAN_REVIEW**。Windows 本机全量回归 49 项通过，退出 0。未验证 POSIX、真实业务项目或生产环境。独立审查、失败反例和最终日志见同目录 evidence/。

| 缺陷 | 修改与实测 |
|---|---|
| R01 | evidence_engine.py、run_check.py 在执行前构建输入副本，并绑定当前输入摘要。test_inputs_v12.py 覆盖间接加载、目录联接、依赖变化和 npm 构建产物。原反例中修改断言后，旧成功失效，重跑退出 1。 |
| R02 | gate_policy.py 为 check_gate.py 和 workflow.py 提供同一套策略检查。P6 缺 build 的原反例在两个入口均阻断。test_policy_v12.py 实测独立签名、签名重放和命令身份。原工作流测试保留断言，增加测试签名并用实际 lint 命令替换曾标作 lint 的 unittest。 |
| R03 | run_check.py 在执行前解析参数，错误返回 2。test_parser_v12.py 检查随机哨兵、空收据目录和合法命令；错误参数不再出现在标准错误中。 |

从 v1.1 标签独立导出的基线通过原 38 项测试。修复期间全量回归曾暴露 Windows 并发初始化锁文件的竞争；移除加锁前多余的字节写入后，全量 49 项和单独的 3 项并发测试均通过。

独立审查实测，在可写副本中临时替换文件再恢复，仍可取得本地成功收据。两个门禁都阻断没有独立输入验证签名的收据。管理员需保护签名信任配置；审查者应在能核实环境和全部执行输入时才签名。大依赖目录的性能未测。签名测试使用临时密钥，未配置实际系统信任。

复跑命令为 `python -B -m unittest discover -s fullstack-kit/tests -v`。原始反例的修复前后输出分别在 evidence/before.json 和 evidence/after.json。各文件字节散列见 evidence/SHA256.json。
