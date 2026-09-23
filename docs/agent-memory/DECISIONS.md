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

## SUPERSEDED 或 rejected 决策

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
