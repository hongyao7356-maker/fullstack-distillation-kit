# v1.3 验收映射

以下为用例映射。实际结果、命令、退出码、日志散列由最终验收报告记录。全部用例均使用合成工具 fixture，不使用真实生产凭据。

| 项 | 验证位置 |
|---|---|
| T01 合规授权范围通过 | test_release_v13 当前环境正例、历史产物正例 |
| T02 环境 pass→fail | test_runner_v13、test_release_v13 环境变化和实际失败 |
| T03 工具二进制与依赖变化 | test_environment_v13 Node 二进制、安装内容变化、外部 Python 拒绝 |
| T04 未批准变量隔离 | test_environment_v13 NODE_OPTIONS/UNKNOWN_INJECTION、Python 环境 |
| T05 并发输入改变 | test_runner_v13 并发配置变化失效；真实隔离平台的瞬态篡改防护仍需平台验收 |
| T06 秘密安全 | 原 test_security_v11、test_parser_v12，加环境模拟低熵秘密拒绝和隔离 |
| T07 npm 产物实际留存 | test_runner_v13，保留文件内容可读 |
| T08 保留文件篡改 | test_runner_v13、test_release_v13，门禁拒绝 |
| T09 必需产物缺失 | test_artifacts_v13、test_release_v13 |
| T10 同 run_id 冲突 | test_artifacts_v13 单进程和双进程发布 |
| T11 旧签名/schema/产物拼接 | test_attestation_v13、test_release_v13、test_artifacts_v13 |
| T12 多次运行独立发布 | test_artifacts_v13 独立 run_id |
| 签名者权限、撤销和过期 | test_release_v13，项目/阶段/用途/平台/有效期各项反例 |
| 路径安全 | test_artifacts_v13 绝对路径、穿越、ADS、保留名、重复路径、硬链接、junction |
| 中断恢复 | test_artifacts_v13 提交异常、真实终止发布进程后重试 |
| 最终交付物 | verify_release.py 正常入口测试及 verify_delivery 实际文件对比 |
| 既有回归 | 保留原49项，覆盖输入校验、脱敏、超时进程树、并发收据、阶段审批等 |

T05 的本地失效与未签名阻断可实测。真实受信 CI 隔离、网络服务边界和生产权限配置尚未提供，因此不得把其标记为真实平台 PASS。
