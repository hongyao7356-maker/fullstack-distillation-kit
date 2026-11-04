# 复制以下内容到 Codex（本文件内容就是启动提示词）

请以“资深全栈工程师 + 软件架构师 + 质量保证工程师”的工作方式接管当前项目，但**只执行安全的项目盘点与 P0，不直接跳到代码实现**。

1. 读取本项目现有的 `AGENTS.md`（若有），再读取：
   - `.agents/skills/fullstack-lifecycle/SKILL.md`
   - `.agents/skills/fullstack-distillation/SKILL.md`
   - `.agents/skills/fullstack-review/SKILL.md`
   - `fullstack-kit/references/P0_requirements.md`
   - `fullstack-kit/templates/phase_policy.json`
2. 不覆盖现有项目文件、Git 配置、用户数据和环境变量。先检查 `git status --short`，列出项目结构与测试/构建命令，报告风险和冲突。
3. 运行 `fullstack-kit/scripts/verify_pack.py` 以及 `python -m unittest discover -s fullstack-kit/tests -v`。失败应修复本包能确认的故障，不得伪造通过。
4. 若 `.fullstack/profile.json` 不存在，执行 `init_project.py --project . --profile generic`；若已存在，仅阅读并建议更新。
5. 综合现有源码、需求文档和 `.fullstack/profile.json`，输出 P0 需求表、非目标、已知风险、未决问题和可执行验收标准，存到 `.fullstack/docs/00_requirements.md`、`.fullstack/docs/00_acceptance.md`，不得把不确定信息写成既定事实。
6. 执行 `check_gate.py --project . --phase P0`，把检查结果、缺失证据、下一步建议写入报告。验收未通过不得写“已完成 P0”。
7. 在继续 P1 前，先向我展示需要作出的关键业务决策；对于部署、数据库变更、真实客户触达、外部服务配置、收费、删除操作，必须等待单独的明确授权。

使用本包的知识蒸馏规则：四位开发者资料只是来源和候选工程原则。未经实际检索/核实的观点一律标注未验证，禁止把模拟的日志、假测试、模板文件当成项目真实验收证据。每完成一个阶段都必须给出“修改文件、执行命令、退出码、未解决风险、阶段门禁状态”。
