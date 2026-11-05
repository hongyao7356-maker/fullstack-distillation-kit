# v1.2 门禁与迁移

升级后重新运行所有项目检查。新收据绑定项目路径、输入镜像摘要、阶段策略和工具代码。同一检查重跑、移动项目或改变输入后，重新检查和签名。

1. 在 `.fullstack/checks.json` 中为阶段策略的每个必需种类设置唯一的 `check_id`、`kind` 和完整的 `command` 数组。额外列出的检查也必须成功。P0–P5 使用 `project_acceptance`，P6–P7 使用 `production_release`。项目阶段推进需要至少一条显式检查。
2. 在项目目录执行，例如 `python fullstack-kit/scripts/run_check.py --phase P4 --kind test --check-id unit --scope project_acceptance -- python -m unittest discover -s tests`。命令分隔符 `--` 为必填。错误参数退出 2；敏感值应通过安全配置传入。
3. 命令在临时项目副本内执行。依赖树也会复制和散列，大项目需预留磁盘和时间；链接或目录联接可能阻断。副本与原项目共享宿主权限。宿主文件、外部工具链、环境变量、网络输入或运行中可变输入都需要独立审核。无法证明输入边界时停止签名。
4. 独立审查者核实执行环境、实际命令和输入，P6/P7 还要核实真实项目来源。在受信环境运行 `gate_policy.py --project <项目> --phase P4`，将标准输出按原始字节保存到项目外文件（避免终端转码或增加换行）。用单独保管的审查者密钥执行 `ssh-keygen -Y sign -f <审查者密钥> -n fullstack-origin-v1 <声明文件>`，将生成的签名复制为 `.fullstack/origin/P4.sig`。其他阶段替换阶段名。
5. 管理员在 Windows 系统目录的 `fullstack-kit/allowed_signers` 或 POSIX 的 `/etc/fullstack-kit/allowed_signers` 配置信任的公钥，格式为 `reviewer ssh-ed25519 <公钥数据>`。使用系统 OpenSSH 校验。部署方须保证信任文件和工具不可由被检项目更改；缺少信任配置时门禁阻断。
6. 使用 `workflow.py` 检查阶段并由负责人交互批准。工具验证、执行来源签名、阶段审批是三个分别留证的步骤。此包不执行生产部署。
