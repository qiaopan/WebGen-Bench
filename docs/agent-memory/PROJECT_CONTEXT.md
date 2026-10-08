# 项目背景（Project Context）

> **2026-10-03：WebGen-Bench 这一阶段已封版归档**（总结见根目录 `README.md`，快照见 `archive/phase1-webgen-2026-10/`）。下一阶段可能转向 SWE 类基准；下面描述的是本阶段的架构。
>
> **2026-10-05：WebGen 在学校 H200 集群上重启**，全部自部署、不调 Azure、采用官方评测协议（见 DECISIONS「WebGen 第二阶段」）。下文的 Azure 角色只适用于第一阶段。

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

默认 Azure-only 配置的 deployments 按约定为：

- generator: `webgen-generator-gpt4o`（Azure GPT-4o，version `2024-11-20`）；
- memory: `webgen-memory-gpt4o`（Azure GPT-4o，version `2024-11-20`）；
- reflection: `webgen-evaluator-gpt54-mini`（仅完成任务后的反思）；
- functional evaluator: `webgen-functional-evaluator-gpt4o`（Azure GPT-4o，version `2024-11-20`）；
- appearance evaluator: `webgen-appearance-evaluator-gpt4o`（Azure GPT-4o，version `2024-11-20`）；
- embedder: `webgen-memory-embedding`.

2026-09-28 起另有一个**论文近似的本地 5090 baseline profile**，不得与 Azure-only 结果混用：

- generator: `WebGen-LM-7B`，经 localhost OpenAI-compatible endpoint；
- functional evaluator: `qwen2.5-vl-32b-awq`（Qwen2.5-VL-32B-Instruct-AWQ），经另一 localhost endpoint；
- appearance evaluator: Azure `webgen-appearance-evaluator-gpt4o`；
- memory/reflection 与 embedding: Azure `webgen-memory-gpt4o`、`webgen-memory-embedding`（No Memory 条件不调用它们）。

代码通过角色专用 `WEBGEN_GENERATOR_*`、`WEBGEN_FUNCTIONAL_EVALUATOR_*`、`WEBGEN_APPEARANCE_EVALUATOR_*` 环境变量路由；只保留旧通用 evaluator 变量作回退。运行前使用 `scripts/preflight_reflective_models.py` 验证所有角色。local endpoints 由 SSH tunnel 提供，具体连接凭据不进入仓库文档。

2026-09-29 起服务器只剩一台 5090，另有一个**Mac 本地生成器 profile**（独立标注，不与上面的 5090 BF16 profile 混用）：generator 改为 Mac（Apple M5、24GB）上 llama.cpp 运行的 `WebGen-LM-7B` Q8_0（自行从官方权重量化），仍暴露 `http://127.0.0.1:8000/v1`、模型名 `WebGen-LM-7B`；functional evaluator 仍是服务器上的 `qwen2.5-vl-32b-awq`（经 8001 隧道）；其余角色不变。决策与理由见 DECISIONS.md。

薄接口为 `MemoryLLM`、`Embedder` 和 `AgentAdapter`。Memory core 不应依赖 provider/plugin framework，也不应改变 `AgentAdapter` 返回内容的语义。

## 实验/评测方法

每个生成网站都使用 functional GUI/WebVoyager-style checks 和 screenshot appearance evaluator 评测。raw evaluator trajectories 作为 evidence 保留。每个 check 的结果应保留 Pass/Partial/Fail，以及可用时的 structured attribution（例如 logic failure、interaction-budget exhaustion、appearance issue）。

Generation prompt provenance 通过每个生成目录下的 `000001.prompt.txt` 保存；新 runner 也会把
prompt（或其路径）放入 trajectory `run_config`。二者记录的是“打算发送”的文本；Bolt exported chat JSON（`000001.json`）才是模型实际收到内容的权威来源。2026-09-26 之前 Bolt 会在第一个换行处截断 prompt（已修复，见 DECISIONS.md），runner 现在用 `prompt_delivered` 核对二者是否一致。

Long Memory 不得使用 hidden final-evaluation instructions/results 修复同一个 formal benchmark task。post-task reflection 可以为后续任务创建 memory。同任务 reflection/retry 仅是 diagnostic experiment，必须明确标注。正式结论的各 comparison arms 应使用相同 generator/evaluator/task settings。

## 仓库约定

- 当前研究使用的 main working branch：`reflective-multimodal-memory`。
- outputs 位于 `outputs/experiment/`；每次运行需要新的 output directory。
- Prompt provenance：存在时，`000001.prompt.txt` 是权威的 submitted prompt；Bolt 导出的 chat JSON 可能遗漏追加的 memory。
- Bolt generation 和基于 PM2 的 evaluation 共享 host state。不得并发运行相互竞争的 evaluators；使用 runner 的 evaluation lock。
- 现有 worktree changes 可能属于之前的 agents/Copilot。保留无关 modifications，禁止随意 reset/clean worktree。
