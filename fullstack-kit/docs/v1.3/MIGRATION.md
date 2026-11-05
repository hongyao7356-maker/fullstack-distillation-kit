# v1.2 到 v1.3

## 数据与兼容性

v1.3 保留 SQLite 执行索引和 schema_version=2 收据容器，新增 contract_version=1.3、environment、environment_mode、candidate_id、artifact、started_utc、finished_utc。外部签名载荷使用独立的 schema_version=1.3。v1.2 生产签名不能满足 v1.3 门禁。旧文件保留用于审计。

P6/P7 强制执行平台与审查者双签。非生产项目可显式设置 contract_version=1.3 升级双签，历史非生产审批入口继续兼容。所有 project_acceptance/production_release 运行均采用受控环境；未声明环境的 tool_selftest 保留诊断兼容行为，其收据不能满足项目或生产用途。

## 检查配置

每个阶段使用唯一 check_id，同阶段各项使用同一个 candidate_id 和 runner_id。每个已配置检查均为必需，阶段政策要求的 kind 也必须配置。修改候选、配置、源码或工具政策后重跑并重新签名。最新执行失败或仍在运行时，旧成功不能用于当前候选。

```json
{
  "P6": [{
    "check_id": "release-build",
    "kind": "build",
    "command": ["npm", "run", "build"],
    "scope": "production_release",
    "contract_version": "1.3",
    "candidate_id": "release-2026-11",
    "runner_id": "organization-windows-builder",
    "environment": {
      "keys": ["REVIEW_BUILD_MODE"],
      "mode": "CURRENT_ENV_CHECK"
    },
    "outputs": [{
      "path": "dist",
      "type": "directory",
      "max_bytes": 10485760,
      "max_files": 1000
    }]
  }]
}
```

keys 是明确声明为非秘密的环境变量名。值从当前宿主读取，未设置也绑定。秘密名称、已知秘密值、加载器覆盖项被拒绝；秘密不得伪装成普通配置。当前适配器不传递生产秘密引用，涉及秘密或外部服务的构建需另行接入受信平台。

CURRENT_ENV_CHECK 要求验证时实际环境、工具和依赖仍一致。ATTESTED_BUILD_ARTIFACT 验证双签绑定的原构建产物，允许无关本地环境变化，仍核对当前候选、最新记录、政策、源码及实际产物。历史产物可留存审计；跨候选发布需要显式配置和新的证明。

## 支持的执行边界

受控入口支持当前宿主 Python、Node、npm/npx；具体命令还受 runner 与 kind 政策限制。外部 Python/venv、py 启动器及其他未绑定工具链被拒绝。直接 Python 检查和工作进程使用 -S，依赖全局 site-packages 的 pytest/mypy 项目需要受信平台适配，不能声称当前入口已支持。

子进程使用最小环境，固定 PATH 和必要 Windows 变量，隔离 NODE_OPTIONS、PYTHONPATH、用户 npm 配置。工具身份包含实际二进制、npm 安装内容、宿主标准库/DLL/全局包，以及项目 node_modules/.venv/venv 内容。Python 全局启动钩子带活动代码时拒绝运行。散列全依赖会增加检查耗时和磁盘读取。

本地副本仍共享宿主权限。绝对路径、动态服务、执行中替换恢复、任意多级子进程的外部依赖，需要真实执行平台提供不可变输入与访问控制。双签适配器要求平台为此负责，缺少有效证明即阻断。

## 产物与故障恢复

仅成功、输入一致、声明了 outputs 的 build 才发布产物。文件在 .fullstack/artifacts/<run_id>/files 下，manifest 在同级。输出根支持 dist/build 下的新文件，覆盖原输入会使收据失效。其他输出根当前需调整 runner 策略并重新审查。

暂存目录完成后原子发布。目标存在时拒绝覆盖。异常中断可能留下 .staging-* 或尚未绑定成功收据的孤立产物；门禁不认可这些对象。重试使用新 run_id；同 run_id 冲突由调用方处理。没有自动清理，默认保留所有证据，人工审查期间应固定保留。部署管理员负责配额、访问权限、归档与备份；清理必须经授权，删除后验证应失败。

## 外部证明接口

受信执行平台应在自己控制的隔离环境执行检查，核实全部输入和输出，再生成规范 JSON。用 verify_release.py payload --project <项目> --phase P6 --issued-utc <UTC时间> --expires-utc <UTC时间> 输出原始 UTF-8 字节；有效期最长 24 小时。保存到项目外文件，避免 PowerShell 转码。

平台用其私钥对原始字节执行 ssh-keygen -Y sign -n fullstack-v1.3-runner。独立审查者用另一把私钥执行 ssh-keygen -Y sign -n fullstack-v1.3-reviewer。分别将 JSON、两个签名交付为 .fullstack/origin/P6.attestation.json、P6.runner.sig、P6.reviewer.sig。签名生成端必须核实声明，不能自动给任意本地 JSON 背书。

Windows 信任表为系统目录 fullstack-kit/trust-v13.json，POSIX 为 /etc/fullstack-kit/trust-v13.json。管理员保护该文件、工具和私钥。每条 signer 包含 role、public_key（Ed25519）、projects（精确绝对路径列表）、phases、scopes、runner_ids、revoked、not_before、not_after。runner/reviewer 公钥必须不同。撤销立即影响后续验证。

该接口是外部证明校验协议。真实 CI 接入、凭据保管、权限配置和平台隔离需要单独验收，本次没有安装生产信任锚。

## 验证实际交付文件

运行 verify_release.py verify --project <项目> --phase P6 验证当前候选。附加 --delivery-root <目录> 时，该目录下按 run_id 存放交付文件树（如 <run_id>/dist/app.js），验证器逐项核对保留清单与实物，拒绝额外文件、遗漏、篡改和链接。

通过表示工具证据可提交人审。workflow 的阶段审批继续单独执行，部署由业务发布流程负责。
