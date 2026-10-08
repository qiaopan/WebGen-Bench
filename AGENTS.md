# Codex repository instructions

## 共享记忆（每个新 Codex session 的 cold start 必做）

在开始任何有意义的仓库工作、计划或修改前，依次完成：

1. 阅读 `docs/agent-memory/PROJECT_CONTEXT.md`。
2. 阅读 `docs/agent-memory/DECISIONS.md`。
3. 阅读 `docs/agent-memory/HANDOFF.md`。
4. 运行 `bash scripts/codex-handoff-brief.sh`，取得新鲜的 Git 状态、近期提交/差异摘要，以及实验输出是否比 `HANDOFF.md` 更新的检查结果。

这些步骤是 Codex 在本仓库中的共享记忆接入机制。不要创建 Codex 专属的第二套 project memory；唯一共享记忆始终是上述三份文件，也由 Claude Code 使用。

## 事实来源与冲突处理

1. 实际仓库状态优先：`git status`、Git history/diff 及 `outputs/experiment/*/continual-report.json`（或其他实际输出）是真实状态的 source of truth。
2. `HANDOFF.md` 是交接指针，不是不可质疑的事实。若启动检查发现更新的实验输出，或代码/Git 与文档冲突，先核实实际文件，再明确说明 `HANDOFF.md` 可能已过期。
3. `PROJECT_CONTEXT.md` 与 `DECISIONS.md` 是稳定的背景与决策记录；除非实际实现或已确认的新研究决策与其冲突，否则应遵守它们。

## shared-memory maintenance（语义判断，不是机械动作）

- 当有意义的工作改变下一位 agent 需要知道的当前状态时，更新 `docs/agent-memory/HANDOFF.md`。删除已解决项目；不要把它写成完整实验日志或 Git history。
- 只有发生真实的研究/架构决策、决策变更或决策被 superseded 时，更新 `docs/agent-memory/DECISIONS.md`。
- 只有稳定的项目级架构、方法或约定改变时，更新 `docs/agent-memory/PROJECT_CONTEXT.md`。
- 不要在每次小修改后机械更新三份文件。Git 始终是代码变更的 source of truth。

## 语言与边界

- 面向用户的解释、报告、问题和总结使用中文；代码标识符、路径、命令、配置键、hook/event 名称和模型名保留英文。
- `docs/agent-memory/*.md` 使用中文为主、英文技术标识符保留原样。
- 不要为了 Codex 修改 `.claude/`、`CLAUDE.md` 或 Claude Code 的接入机制；两边仅共享 `docs/agent-memory/` 中的三份文件。
