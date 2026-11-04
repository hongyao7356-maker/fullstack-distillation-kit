# Codex 全栈开发工程方法蒸馏包 v1.0

**用途**：把公开全栈工程案例提炼成可追溯的决策规则和交付流程，再由 Codex 在当前仓库逐阶段执行；不是训练模型权重，也不承诺能取代专业工程师。

**适用**：Windows + PyCharm + Codex；亦可运行在 macOS / Linux。核心脚本仅使用 Python 3.10+ 标准库。

## 一、安装（推荐：直接给 Codex）

1. 为现有项目创建 Git 提交或备份。**不要将此包解压覆盖已有 `AGENTS.md`、代码、`.env`、凭据或测试脚本。**
2. 把本 ZIP **直接解压到项目根目录**，确保下面两个文件在项目中存在：
   - `.agents/skills/fullstack-lifecycle/SKILL.md`
   - `fullstack-kit/BOOTSTRAP_CODEX.md`
3. 在 PyCharm 中打开项目根目录，打开 Codex 对话，复制 `fullstack-kit/BOOTSTRAP_CODEX.md` 全部内容给 Codex。
4. 在 PyCharm Terminal（PowerShell）执行：

   ```powershell
   py -3 fullstack-kit/scripts/verify_pack.py
   py -3 -m unittest discover -s fullstack-kit/tests -v
   py -3 fullstack-kit/scripts/init_project.py --project . --profile generic
   ```

   Python 只有 `python` 命令时把 `py -3` 换成 `python`。
5. 先让 Codex 执行 **P0：现状盘点与需求验收**。没有用户批准的风险操作不执行；不能把模板当成验收证据。

如需适配数字员工项目，可使用以下路径为项目根目录（由用户在自己的 Windows 环境中执行，不在此包中写入目标路径）：

```
D:\Users\hp\Documents\ChatGPT\New project
```

运行 `init_project.py --project . --profile digital-employee` 生成项目画像草稿（不覆盖已有配置）。

## 二、完整目录

- `.agents/skills/fullstack-lifecycle/`：项目生命周期 Skill，负责按阶段实现。
- `.agents/skills/fullstack-distillation/`：知识蒸馏 Skill，负责提炼来源、证据与局限。
- `.agents/skills/fullstack-review/`：工程审查 Skill，负责审查与复验。
- `fullstack-kit/BOOTSTRAP_CODEX.md`：一次粘贴即可启动的提示词。
- `fullstack-kit/references/P0..P7_*.md`：八个阶段的工程操作规范。
- `fullstack-kit/sources/source_registry.json`：四位开发者及官方资料的**待研究入口**。
- `fullstack-kit/cards/`：两张经过公开文档支持的示例原则卡 + 未验证的研究议题。
- `fullstack-kit/templates/`：项目画像与证据卡格式、阶段标准。
- `fullstack-kit/scripts/`：初始化、来源采集、知识卡校验、命令记录与阶段验收。
- `fullstack-kit/tests/`：脚本自检单元测试。

## 三、第一次交付应是什么

Codex 第一次只需：
1. 确认当前代码库结构、Git 状态、可执行的测试命令、当前尚未明确的需求；
2. 基于实际仓库把 `.fullstack/profile.json` 中的草稿字段补齐，但不要覆盖用户决策；
3. 生成 `.fullstack/docs/00_requirements.md` 和 `.fullstack/docs/00_acceptance.md`（有待确认内容必须列成未决事项）；
4. 列出 P0 缺口，运行门禁检查，**不要提前写正式业务代码**。

## 四、阶段与门禁

P0 需求与边界 → P1 架构与风险 → P2 数据与权限 → P3 前后端与 API → P4 自动化测试 → P5 安全 → P6 部署与回滚 → P7 监控与维护。

检查阶段（示例）：

```powershell
py -3 fullstack-kit/scripts/check_gate.py --project . --phase P0
```

命令证据必须由执行工具产生；仅有文字说明无法替代通过的命令输出。

```powershell
py -3 fullstack-kit/scripts/run_check.py --project . --phase P4 --kind test -- py -3 -m unittest discover -s tests
```

这是**示例命令**，只有目标项目确有对应测试目录才执行；Codex 应按项目栈选择命令。

## 五、蒸馏资料（用户交给 Codex 的是“方法”，而非复制课程）

GitHub 仓库的代码可在各自许可证条件下阅读、学习；付费课程、视频、文章等版权内容仅引用公开网址及短摘要，不得绕过付费墙、大规模转载或把无授权内容塞进包里。知识卡应使用**自己的概括**、注明来源与版本、注明适用条件和反例。仓库历史/Issue/PR 只能被标记为“已研究”，如果实际打开并记录了对应的 URL、commit SHA / PR / 行为证据。

可选的在线元数据收集：

```powershell
py -3 fullstack-kit/scripts/fetch_metadata.py --project .
```

这只采集 GitHub 公共仓库元数据，不拉取代码、**不执行第三方代码**；离线也能用整个包。GitHub API 可能限流；网络访问失败不影响基础安装。

## 六、准确说明边界

- 此包提供工程流程、来源入口、初始示例卡和自动检查脚本；**没有替你下载并人工精读四位开发者的所有教程、视频、Issue、PR**。深度蒸馏是后续可追溯工作，不能伪称已完成。
- 阶段检查通过意味着所要求的文档、证据与文件完整性符合**静态规则**，不代表业务正确、测试覆盖充分或可以直接上线。
- 任何生产部署、数据删除、真实微信自动回复、获取凭证、外部付费服务调用，均需事前人工明确授权。
- 已有项目约束、原有 `AGENTS.md`、项目的构建与测试要求优先于本包泛化示例。**冲突时先报告，不暗自覆盖。**
