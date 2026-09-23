# 项目背景（Project Context）

## 研究目标与范围

本项目研究网站生成 agent 是否能通过长期记忆（Long-Term Memory）在跨任务过程中提升表现。目标场景是 WebGen-Bench 风格的网站生成：生成网站、评估功能行为与外观，然后保留对后续网站任务有用的跨任务经验。

核心对比仍是 **No Memory vs Long Memory**。当前工作处于探索阶段，优先研究什么样的记忆内容/prompt 形式有用；检索质量和大规模统计结论属于后续工作。

## 当前长期记忆方法

记忆设计区分三层：

1. `trajectories`：不可变的任务/运行 provenance、artifacts、evaluation results，以及原始 evidence 路径。
2. `reflection_cases`：具体的 functional 或 appearance cases，保留任务本地的 trigger、expected state、observed result、hypothesised cause、preventative action、verification 和 evidence references。
3. `experiences` / `skills`：更高层的 candidate 或 active 可复用知识。

`memory_sources` 保留 derivation/provenance。相似度（similarity）只用于发现候选；不得自动合并 memories。active Experience/Skill 是通常的 retrieval target；一条 trajectory 可以产生零条 memories。

case-oriented 路径将新任务拆解为最多三个 functional aspects 和一个 appearance aspect，并保持功能知识与外观知识分离。预期注入内容是简洁、面向当前任务的 implementation guidance，而不是历史 trajectories 的原始堆叠。

## 组件

| 组件 | 职责 |
|---|---|
| `src/long_memory_schema.sql` / `src/long_memory.py` | `trajectories`、`reflection_cases`、Experience、Skill 与 provenance 的 SQLite schema/initialization。 |
| `src/long_memory_runtime.py` | 通用 Long Memory extraction、admission、consolidation、evidence-aware retrieval 与 adapter contracts。 |
| `src/reflection_case_memory.py` | 具体 case storage、aspect decomposition、case/Experience candidate discovery、relevance decisions 与 case packet construction。 |
| `src/post_task_reflection.py` | 根据 task/evaluator evidence 创建 functional 和 appearance reflection drafts。 |
| `src/long_memory_integrations.py` | Azure Memory LLM/embedding adapters 与 Bolt prompt formatting。 |
| `scripts/run_continual_memory.py` | continual/domain-block experimental runner。 |
| `scripts/run_stage1.py` | 较早的 G1/G2-style runner 与通用 evaluator-result extraction。 |
| `src/automatic_bolt_diy/automatic_web_gen.py` | 驱动 Bolt generation、archive validation 与 prompt/artifact capture。 |

当前 case-only diagnostic 还包含 second-stage adaptation：Memory LLM 接收当前任务的
functional/appearance aspects 与人工选定 cases，过滤不匹配的具体字段，并生成当前任务
可执行的 implementation pattern；Generator 只接收改写后的 pattern。该路径尚未证明适合
正式大规模实验，automatic retrieval 仍应单独评估。

## 模型与接口

当前配置的 Azure deployments 按约定为：

- generator: `webgen-generator-gpt41-mini`;
- memory/reflection: `webgen-memory-gpt41-mini`;
- evaluator: `webgen-evaluator-gpt54-mini`;
- embedder: `webgen-memory-embedding`.

薄接口为 `MemoryLLM`、`Embedder` 和 `AgentAdapter`。Memory core 不应依赖 provider/plugin framework，也不应改变 `AgentAdapter` 返回内容的语义。

## 实验/评测方法

每个生成网站都使用 functional GUI/WebVoyager-style checks 和 screenshot appearance evaluator 评测。raw evaluator trajectories 作为 evidence 保留。每个 check 的结果应保留 Pass/Partial/Fail，以及可用时的 structured attribution（例如 logic failure、interaction-budget exhaustion、appearance issue）。

Generation prompt provenance 通过每个生成目录下的 `000001.prompt.txt` 保存；新 runner 也会把
prompt（或其路径）放入 trajectory `run_config`。Bolt exported chat JSON 不是完整 prompt 的权威来源。

Long Memory 不得使用 hidden final-evaluation instructions/results 修复同一个 formal benchmark task。post-task reflection 可以为后续任务创建 memory。同任务 reflection/retry 仅是 diagnostic experiment，必须明确标注。正式结论的各 comparison arms 应使用相同 generator/evaluator/task settings。

## 仓库约定

- 当前研究使用的 main working branch：`reflective-multimodal-memory`。
- outputs 位于 `outputs/experiment/`；每次运行需要新的 output directory。
- Prompt provenance：存在时，`000001.prompt.txt` 是权威的 submitted prompt；Bolt 导出的 chat JSON 可能遗漏追加的 memory。
- Bolt generation 和基于 PM2 的 evaluation 共享 host state。不得并发运行相互竞争的 evaluators；使用 runner 的 evaluation lock。
- 现有 worktree changes 可能属于之前的 agents/Copilot。保留无关 modifications，禁止随意 reset/clean worktree。
