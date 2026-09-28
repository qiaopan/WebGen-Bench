# 持久决策记录（Durable Decisions）

## CURRENT 决策

### 实验定位与公平性

- **将 continual long-term memory 作为当前研究方向。** 较早的 frozen G1 -> G2 experiments 仍可作为 baselines/diagnostics，但当前目标是让已完成任务为后续任务形成 memory。这更符合 ReasoningBank 的跨任务学习直觉。
- **保留 `agent_id`，不引入 shared cross-agent memory space。** 研究需要分别记录每个 agent 的 trajectories、memories 和 outcomes。跨 agent sharing 会混淆实验。
- **Domain 是软 relevance/provenance signal，不是硬 memory silo。** 任务可在 same-domain blocks 中运行，使相关 cases 有机会出现；但真正适用时仍允许 cross-domain transfer。
- **正式实验中禁止使用 hidden final-evaluation feedback 修复同一任务。** 这样会泄漏 benchmark answer。同任务 self-reflection 仅允许作为明确标注的 diagnostic，用于检验某个 reflection idea 是否可能有帮助。
- **每次付费 generation 前都必须给出 pre-run comparison table 并取得用户确认。** 表中必须说明 question、task、data/cases/DB、manual vs automatic selection、models、generation/evaluation calls，以及相对前一次运行的变更。

### Memory 内容与 provenance

- **使用 Candidate -> Active/Rejected admission。** 并非每条 trajectory 都会产生 memory；通常只有 active Experience/Skill 可检索。
- **Experience 和 Skill 按 knowledge type 区分，而不是按 source trajectories 数量区分。** Experience 是 lesson/observation/warning；Skill 是 reusable procedure/strategy。不得强制每个 Experience 都关联一个 Skill。
- **保留完整 provenance。** Consolidation 可以派生新知识，但不得删除、覆盖或重新编号 source memory。复用 `memory_sources`；不要仅为了 logs 增加 `memory_operations` table。
- **Similarity 只提出候选。** 它不能授权 automatic merge。semantic/evidence review 决定 KEEP/SUPPORT/CONSOLIDATE/REJECT。
- **Evidence 只对已相关候选排序。** consolidated status 本身不能提升不相关 memory。

### Reflection 与 prompt 方向

- **functional 与 appearance reflection 必须分开。** 二者依赖的 evidence 和 failure modes 不同。
- **具体 case 很重要。** “网站做得差”不是可复用 memory；有用的 case 应说明 trigger、expected state、observed failure/success、preventative action 与 verification。
- **当前 prompt-content 研究中人工选择 source cases。** 暂不优化 automatic embedding retrieval，因为其准确性尚不可信；否则 retrieval error 会与 memory-content quality 混淆。
- **预期注入路径：** selected historical case -> Memory LLM second reflection -> discard irrelevant portions -> current-task executable implementation pattern -> generator。原始 cases 不应是最终预期的注入形式。
- **generator 与 memory model 分工不同。** Memory LLM 负责 adapt/refine memory；generator 负责写网站代码。人工编写的 pattern 是 upper-bound prompt diagnostic，而不是 automatic Long Memory 的证据。
- **原始 requirement 必须保持可见且 binding，但有用的 implementation guidance 不能被表述为可忽略的 reference text。** 一次 `000015` diagnostic 表明，“reference only/lower priority” wording 会使 generator 忽略原本有用的 guidance。这是单次观察，不是普遍规律。

### 评测解释

- **在 evaluation data 中保留 failure reason。** 保留 raw transcript/evidence，并在可行时加入 structured failure stage/type/reason。区分 logic failure、interaction-budget exhaustion 与 evaluator/appearance limitations。
- **Partial 不自动等于 code bug。** 若 evaluator 在达到 target action 前耗尽允许的 interactions，应报告为 interaction-budget exhaustion。
- **screenshot appearance scoring 无法可靠证明精确 CSS named colours。** 如增加 CSS/computed-style checking，它应是 auxiliary compliance signal，而不是静默替换 benchmark appearance score。

### 2026-09-28：论文近似模型配置与新基线

- **将 WebGen-LM-7B + Qwen2.5-VL-32B + GPT-4o 设为一个独立、明确标记的论文近似 baseline。** 角色固定为：WebGen-LM-7B 生成网站；Qwen2.5-VL-32B-Instruct-AWQ 做功能/轨迹 GUI 评测；Azure GPT-4o 做截图外观评分；Azure GPT-4o + embedding 做 Long Memory 的改写、反思和检索。它不是“所有步骤均为 GPT-4o”的复现，也不应同旧 GPT-4o generator 基线混合报告。
- **No Memory baseline 必须使用 `--modes disabled`。** 它不能检索、注入 guidance、执行 post-task reflection，或写入可被后续任务使用的经验。runner 仍会初始化一个空 SQLite 文件，这是共用 runner 的 schema 前置条件，不是 memory write。
- **功能与外观 evaluator 的 endpoint 必须角色隔离。** `WEBGEN_FUNCTIONAL_EVALUATOR_*` 指向本地 Qwen-VL，`WEBGEN_APPEARANCE_EVALUATOR_*` 指向 Azure GPT-4o；不得退回到一个共享的 evaluator endpoint，否则会破坏论文近似的职责划分。
- **本地服务依赖 SSH local-forward，不能假定其跨 terminal/session 存活。** 每次正式生成前运行 `scripts/preflight_reflective_models.py`；只有 generator、memory/reflection、functional evaluator、appearance evaluator、embedding 五项均 PASS 才启动。文档仅记录 localhost 角色，不记录账号或密钥。
- **长任务不以终端流式输出作为健康标准。** Bolt/Selenium 不转发模型生成 token，任务完成前主 runner 输出很少。状态以输出目录的 artifacts 和 `progress.jsonl` 为准，并用只读 `scripts/watch_nomemory_webgenlm_14_21.sh` 观察；不能因静默就重复启动或覆盖同一 output。

### 2026-09 新增决策（换行 bug 之后）

- **Bolt 的 Enter 是发送，prompt 必须用 Shift+Enter 输入换行。** 2026-09-26 之前带换行的 prompt 只有第一段送达。证据：104 份聊天导出没有一份含 guidance，而 24 份 prompt 文件含有；两段消息实验中模型只回复第一段的要求。已修复（`_type_message`）。因此此前所有 Long Memory 生成实际只看到需求原文，其结果**不作为记忆效果证据**；旧 No Memory 基线（2026-09-21，单段需求）完整送达，仍有效。`prompt.txt` 与 `run_config.generation_prompt` 只是“打算发送”，实际接收以聊天导出为准，runner 用 `prompt_delivered` 核对。
- **基础约束（JSX 转义那段）默认不放进 prompt（`base_constraints_in_prompt=false`），两个组一致。** 它是我们手写的、与记忆无关的共用文字；旧基线没有它；换行修复后它会第一次真正送达，会混淆记忆效果。正式重跑时两个组统一决定带或不带。
- **Long Memory 的信息分三类，都不手写结论：** ① 按任务匹配的 guidance；② 通用池（所有 `[implementation]` case，不做相关性把关，按优先级取前几条改写成通用要求）；③ 统计块（只放事实和样本量，标注为相关性）。让系统当“老师”，由代码统计或模型总结产生结论，我们不直接写给 Long Memory。
- **统计记忆放在同一 DB 的可选表 `run_facts`、`check_facts`（只追加）。** `long_memory.py` 的 schema 校验放宽为“核心表严格，可选表不参与”，旧库仍可打开。每次运行记录技术栈（由生成项目的依赖检测）、是否构建成功、各检查结果、功能类别、原因标签及各标签对应的 failed/partial 次数、原因来源、需求是否写明。统计只用早于当前任务的数据。
- **失败的生成也产生记忆。** 构建未通过时记为 `execution_error` trajectory，检查计全 failed，反思出 `[implementation] Project builds and starts without errors` case，固定标签 `project did not build or start`（不由模型起名）；构建失败不写 `check_facts`（构建失败不等于功能失败）。
- **优先级 = 出现次数 × 严重度**：failed 检查 1.0，partial 0.5，构建失败按丢掉的检查数计；窗口为全部历史，半衰期关闭（0），指数 1.0；通用池 6 条候选中留 2 个名额给历史累计严重度最高的，最终取 3 条。数值都在 `config/long_memory.json`，可调。文献参考：Generative Agents（新近度+重要度+相关度相加）、ExpeL（重要度计数）、PER（优先级的 α 次方）、FMEA（严重度×发生度）；failed:partial=1:0.5 是我们自己的设计选择，不是文献值。**半衰期推迟：**等历史足够长再作为消融测试，用户认为它与课程学习的思路相近（简单问题随着模型变好而淡出）。
- **标签可信度原则：** 能客观判定的（技术栈、构建失败、原因来源、需求是否写明）由代码定；由模型起名的标签只用于排序和统计，并要做一致性检验和人工抽查（n=9 时两次分组一致率 100%，但有 1 条明显错标）。“复用已有标签”的规则会把不同问题硬套进旧标签（构建失败被套成校验类问题），所以生成失败不再交给模型标注。
- **整体反思（retrospective）：** 跨任务回看，输入是代码算出的统计表、项目结构事实和已有失败 case；产出的 case 引用的每个数字必须与统计表完全一致，否则丢弃；只追加，不改旧记录；以 `[implementation]` case 的形式存在，暂不写入 experiences 表。触发方式：按 domain block 结束或按任务数，样本量不足时不产出结论。首次结果：样本太少，未能推出“避开 Astro”。
- **可选诊断开关（默认关，仅 Long Memory）：** 构建失败重试时查记忆提示（`repair_hint`）、guidance 自检后补做一轮（`--guidance-selfcheck`）。自检补做会让 Long Memory 多一轮生成，若纳入正式对比，No Memory 需要做同样的自检；首次测试因换行 bug 无效，尚未在修复后测试。
- **评测异常要先核对：** 评测代理没有回复时，共用解析器会把该检查记为 failed（未改，因为属于共用评测逻辑）。发现 failed 先看 `interact_messages.json` 是否只有系统提示；确认是评测异常时可用 `scripts/reeval_single_check.py` 只补评该项，并写明修正原因。000020 r5 第 3 项即如此处理。

- **防同任务泄漏用“只排除当前任务自己”（leave-one-task-out），不按任务编号排时间顺序。** 跑哪个任务，检索（case、通用池）、统计和整体反思都排除该任务自己的数据，其余任务的数据不论编号大小都可读。任务编号只反映第一次执行的顺序，以后要做打乱顺序、任务间相互影响的消融。配置 `exclude_same_task`（默认 true）；阶段一会记录 `excluded_same_task` 的条数，可核对。重跑一个库里已有的任务不会读到它自己上一次的反思。

## SUPERSEDED 或 rejected 决策

- **“Bolt exported chat JSON 可能遗漏追加的 memory，`prompt.txt` 才是权威”：已被推翻。** 真实原因是换行截断，导出的聊天才反映模型收到的内容。
- **“`000015` diagnostic 表明 reference-only/lower priority 措辞使 generator 忽略 guidance”：撤回。** 当时 guidance 根本没有送达，这个结论没有依据。
- **此前所有 Long Memory 生成结果（含 000014 golden cases 的改善、14–19 chain、000018–000020 的 r1–r6）作为记忆效果证据：撤回。**
- **手写一条 Vite+React 的 guidance 作为上限诊断：撤回。** 结论应由系统从经验中得出，而不是人工注入 Long Memory。

## 本 session 新增证据

- **在 retrieval 尚未可信前，prompt-content diagnostic 使用人工选择 cases，并关闭 automatic retrieval。** 这样可以隔离“memory 内容/改写是否有用”和“召回是否准确”两个问题；这是实验方法决策，不代表最终 retrieval 架构。
- **Second-stage adaptation 必须以 task aspects 为硬约束，但允许迁移抽象原则。** 具体字段/动作（例如当前 requirement 未出现的 DOB）应拒绝；“格式要明确、错误要可见”这类抽象原则可保留。此前未使用 task aspects 的 adaptation diagnostic 错误保留 DOB guidance；aspect-gated 000014 由 2 pass/2 partial/1 fail 改善为 4 pass/1 partial/0 fail，但仍是单任务证据。
- **评测归因与原始 outcome 分离保存。** `interaction_budget_exhausted` 不等同于 logic failure；failure stage/type/reason 只用于归因，不覆盖原始 Pass/Partial/Fail。

- **跨 agents 的 shared `memory_space_id`：** 已拒绝，因为它与 agent-specific experiments 冲突。
- **hard per-domain databases：** 已拒绝，因为会阻止合理的 cross-domain transfer。domain blocking 是 execution organization，不是硬 storage boundary。
- **将 frozen-only G1/G2 作为主要方法：** 已被 continual memory 取代。旧 runs 保留为 historical baselines，不是 active method。
- **similarity-threshold direct merge：** 已拒绝；会带来 false merges 并破坏 provenance 的含义。
- **在 retrieval 中自动提升 consolidated memory：** 已拒绝；independent evidence 是 confidence，而不是 applicability。
- **将成功 trajectory 自动视为 positive、失败 trajectory 自动视为 bad memory：** 已拒绝。二者都可能根据 evidence 产生有效 lesson。
- **使用 WebGen-Agent-style hidden final evaluator feedback 反复修复 target benchmark task：** 未采纳到 long-memory formal comparison，因为会改变实验问题并可能泄题。short-loop/self-repair 仍可能是未来 ablation，但不属于当前 scope。
- **将 raw history verbatim 注入 prompts：** 已被 case -> adaptation -> implementation-pattern 方向取代，因为 raw examples 会引入无关细节（例如将 DOB lesson 注入没有 DOB field 的任务）。
