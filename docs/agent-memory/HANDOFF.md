# 当前交接（Codex → Claude Code）

## 当前目标

继续验证 WebGen Long Memory 中“历史 reflection case 是否能经过任务分解、二次反思和 implementation-pattern 改写后改善后续网站生成”。当前阶段刻意关闭 automatic embedding retrieval，使用人工选择的历史 cases，隔离 prompt/memory-content quality 与 retrieval quality。

## 本 session 已完成的 meaningful work

- 核对并比较了 000014 的多轮诊断实验，区分了逻辑失败、interaction-budget exhaustion、评测证据不足和 appearance 质量问题。
- 在 `scripts/run_stage1.py` 中增加结构化评测归因字段：`failure_stage`、`failure_type`、`failure_reason`、`reached_target_action`、`logic_failure_observed`；appearance 结果增加 `score` 和 `appearance_quality_issue`。
- 在 `src/automatic_bolt_diy/automatic_web_gen.py` 中保存实际发送给 Bolt 的 `000001.prompt.txt`，因为 exported chat JSON 可能遗漏追加 prompt；generation result 也返回 `prompt_path`。
- 在 `scripts/run_continual_memory.py` 中加入人工 cases 经 Memory LLM 改写为当前任务 implementation patterns 的路径，并把新 prompt 保存到 trajectory `run_config`。
- 在 `src/reflection_case_memory.py` 中加入 second-stage case adaptation，保留 functional/appearance 分离，并记录 `implementation_adaptations`。
- 后续进一步把 `task_aspects` 传给人工 case adaptation，要求当前任务没有的具体字段（例如 DOB）不得直接加入，只允许迁移抽象验证原则。

## 最新有效实验

输出目录：`outputs/experiment/confirmed_000014_aspect_gate_r1`

- task：000014；mode：continual；人工选择 cases；automatic retrieval 关闭。
- 流程：人工 cases → task-aspect decomposition → Memory LLM 二次剪枝/改写 → GPT-4.1-mini generator → GPT-5.4-mini evaluator。
- 状态：`pipeline_status: completed`；无运行中进程。
- 结果：4 passed / 1 partial / 0 failed（5 functional checks）；appearance score 3。
- 唯一 functional partial：`interaction_budget_exhausted`；未观察到明确 logic failure。
- 最终 prompt 只保留了 lead-form confirmation pattern，DOB 具体 guidance 已被剪掉；可查看 `tasks/000014/continual/000001.prompt.txt`。

对照结果：

- `outputs/experiment/golden_cases_000014_r1`：3 pass / 2 partial / 0 fail，appearance 4；人工 cases 直接交给 generator，没有独立 Memory LLM adaptation。
- `outputs/experiment/confirmed_000014_manual_adapt_r1`：2 pass / 2 partial / 1 fail，appearance 3；Memory LLM adaptation 没有严格使用 task aspects，错误保留 DOB guidance。
- 最新 aspect-gated 版本相对上一版减少了 1 个 fail 和 1 个 partial，但 appearance 没有提升；这仍是单任务 diagnostic，不是正式统计结论。

## 当前未解决问题

- 尚未构建 provenance-safe、同时包含 000015 与 000018–000021 的统一 seed database；18–21 的 reflection 分散在 JSONL，部分结构化知识在另一个 DB，不能直接整库复制。
- second-stage adaptation 目前只在人工 case 路径做过诊断；自动 retrieval 尚未优化，也不应与本 prompt-content 结论混合。
- interaction-budget partial 仍可能掩盖网站真实逻辑；应继续保留原始轨迹和结构化归因，不把所有 Partial 当作 code bug。
- appearance score 仍主要来自截图；CSS/computed-style 颜色检查尚未实现为独立辅助指标。
- 当前 worktree dirty，包含先前 Copilot/agent changes、实验脚本和未提交文件；不得 reset/clean 或把全部 dirty changes 当成本 session 的单一 commit。

## Claude Code 接手后的第一步

先只读检查最新 prompt、`memory-events.jsonl`、`post-task-reflections.jsonl` 和 `progress.jsonl`，确认 aspect-gated adaptation 的实际输入/输出；随后决定是否构建统一 seed DB。不要直接启动付费 generation，除非先给出 pre-run comparison table 并取得用户确认。

## 易误解的临时信息

- `second_reflection_000014_r1` 已中断且只用了 000015 cases，不代表完整历史方案。
- `confirmed_000014_manual_adapt_r1` 与 `confirmed_000014_aspect_gate_r1` 都是诊断实验，不是 No Memory vs Long Memory 的正式全量结果。
- `task_request` 是原始 requirement；新运行的完整实际 prompt 应优先查看 `000001.prompt.txt` 或 trajectory `run_config.generation_prompt`，不要只看 exported chat JSON。
- `interaction_budget_exhausted` 表示 agent 没走到目标动作，不等于已经观察到网站逻辑失败。
