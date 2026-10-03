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
- **`accepted_reflection_count` / 每条 case 的 `accepted_for_memory` 不能当作内容可信度指标。** 它在 `_normalise_functional`/`_normalise_appearance`（`src/post_task_reflection.py`）里判定，只看模型这次有没有直接引用可解析的 `evaluation_result`/`chat_message` 编号；真正更可靠的代码/需求证据核实（`_ground_code_evidence`、`_ground_requirement_evidence`）发生在**之后**，不会回头更新这个标记。000018 的反思 `accepted_reflection_count=0`、`dropped_by_critique=0`，人工核对全部 4 条 functional case 的代码引用后确认内容和真实源码一致（1 条因引用片段里用“…”拼接不相邻代码行，被逐字校验器判为未验证，属于引用格式问题，不是内容错）。该标记不影响是否存库（`ReflectionCaseMemory.store()` 不读它），只是容易被误读为质量分；判断某条 case 是否可信，应看它每条 `evidence_refs` 自己的 `grounded` 字段，而不是这个聚合计数。

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

### 2026-09-29：服务器缩减后的硬件分工（Mac 本地生成器 + 服务器 A 评测）

- **背景：** 两台 5090 服务器被收回一台（视觉评测那台，`sc448961`），只剩生成服务器（`sc448960`，1×RTX 5090 32GB）。一张卡放不下两个模型：WebGen-LM-7B BF16 约 17GB（含 KV cache）+ Qwen2.5-VL-32B-AWQ 约 23GB（含 8192 上下文与图像），超出 32GB。
- **决策：服务器 A 只跑 Qwen2.5-VL-32B-AWQ 做功能评测；WebGen-LM-7B 生成器改在 Mac（Apple M5、24GB 统一内存）本地用 llama.cpp 跑 Q8_0。** 外观评分、memory/reflection、embedding 仍为 Azure，不变。
- **为什么不能“同一张卡分时”：** Long Memory 的任务 N 要读任务 N-1 的评测与反思结果，任务之间是同步阻塞的依赖链，不能先全部生成、再全部评测。
- **这是一个新的、必须单独标注的 profile：** 生成器由 vLLM + BF16 + 5090 变为 llama.cpp + Q8_0（8.50 BPW）+ Apple M5。它的结果不得与 5090 BF16 生成器的结果混合或直接比较；No Memory 与 Long Memory 两个 arm 都必须在这个新 profile 下运行，此前 BF16 profile 的 baseline 只作历史参考。
- **自己量化，不用第三方量化版：** 从官方 `luzimu/WebGen-LM-7B`（revision `99f749fb571b5f7069625c6fbbce00d2fb9c222c`）经 BF16 GGUF 量化为 `Q8_0`，无 imatrix、无校准数据、默认参数。理由是可复现、可追溯（工具版本、命令行、文件 SHA-256 全部可写进论文），并非第三方量化版被判定为不可信；对 Q8_0 这种简单分块量化，不同来源的结果差异预期很小。完整参数在 Mac 上的 `~/webgen-local-generator/QUANTIZATION_RECORD.md`（不在仓库内）。
- **Q8_0 而不是 BF16 / 4-bit：** 24GB 统一内存要同时容纳系统、Chrome（Bolt/Selenium）与模型；BF16 权重约 15GB 太紧，4-bit 质量损失更大。8-bit 权重约 8GB，留有余量。这只是内存估算，速度与内存压力尚未实测。
- **服务约定与服务器一致：** 模型名 `WebGen-LM-7B`、端口 8000、上下文 32768、只监听 127.0.0.1；生成器改在本机后，8000 不再需要 SSH 隧道，只保留到服务器 A 的 8001 隧道（Qwen-VL）。
- **探索阶段允许用 Mac Q8_0 接着跑现有 Long Memory batch 1，精度差异先不追究（用户 2026-09-30 决定）。** 理由：最终会在冻结的协议下整体重跑（No Memory 与 Long Memory 同一 profile）。代价必须记住：已有的 batch 1 链条（000015/000016/000014/000017）大概率由 5090 上的 BF16 生成器产生（依据是运行时间与当时的服务配置，运行元数据只写模型名 `WebGen-LM-7B`），从 000018 起换成 Mac Q8_0，同一条链里混了两种生成器，因此这批结果只能作探索、调试用，**不得作为记忆效果的证据，也不得写进论文的正式对比**。
- **付费 generation 前的 pre-run 对比表规则不变。** 用户说“接着跑”后，仍先做免费/低成本的就绪检查（隧道 + preflight），再给出对比表并取得确认才开始生成。

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

### 2026-09-30：Mac Q8_0 profile 正式升级为论文协议，并定下 101 任务的补齐+交替执行顺序

- **将“Mac 本地生成器 Q8_0 + 服务器 A Qwen2.5-VL-32B 功能评测 + Azure GPT-4o 外观评测/记忆/embedding”这条 profile，从此前标注的“仅供探索/调试”正式升级为论文使用的正式协议。** 此前（2026-09-29 决策段）明确写过“这批结果只能作探索、调试用，不得作为记忆效果的证据，也不得写进论文的正式对比”——该限制针对的是旧的 `longmem_ghtoken_batch1`（同一条链混用了 5090 BF16 与 Mac Q8_0 两种生成器）。用户 2026-09-30 决定：只要一条链自始至终只用 Mac Q8_0 生成器（不再混用 BF16），其结果可以正式用于论文对比，不再要求"等 protocol 冻结后从 000014 清零重跑"。
- **正式协议覆盖的两条链：** No Memory 用 `outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2`（`--modes disabled`）；Long Memory 用 `outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1`（`--modes continual --post-task-reflection --memory-representation case_only`）。两条链的 `run-metadata.json` 均确认 generator=WebGen-LM-7B（Mac Q8_0）、functional evaluator=qwen2.5-vl-32b-awq、appearance evaluator=webgen-appearance-evaluator-gpt4o，profile 一致，未再混用旧 5090 BF16 结果。
- **背景（为什么两条链任务集合此前不一致）：** No Memory 已经把 domain block 1（000014–000021，8 个）全部跑完；Long Memory 当时缺 000016/000017/000018（block 1 未跑全），但已经先跑了 block 2 的 000026/000027/000028，并在生成 000029 时被中断（进程消失，日志无报错、Mac 未睡眠、系统日志无 OOM 强杀记录，最可能是当时的终端/session 被关闭，而非代码或硬件故障）。
- **补齐阶段（一次性，不计入后续交替顺序）：** No Memory 补跑 000026/000027/000028；Long Memory 补跑 000016/000017/000018。跑完后两条链共同覆盖同一组 11 个任务：000014、000015、000016、000017、000018、000019、000020、000021、000026、000027、000028。补齐不违反 leave-one-task-out：跑哪个任务只排除它自己，其余已入库数据（不论任务号顺序）都可检索，所以 Long Memory 在已经有 019–021、026–028 之后再补 016–018，不影响其有效性。
- **从 000029 起严格按 manifest 顺序（跨 20 个 domain block，manifest.json 定义的插入序，不是任务号数字序）交替跑完剩余 90 个任务，且“谁先跑”本身逐任务交替，不固定谁先：** 000029 先 No Memory（生成+评测）、再 Long Memory；000030 先 Long Memory、再 No Memory；000031 再换回先 No Memory；以此类推，奇偶切换到 manifest 里最后一个任务 000095（第 101 个任务）。这样两条链在任意时刻查进度都停在同一个任务号上，避免再出现像本次一样两条链各跑漏了不同任务、进度无法直接对比的情况；交替谁先跑是为了不让固定的先后顺序（例如共享 Bolt/Chrome 状态、GPU 预热）系统性偏向某一条链。
- **该顺序由脚本固化（不手动逐任务敲命令）**，脚本与执行记录见 HANDOFF.md 对应条目。

### 2026-09-30：No Memory 零分任务的主因排查——大量“原封不动的脚手架”，疑似与 prompt 长度/具体度相关

- **背景：** 用户要求排查 (a) Long Memory 外观评分缺失（000019/000020/000027）的原因，(b) Long Memory 得零分任务的主因，(c) No Memory 大量零分任务的主因。以下结论基于直接核对**真正被打包评测的产出代码**（`extracted/.../src/App.vue` 等），而不是聊天导出 JSON——本 session 发现聊天导出 `000001.json` 的 assistant 消息内容与实际构建产物可以不一致（例如 000015 Long Memory 的导出文本是纯脚手架，但实际构建产物是完全定制的诊所网站），这是一个新的、尚未解释的导出/构建不一致现象，**分析产出内容必须以 `extracted/` 下的真实文件为准，不能只看 `000001.json`**。
- **(a) 外观评分缺失 = 构建失败，不是评测异常。** 000019、000020、000027（Long Memory）都只有 `.attempt-1.failed.zip`/`.attempt-2.failed.zip`，没有最终 `000001.zip`，`extracted/` 目录不存在。`000001.generation.json` 显示两次尝试报的是**完全相同**的 `vue-tsc` 严格类型检查错误（缺 import、未使用变量、组件方法类型不存在等），说明唯一一次修复重试没有真正改动代码。没有网站就没有截图，外观评分自然是空——不需要、也没法重跑外观评分；需要修的是生成/修复这一步本身。
- **(b) Long Memory 零分任务的主因 = 与 (a) 同源的构建失败，不是“反思没更新到新任务”。** 这些任务从未跑到任何功能交互，失败发生在生成阶段，memory/reflection 根本没有介入的机会。反思侧已经按项目既有规则正确产出了 `[implementation] Project builds and starts without errors` case（不写入 `check_facts`），memory 记录本身没问题，只是救不回当前这次构建。
- **(c) No Memory 零分任务的主因（新发现，样本量小，需要更多任务验证）：** 抽查全部 8 个已完成 No Memory 任务的真实产出代码，**5/8（000014、000015、000016、000017、000019）是与 `npm create vite -- --template vue-ts` 默认脚手架逐字节相同的未修改代码**（默认 logo、"count is 0"、默认配色全部原样保留），模型没有写任何业务代码；只有 3/8（000018、000020、000021）是真正的定制生成。抽查的 5 个 Long Memory 已完成任务（000014、000015、000021、000026、000028）里**没有一个是空脚手架**，全部有真实定制内容。
- **两边送入模型的 prompt 长度/具体度差距明显：** No Memory 的 prompt 结尾固定是一段内容为空的占位符（"Relevant Experiences\n[]\n\nRelevant Skills\n[]"，全长约 1000 字符）；Long Memory 的 prompt 同一位置是几百字的具体 implementation guidance、已知构建陷阱提醒、历史统计数字（全长约 3500 字符）。核对过 `prompt.txt`/`000001.request.json`，没有发现截断或格式错误的证据。
- **判断（非定论，样本仅 8+5，需要后续任务验证）：** 这个本地 Q8_0 量化 7B 小模型，在拿到“内容单薄、结尾是空占位符”的 prompt 时，相当比例（本次样本 5/8）会退化成直接抄默认脚手架，而不是尝试生成；拿到内容具体、带示例/陷阱提醒的长 prompt 时没有出现这种情况。这**可能不是代码 bug**（prompt 传输本身完整），更像是小模型对“单薄 prompt”不稳健的固有弱点。**这对论文叙事的含义：** Long Memory 相对 No Memory 的优势里，可能有一部分不是“教会了更好的实现方式”，而是“提供的具体文字内容本身防止了小模型摆烂/退化成脚手架直抄”——这两者都是 memory 的真实增益，但归因解释上要如实区分，不能笼统说成“记忆让模型写出了更聪明的代码”。**后续任务量增加后应重新核实这个 5/8 比例是否稳定，并检查是否存在两边 prompt 构造代码路径不一致导致的潜在 bug。**

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
- **（2026-09-29）在 Mac 上跑 Qwen2.5-VL-32B：** 已排除。AWQ 权重约 20GB，加图像与 KV cache 超出 24GB 统一内存可用部分，且 Mac 处理截图很慢。
- **（2026-09-29）单张 5090 同时放 7B 与 32B-AWQ：** 已排除。需把 7B 降到 FP8/AWQ 并卡死显存比例，既脆弱，又会改变生成器精度。
- **（2026-09-29）先全部生成、再切换模型全部评测：** 已排除，与 Long Memory 的任务间依赖冲突（见上）。
- **（2026-09-29）用 Colab 学生额度当评测服务：** 已排除。免费/学生档 GPU 通常放不下 32B-AWQ；会话有时长与空闲限制，断线会打断依赖链并造成输出目录与记忆库状态不一致；隧道稳定性也不如 SSH。学校额度的具体条款需自行核对，此条基于一般情况。
- **（2026-09-29）用 Claude Session Credits 部署自己的模型：** 不可行。额度只用于 Anthropic 模型调用，不提供 GPU，也不托管开源模型。

### 2026-10-01：guidance 压缩步骤（试验中，尚未纳入正式协议）

- **动机：** Long Memory 000016 主链 0.25（只写了首页）而 No Memory 0.50；注入的记忆约为需求原文的 5.7 倍（12 条：guidance + 陷阱 + 统计），guidance 遵守度 1/8。用户判断为“guidance 喧宾夺主”，盖过了需求本身。
- **做法：** `src/reflection_case_memory.py` 的 `condense_packet`：检索出的候选（case pattern + 通用池）交给 Memory LLM 合并压缩，**最多 5 条、总长不超过需求原文的 1 倍**；每条必须引用来源候选 id（provenance 保留在 `guidance_run_info` 与 `case_retrieval` 事件的 `guidance_condense`）；统计块不再原样注入，只供压缩时排序参考。配置 `guidance_condense`（默认 false）、`guidance_max_items`、`guidance_max_ratio`；诊断用 `config/long_memory_condensed.json`。
- **上限数值不是文献给定值。** 文献只支持“指令越多/上下文越长、遵守度和推理越差”的方向，没有标准比例；5 条与 1 倍是我们的设计选择，后续可做消融。
- **首次诊断（000016，DB 副本，不写主链）：** 压缩版 `outputs/experiment/diag_016_condensed`：prompt 3533 → 1231 字符，保留 3 条；功能 4 passed / 2 partial（两项均为评测交互次数耗尽）/ 0 failed = 0.83，外观 3。原样重跑 `diag_016_baseline`（prompt 3507 字符）：1 passed / 1 partial / 4 failed = 0.25，外观 3，与主链完全相同；代码只有 NavBar/HomePage/ContactForm，没有产品、新闻、关于页面，而压缩版生成了全部 5 个 view。说明 0.25 不是偶然，未压缩的长 guidance 会稳定地让生成器只写首页。仍是单任务、各 1 次的证据，需在更多任务上验证。
- **是否纳入正式协议待定：** 中途改变 Long Memory 协议会使链前后不一致，可能需要重跑已完成的 Long Memory 任务，由用户决定。
- **参考文献（写论文时引用）：**
  - Harada et al., 2025, *Curse of Instructions: Large Language Models Cannot Follow Multiple Instructions at Once*（同时遵守全部指令的概率 ≈ 单条遵守率的 n 次方）。
  - Jaroslawicz et al., 2025, *How Many Instructions Can LLMs Follow at Once?*（IFScale，指令数增加时遵守度下降）。
  - *ManyIFEval*（多指令遵守基准，与 Curse of Instructions 同出）。
  - Shi et al., 2023, *Large Language Models Can Be Easily Distracted by Irrelevant Context*（GSM-IC，无关上下文降低准确率）。
  - Du et al., 2025, *Context Length Alone Hurts LLM Performance Despite Perfect Retrieval*（仅上下文变长即降低表现）。
  - 作者/年份写作前需再核对原文。

### 2026-10-01：外观分解析修正（不影响已报告分数）

- runner（`scripts/run_stage1.py`）原正则 `Grade\s*:\s*([1-5])` 读不出 GPT-4o 常写的 `Grade: **3 (Average)**` / `**Grade:** 3`，导致运行记录里 appearance `score` 普遍为 None。已改为 `Grade\W{0,6}?:\W{0,6}([1-5])`。核对全部 174 个历史 `shots/result.json`：`scripts/generate_scorecard.py` 的解析与新正则读数完全一致，因此此前报告的外观分不受影响；记忆/反思不读该字段。旧记录已用 `scripts/backfill_appearance_grade.py` 补全（备份后缀 `.before-grade-backfill`）。

### 2026-10-01：压缩正式启用于 Long Memory 链；重跑的 trajectory 修复；“缺失功能”反思规则

- **Long Memory 链从 019 重跑起启用压缩**（用户决定）：`catchup_remaining.sh`、`paper_protocol_phase2.sh` 的 Long Memory 命令加 `--memory-config config/long_memory_condensed.json`；`config/long_memory.json` 保持原样（No Memory 读它，配置指纹不变）。Long Memory `run-metadata.json` 的 `memory_config_sha256` 已改为压缩版，原文件备份 `run-metadata.json.before-condense`。排错阶段只重跑低分/构建失败任务（019、021，以及 020/027/028 构建失败），014/015/026 保留旧结果；因此该链混有压缩前后结果，只作排错，正式论文结果需在做法定下后统一重跑。
- **重跑原 Long Memory 任务的步骤：** 备份 DB → 旧 trajectory 的 `reflection_cases` 置 archived、派生 experience 置 rejected/archived、删除其 `run_facts`/`check_facts`/`case_supports` → 从 `progress.jsonl` 去掉该任务 → 任务目录改名 `*.pre-condense-backup`。
- **bug（已修）：重跑没有新建 trajectory。** `upsert_trajectory` 按 `trace_path` 查找，目录改名后新运行路径与旧的相同，于是复用旧 trajectory，只更新 evaluation，`run_config` 里仍是旧 prompt。现在只有压缩包 sha256 也相同时才复用。019 已拆分：旧 `eead5acd…`（attempt 1，恢复旧评测）、新 `0d3c8a82…`（attempt 2，压缩 prompt 1596 字符，7 条新 case 与统计已移过去）。`memory_sources` 不可改，新 experience candidate `a4c142b6…` 的 2 条来源仍指向旧 trajectory（candidate 不参与检索）。审计其余 trajectory：无同类问题。
- **反思“缺失功能”规则：** 019 的“客户案例”检查失败，真实原因是网站没有该版块，但反思按“话题纪律”只能写评测员实际点过的新闻 Read More，归因错位。`FUNCTIONAL_CASE_INSTRUCTIONS` 新增：若代码中不存在该检查要求的功能，缺失本身即 established cause，需引用缺少它的导航/路由代码；评测员误点的无关控件不在此检查归因。

### 2026-10-01：prompt 长度统计；016 两次压缩结果相差大的原因

- **`run_facts.prompt_stats`（JSON，由代码计算）：** 需求字数、注入记忆字数、记忆/需求倍数、guidance 条数、是否压缩及压缩前候选数、留下条数、字数上限与实际字数。`memory_chars` 含固定标题与说明（约 200 字），所以倍数会略高于压缩上限 1.0。旧数据已用 `scripts/backfill_prompt_stats.py` 补算并导出 `outputs/experiment/prompt_length_analysis.csv`（含已归档旧版运行）。用途：论文中“注入长度 vs 得分”的分析和压缩消融；注意长度与 guidance 内容同时变化，观察数据只能说明相关，因果结论需在同一任务上只改长度做受控对照。
- **“正式链”与“诊断副本”的区别：** 诊断副本 `diag_016_condensed` 是把当时的 Long Memory `memory.db` 复制一份单独跑，结果不写回正式链，跑时库里还是 019/021 重跑之前的旧经验；正式链是 `longmem_mac_q8_19_21_then_remaining_r1` 本身，016 跑时库里已有 019/021 重跑后的经验，且旧 021 反思已归档。
- **两次压缩版 016 相差大（诊断 0.83 vs 正式链 0.17）的原因：** 不是生成模型的随机性（本地模型在相同 prompt 下几乎确定输出），而是**两次 prompt 里的 guidance 不同**，源于两次跑时记忆库状态不同。诊断那次通用池有 1 条“交互后更新的内容要显示在可见位置”，模型在 `App.vue` 写了一排导航按钮，各页面都能进；正式链这次通用池为空，5 条 guidance 中 3 条写“放在单独页面（dedicated view）里”，模型建了独立路由，但 `App.vue` 只有 `<RouterView />`、首页没有任何链接，5 项检查都因找不到页面而失败。guidance 各条本身都准确、相关（背景色、表单、详情），问题在于**缺少“每个页面要有导航入口”这一条**——这是覆盖面问题，不是准确度或相关度问题。
- **通用池变空是重跑归档的副作用：** 通用池只取 `[implementation]` case，且整个库至少要有 2 个不同任务贡献才启用（`min_tasks=2`）。重跑前恰好是旧 021（“导航中的页面要挂载”）与 027（“事件函数声明、数组类型”）两个；旧 021 归档后只剩 027，整个通用池为空。在当时的库里没有可用的导航经验，016 学不到，符合预期。
- **016 正式链的反思已补上该经验：** 4 条 active 功能 case 都要求“每个内容版块都要有可见的导航入口、从首页可达”（另 1 条同内容因 uncertain 归档）。但它们是功能 case 而非 `[implementation]`，不进通用池，只在新任务有相似功能时被检索；导航/联系/新闻几乎每个网站都有，预期多数后续任务能匹配到。4 条内容高度重复，靠压缩步骤合并。**后续要核对：** 之后任务的 prompt 中是否出现导航入口这一条，以及“页面写了却无入口”是否不再出现。
- **“页面写了却没有导航入口”是该 7B 模型的高频错误：** 出现在 No Memory 021、旧 Long Memory 021、正式链 Long Memory 016。
- **待用户决定的两个修法：** (1) 不改，让 016 这次失败的反思重新产出该经验（符合“结论不手写”）；(2) 修改重跑归档规则，使通用池经验在旧运行归档后仍保留来源支持。尚未实施。
- **同一任务单次结果波动大**（016 压缩版两次 0.83 / 0.17，虽然原因是 guidance 不同而非随机性），论文正式结果可能需要每任务多次运行或固定记忆库状态做对照，待用户决定。

### 2026-10-01：每个 pair 的标准分析流程（用户要求，之后每个任务都按此做）

每个任务两臂都跑完后，先出 `scripts/compare_task.py <id>` 三栏表（No Memory / Long Memory 压缩 / 未压缩，如有），然后对 **Long Memory 压缩版每一项 failed 和 partial** 按下面顺序逐层归因，前一层没问题才看下一层：
1. **检查本身：** 失败原因是网站真缺陷、功能缺失、评测的隐藏要求（需求没写）、还是交互次数用完未验证。对照 `extracted/` 代码确认。
2. **检索（相关度）：** `memory-events.jsonl` 里该任务的 `case_retrieval` 事件——任务拆出的 aspects 是否覆盖了这项检查对应的需求；库里有没有能防住这个问题的 case；有的话是被 reject、还是 match 了但没被 `selected`（注意同一 case 被重复选中占名额）。
3. **改写/压缩（准确度）：** `implementation_adaptations` 与 `guidance_condense.items`——改写后的 pattern 是否保留了原 case 的要点，压缩是否删掉了关键一条。
4. **prompt（表达）：** 最终 prompt 里的 guidance 措辞是否误导或相互冲突（如“所有版块首屏可见”与“一页式滚动”冲突，“放在单独页面”导致只建路由不加导航）；模型是否照做。
5. **反思（是否符合预期）：** 该任务新写入的 `reflection_cases`——每项 failed/partial 是否都有对应、归因是否对（对照代码）、有没有写到已 passed 的检查上、uncertain 归档是否合理、有没有产出能防住下次同类问题的经验。
结论按“检查本身 / 检索 / 改写压缩 / prompt / 反思”五类给用户，并指出哪些需要改代码或指令。

- **000017 按此流程的发现（Long Memory 压缩 0.58 = No Memory 0.58）：** (a) 网站没有“活动介绍”版块（需求列出），且做成标签页而非一页式，介绍/优惠无导航入口；(b) 检索：任务拆解的 3 个功能 aspect 没有覆盖“介绍”版块；016 新产出的导航 case `47f2c1bc` 被判 soft_transfer 但未入选，而新闻导航 case `dd799df5` 被重复选中两次占名额；(c) 改写：`dd799df5`（“新闻要有可达入口”）被改写成“版块滚动到时可见”，丢掉了“要有导航入口”的要点；(d) prompt：“轮播/评价/公司信息都要首屏可见”可能促使模型改用标签页，与“一页式”冲突；(e) 反思：介绍缺失归因正确；轮播没有定时器归因正确（代码确认）；但写了一条“评价文字不可见”的 partial，而评价检查实际通过，属于归错检查；导航 partial 没有对应 case。待改：选中去重、改写保留要点、反思的检查对应。
- **已实施的三处修改（2026-10-01，对之后启动的任务生效，Long Memory 018 已在旧代码下启动）：** (1) `select_cases`：每个 aspect 仍只选 1 条，但优先选未被其他 aspect 选过的 case（同一查询的多个 aspect 之前都拿同一条最高相似度 case，挤掉了其他相关经验，如 017 的导航 case `47f2c1bc`）；(2) `CASE_IMPLEMENTATION_ADAPTATION_INSTRUCTIONS`：改写必须保留原 case 预防动作里“缺失的那个元素”（导航入口、提交处理、轮播定时器等），不得换成更弱的可见性条件；(3) `FUNCTIONAL_CASE_INSTRUCTIONS` 新增 “Check identity”：先从首条 tester 消息读出本检查的任务，feature_object 必须是该任务的功能，路过其他功能时看到的问题不写在本检查下，否则返回 null。
- **选择机制说明：** 每个功能/外观 aspect 按向量相似度取候选 → Memory LLM 判 hard_match / soft_transfer / reject → 每个 aspect 选 1 条（先 hard_match，再 soft_transfer，按相似度顺序取第一条）→ 每个 (case, aspect) 改写一次 → 统计排序 → 压缩。

### 2026-10-01：全站性经验进入通用池（scope=site_wide）；不在需求拆解里固定加导航
- **决定：** 功能反思新增 `scope`（`site_wide|feature`）。对几乎任何网站都成立的结构性经验（需求列出的每个版块都要存在且有导航入口、导航切换到的视图必须渲染）标 `site_wide`，存为 `[implementation]` case，进入通用池；通用池不靠功能相似度，按“出现次数 × 严重度”排序。原因：017 中 016 的导航经验相似度只有 0.50–0.55，与其他候选几乎无差别，且它不是某个功能的经验，按功能相似度检索会排不上去。
- **否决：** 在需求拆解中固定加入“导航/版块覆盖”aspect——等于把结论手写进系统（用户判断“太刻意”）。重要性应由通用池的出现次数 × 严重度排序自然体现。
- **016 反思已按新规则重做：** 5 条功能 case 全部标为 site_wide，通用池启用（016 + 027 两个任务），导航经验已是通用池候选。注意 5 条里都混有一部分功能细节（如“联系表单要可见”），后续观察通用池改写能否只保留全站部分。
- **000018 分析（Long Memory 0.33 vs No Memory 0.67，018 在上述修改前启动）：** 网站只有一个 `LandingPage`，无导航、无“服务状态查询”版块。guidance 第 1 条“落地页展示所有内容，无需导航”（由外观 case 改写而来）与评测的导航检查直接冲突，模型照做后导航、服务链接两项失败——属改写/prompt 问题；状态查询在 guidance 中列出但模型未实现——模型未遵守；预订失败为交互次数耗尽。反思：状态缺失、服务入口、预订按钮归因合理；“无导航”一条被标 uncertain 归档，但代码可证实无导航，应为 established。

### 2026-10-01：去掉代码写死的“首屏展示所有功能”外观 aspect；改写不得把限定说法变绝对
- **原因（000018 追查）：** `_aspects` 原本固定追加外观 aspect“landing page / first screen visibly presents the required features: …”，是手写设计假设。018 中它检索到信用修复任务的外观 case（原文“表单与服务介绍要出现在首屏，**不要只藏在导航后面**”），改写成“落地页展示全部内容，**不需要导航**”，压缩后排第一，模型做成无导航单页，导航与服务链接检查失败；017 的“轮播/评价/公司信息都要首屏可见”同源。
- **修改：** 删除该固定 aspect；`CASE_IMPLEMENTATION_ADAPTATION_INSTRUCTIONS` 增加：保留原 case 的限定语，不得把有限定的说法改成绝对说法，不得加入与当前需求或其他 guidance 冲突的要求（如取消导航）。
- **重跑：** 这两处只影响生成前的检索/改写，不影响反思，因此 016 不需重做（其反思已按 site_wide 规则重做）。Long Memory 017、018 已归档重置，020（旧代码刚开始生成即中止，目录 `tasks/000020.aborted-old-code-backup`）重跑；队列 `outputs/experiment/full_queue_2026-10-01_after_first_screen_fix.txt`，从 L:000017 开始。

### 2026-10-01：通用池冷启动与泛化
- **更正：** 通用池并非“至少 2 个任务才启用”。实际是最多 6 个候选：出现在 ≥2 个任务的“广泛”经验，加 2 个“保底”名额给严重度最高者（不要求出现次数）。此前保底名额只在统计排序启用时才给，否则为 0，导致冷启动时通用池为空。
- **修改：** (1) 保底名额不再依赖统计排序；统计尚不可用时按最新的 `[implementation]` 经验填；(2) 保底名额每条经验（按 `implementation_breadth` 的分组）只取一份，避免同一任务同一经验的多份副本占满名额（016 的 5 份导航经验曾挤掉 027 的经验）；(3) `COMMON_POOL_ADAPTATION_INSTRUCTIONS` 增加泛化：只保留对任何网站成立的部分，删掉夹带的功能细节；条件句只用于搭建方式（setup、数据流、渲染），不能用来保留某个功能的行为。存库的原始 case 不改，泛化只在进入通用池改写时进行。
- **实测（正式链当前库）：** 通用池输出 2 条：“每个主要内容版块都要有自己可达的导航入口或路由”；“Vue 模板事件处理函数在同一 `<script setup>` 中声明，响应式数组显式类型”。功能细节（产品详情、新闻文章）已去掉。
- **016 的 5 条都标 site_wide 是否符合预期：** 方向符合（5 项失败同一根因）。夹带的功能细节由上面的泛化处理；更彻底的“反思时拆成 1 条全站 + 若干功能”需要反思同时看多项检查，暂不做，先观察。

- **000017 重跑（去掉首屏 aspect 后；Long Memory 0.33 vs No Memory 0.58）：** 通用池的导航经验生效（“每个主要版块都要有可点击的导航入口”），导航检查由 partial 变 passed。新的主因：Vite 默认 `src/style.css` 未删，`:root { color: rgba(255,255,255,0.87) }` 让评价、公司信息、介绍的文字在浅色卡片上是白字，评测员看不到内容，3 项判 failed（代码中数据和挂载都正确）。与 019 旧版的白字问题同源。检索/改写/prompt 本身无误，但库里没有“删除或覆盖脚手架全局样式（白字、深色背景）”这条全站经验。反思：都抓到“文字看不见”，但只写成“提高对比度”，没有点出 `style.css` 的继承白字这一根因，也没标 site_wide。待查：反思收到的 `code_manifest`/代码文件是否包含 `src/style.css`。
- **跟进（017）：** 反思收到的代码里本来就有 `src/style.css`，但模型没把“文字看不见”联系到它。`FUNCTIONAL_CASE_INSTRUCTIONS` 截图段增加具体步骤：数据在代码里却看不到文字时，查全局样式表 `:root/body/#app` 上未被覆盖的 `color`/`background`；找到即为 established 原因，引用该规则作 code_evidence，经验写成“替换或删除脚手架的全局颜色”，scope=site_wide。泛泛的“提高对比度”不算 established。

### 2026-10-01：全站经验的选择规则；脚手架全局样式的代码检测
- **用户担心“全进通用池会掏空功能池”。** 改为：一个任务里被标 site_wide 的经验，由 Memory LLM 按“是否同一结构性根因”分组（`SITE_WIDE_CHOICE_INSTRUCTIONS`，`_choose_site_wide`），每组只留 1 条最纯粹关于整站、不针对单一功能的经验作为 `[implementation]` 进通用池（记录 `site_wide_choice_reason`），其余改回功能经验，继续按功能相似度检索。不同根因各留一条，不会因为数量上限丢掉。未按任务硬性限数。
- **016 按此重存：** 5 条中选出“site navigation to the company information, product…”为全站经验，其余 4 条（公司介绍、产品、新闻、联系）为功能经验。
- **脚手架全局样式检测（代码事实）：** `global_style_findings`（`src/long_memory_integrations.py`）报告哪些全局样式表在 `:root/html/body/#app` 上设浅色文字或深色背景，以及是否被入口文件引入；放入反思证据 `code_manifest.global_style_findings`。全部已生成项目都残留 Vite `style.css`（白字 + #242424），约半数被引入（No Memory 8 个中 4 个，Long Memory 7 个中 4 个），两臂共有。当前 019（attempt 2）的 `style.css` 未被引入，所以白字只在 017 当前运行中生效；019 无需重做反思。
- **未解决：** 即使给出该事实，gpt-5.4-mini 重做 017 反思时仍只写“提高对比度”，未引用 `style.css`、未标 site_wide（v2、v3 两次均未替换入库）。待用户决定是否像构建失败一样，由代码在“检测到被引入的白字全局样式 + 有检查因内容不可见失败”时直接产生固定标签的 `[implementation]` case。
- **000018 重跑（Long Memory 0.17 vs No Memory 0.67）：** 通用池这次已产出导航经验（“每个主要版块都要有可达的导航入口”），但**压缩步骤把通用池的 3 条全部删掉**，最终 4 条都是具体功能（预订、状态查询、联系、背景色）。网站有顶部导航，但只有 Book Now / Check Status / Contact Us，缺 Home 和 Services（需求列出服务详情）。另外 `style.css` 被引入（白字 + #242424），联系页“Phone:/Email:”后面的号码与邮箱是白字看不见，判 failed。预订按钮失败、状态查询交互次数耗尽。主因：压缩删掉通用经验（压缩问题）+ 脚手架白字（经验缺失）。018 在通用池泛化修改之前启动。
- **000018 深查（为什么 Long Memory 0.17 反而低于 No Memory 0.67）：**
  - **guidance 收窄了模型的范围：** 压缩前 8 条候选（5 条功能：服务详情、预订、状态查询、联系、背景色；3 条通用池含导航），预算 461 字（=需求长度×1.0），只留 4 条：预订、状态查询、联系、背景色。**“服务详情”和全部通用经验被删。** 模型恰好只做了 guidance 列出的三个功能（Book Now / Check Status / Contact Us 三个 tab），没有 Home、Services；No Memory 没有 guidance，按需求原文做了 Home/Services/Book/Inquiry/Contact 五个入口。这是“guidance 喧宾夺主”的另一种形态：不是太长，而是**列出的子集被模型当成了全部范围**。
  - **压缩删掉通用经验与服务详情的原因（推断）：** 压缩指令写有 “drop generic advice” 与 “drop anything already stated in the requirement”，导航类通用经验可能被当作 generic，服务详情被当作需求已写；预算 461 字只容得下约 4 条 ~110 字的句子。
  - **白字：** 两臂都引入了 Vite `style.css`（白字 + #242424）。No Memory 在 `.content` 等容器上显式设了文字颜色，所以没受影响；Long Memory 的联系页 `<p>` 没设颜色，继承白字。属于偶然，不是记忆导致。017 反思出的“提高对比度”经验是功能 case（评价、公司信息），018 没有这些功能，未被检索到，没有迁移。
  - **用户否决由代码直接写白字经验：** 违背“由 Long Memory 自己反思得到”的初衷（参考的是 WebGen-Bench 的评测设置，不是 WebGen-Agent 的人工规则）。代码检测事实 `global_style_findings` 仍作为证据提供给反思。
  - **待讨论：** 压缩时通用/功能的比例（给通用池保留名额）；压缩只缩字数、不删条目（每条都保留、各自写短）作为另一种方案对比；guidance 头部是否需说明“只是补充，需求列出的功能都要做”。

### 2026-10-01：反思只给通用排查方法，不给具体结论（用户确认的原则）
- **原则：** 可以教排查方法（看代码、看报错日志、顺着样式从元素→父容器→全局样式表追查、按原因所在位置判断范围），不能给具体问题的答案（如“删除脚手架全局颜色”）。人写的结论只能作为标注清楚的上限诊断。
- **已撤回的引导：** 反思指令中“经验写成替换或删除脚手架全局颜色、标为 site_wide”以及 scope 的具体例子（导航入口、继承白字）；`SITE_WIDE_CHOICE_INSTRUCTIONS` 的具体例子。曾按引导版存入的 017 反思（v4）已被替换。
- **现在的通用规则：** 截图看不到但代码有内容时，按元素自身样式→父容器→入口文件引入的全局样式表逐层追查，引用最终决定显示的规则；scope 按原因所在位置判断（入口文件、全局样式表、路由/导航、根布局等所有页面共享的部分 → site_wide）。
- **代码事实改为中性：** `code_manifest.global_style_rules` 列出入口文件引入的全局样式表在 `:root/html/body/#app` 上的全部声明（含 `@media` 条件），不再只挑白字/深色背景。
- **评测浏览器为深色模式：** 017 截图外围为 `#242424`，说明 Vite `style.css` 的深色主题（白字）在评测时生效；浅色模式下的 `#213547` 不生效。
- **017 干净版反思（v6，已入库）：** 一条自己引用了 `style.css` 的 `:root { color: rgba(255,255,255,0.87) }`，经验为“内容区设置不依赖页面主题的文字样式”；但仍标为 feature，未按原因位置判为 site_wide，因此不会迁移到没有同类功能的任务。如实记录为当前反思模型（gpt-5.4-mini）的局限；更强反思模型可作为论文消融变量。

### 2026-10-01：压缩改为“先缩字数再删条目”，通用池第一条保底；guidance 开头声明需求全部要做
- **压缩指令：** 删去 “drop generic advice” 与 “drop anything already stated in the requirement”；改为优先缩短措辞，只删重复或不适用的；“common pitfall” 类至少保留第一条。代码兜底：若压缩结果没有引用通用池候选，用通用池第一条替换最后一条（或在有余量时追加）。
- **guidance 开头：** “The requirement above remains binding: build every page and feature it lists, including those not mentioned below… only add how to implement parts of it”。原因：018 中模型只实现了 guidance 列出的子集。
- **预览工具：** `scripts/preview_guidance.py --output <链> --task-id <id> --log <单独日志>` 只跑检索/改写/通用池/压缩（第一、二阶段），只读记忆库，日志写到单独文件，不污染 `memory-events.jsonl`。018 预览：导航通用经验排第一，5 条 420 字；“服务详情”仍因 5 条上限被删。
- **000020（Long Memory，修改前代码）：** 0.40 / 外观 4 vs No Memory 0.50 / 3，尚未逐项分析。

### 2026-10-01：经验分池改为单独的路由步骤
- **原因：** 写反思时顺手填 scope 不可靠（017 引用了 `style.css` 的经验仍被标 feature）。
- **做法：** `route_scope`（`src/post_task_reflection.py`）对每条功能经验单独调用一次 Memory LLM，只判断“同一原因会不会影响其他页面”（`SCOPE_ROUTING_INSTRUCTIONS`，通用标准，无具体答案）；附带代码事实 `code_evidence_from_shared_file`（代码证据是否来自入口文件、根组件、路由或被入口引入的全局样式表），只作证据不作答案；理由记入 `scope_reason`。之后仍由 `_choose_site_wide` 按根因去重，每组只留一条进通用池。
- **017（路由后）：** 引用 `src/style.css` 的那条判为 site_wide（进通用池），其余 3 条原因在组件内，为 feature。
- **016（路由后）：** 路由把 4 条判为 site_wide（原因在共用的 `src/router/index.ts`），新闻那条判为 feature（路由里有 `/news`）；去重后只留“全站导航”1 条进通用池，其余 4 条为功能经验。
- **018 预览（路由后）：** guidance 5 条中两条来自通用池：“所有文字与背景有足够对比，结构化面板显式定义文字样式”（来自 017）和“所有版块都要有导航链接”（来自 016）；状态查询那条因 5 条上限被删。
- **000018 路由后重跑：Long Memory 0.67 / 外观 3 = No Memory 0.67 / 3（同一任务此前 4 次为 0.33、0.17、0.17、0.08）。** guidance 含两条通用经验（导航入口、文字对比度）。导航、服务列表、联系方式（这次无白字）、配色均通过；失败：预订（交互次数耗尽）、状态查询（未实现——压缩 5 条上限把它挤出 guidance，开头声明也未能补上）。反思：状态查询缺失被路由判为 site_wide 进通用池，理由需核对；属于缺失单一功能，按标准应为 feature。

### 2026-10-02：需求优先的 guidance 开头；压缩上限 6 条、1.5 倍；路由“缺失功能算 feature”
- **guidance 开头改为：** 需求优先，列出的每个页面和功能都要做；下面的说明**不是要做什么的清单**，只是之前网站容易出错的地方；需求列出的功能即使没有说明也要做。原因：No Memory 能做到的，加了 guidance 反而漏做（018）。
- **压缩上限：** `guidance_max_items` 5→6，`guidance_max_ratio` 1.0→1.5（`config/long_memory_condensed.json`；Long Memory `run-metadata.json` 指纹已更新，备份 `run-metadata.json.before-max-items-6`）。018 预览显示真正卡住的是字数（1.0 倍=461 字只容 4 条），不是条数。文献只说明条数越多遵守度越低，没有给出界限；6 条/1.5 倍仍是设计选择，可做消融。
- **路由补充：** 只是缺了某个页面或功能时，即使证据引用的是共用文件（如路由列表），也属于 feature；site_wide 只给共用文件里本身让多个页面出问题的规则或设置。
- **018 第一、二阶段预览（改后）：** 7 候选→6 条，434/691 字：导航（通用）、服务详情、联系、背景色、预订确认、状态查询——需求功能全部覆盖；但通用池第二条“文字对比度”被删（只保底第一条通用经验）。
- **队列：** 018 生成前先跑不受影响的 No Memory 026/027/028。

### 2026-10-02：guidance 与需求的关系——文献与对策（讨论中）
- **文献（已核对出处）：**
  - Du, Tian et al., 2025, *Context Length Alone Hurts LLM Performance Despite Perfect Retrieval*，Findings of EMNLP 2025，arXiv:2510.05381。即使完美检索、无干扰，仅输入变长就会降低表现（Llama-3.1-8B 在 30K token 时 MMLU 降 24.2%）。支持“控制注入长度”。
  - Liu et al., 2024, *Lost in the Middle: How Language Models Use Long Contexts*，TACL 12:157–173。信息在开头或结尾时最好用，在中间最差。支持“需求放最前、末尾再提醒一次”。
  - Wallace et al., 2024, *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions*，arXiv:2404.13208。模型被训练成按来源优先级遵守指令。支持在 prompt 中明确“需求优先、guidance 只是补充”。
  - Shi et al., 2023, *Large Language Models Can Be Easily Distracted by Irrelevant Context*（GSM-IC），ICML 2023。无关内容分散注意力。
  - 条数类（Curse of Instructions、ManyIFEval、IFScale）：出处待核对。
- **问题：** 018 中 guidance 列出部分功能后，模型把 guidance 当成要做的全部范围，漏做需求里的其他功能。
- **对策候选：** (1) guidance 只写“怎么做容易错的部分”，每条锚定到需求里的某一项（“对需求中的 X：…”），不单独写“实现 X”，避免看起来像功能清单；(2) 通用/功能名额分配：通用 ≤2、功能 ≤4，总数 ≤6；(3) 开头已声明需求优先、guidance 不是清单；可在 guidance 末尾再加一句“需求中的每个功能都要实现”（利用首尾位置效应）；(4) 后续做消融：固定条数改长度、固定长度改条数，指标用“需求功能完成数”。
- **隧道：** 在校园网内无需 VPN 即可直连服务器 A；8001 隧道会自行断开，已加 `scripts/keep_tunnel.sh`（每 30 秒检查并重连，日志 `outputs/experiment/tunnel_keeper.log`）。
- **三条对策已实施（2026-10-02）：** 压缩指令要求每条以“对需求里的 X：…”开头、通用 ≤2 条（代码保底前两条通用经验，缺的替换最后一条功能项）、guidance 末尾加“需求列出的每个页面和功能都要实现”。018 预览：8 候选→5 条（622/691 字），导航与文字对比度两条通用经验保住、末尾提醒生效；但模型没有按“对需求里的 X”格式写，服务详情与状态查询被字数挤掉，靠开头/末尾声明兜底。guidance 改写继续由独立的记忆模型（GPT-4o）做：评测模型会泄露评分标准，7B 生成器改写能力弱且占用 Mac 生成时间（7B 自我改写可作消融）。

### 2026-10-02：修复回复被截断（Bolt 5 分钟超时）；构建失败不再整体重试
- **现象：** No Memory 026 的 5 次修复，Bolt 聊天记录里修复请求一条回复都没有，6 个失败包内容相同。生成器日志显示每个请求约 5 分钟被调用方取消（`cancel task`），被原样重发 3 次。
- **原因（已实测）：** Bolt 在修复前做“上下文优化”（`createSummary`/`selectContext`），是非流式调用；Node.js 内置 fetch 默认 300 秒收不到响应头就超时（`UND_ERR_HEADERS_TIMEOUT`），AI SDK 默认再重试 2 次。首次生成对话短，不触发；只有修复阶段受影响。实测：默认 301 秒报错，加载修改后 330 秒正常。
- **修复：** 仓库外 `~/webgen-local-generator/bolt-preload/long-timeouts.mjs`（undici `setGlobalDispatcher`，headers/body 超时 30 分钟），`scripts/start_bolt_provider.sh` 通过 `NODE_OPTIONS=--import` 加载；两臂相同，不改 Bolt 代码。30 分钟而非 1 小时：修复回复约 5–14 分钟，且短于 runner 的 2700 秒等待。
- **影响范围：** 两条正式链当前保留的结果中只有 No Memory 026；Long Memory 020/027/028 的旧失败已归档（更早的批次同时受换行 bug 影响，不单独归因）。
- **构建失败不再整体重试（`run_with_retries`）：** 修复次数用完后直接记为构建失败；整体重试只留给浏览器/Bolt 基础设施故障。原因：temperature 0 下重新生成得到相同项目，每轮白花约 40 分钟并覆盖上一轮的构建记录。两臂共用。
- **修复后 No Memory 026：** 修复回复正常送达，代码确实在改（报错从 `App.vue`/`Poll.vue` 变为 `PollList.vue`），但仍过不了 vue-tsc 严格检查；这是模型能力的真实结果。

### 2026-10-02：反思质量——分步排查、可信度一致性、回归集
- **起因：** Long Memory 018 预览中“服务详情放首屏”一条来自 014 的旧反思（9/29）：检查实为评测员交互次数用完，反思把猜测（appears）写成经验，并以 active 进库。当时 prompt 没有 `cause_confidence`。同类“首屏”思路曾由代码写死的 aspect 引入，已于 10/1 删除。
- **核对 014 代码：** 服务介绍并不缺失（`ServicesView.vue` 有标题与带描述的卡片）；`.service-card` 白底未设文字颜色，继承入口引入的 Vite `style.css` 白字（评测浏览器为深色模式），所以看不见。三次反思（旧版、当前、加措辞规则）都没归因到 `style.css`；当前版只在一次中看到“文字看不见”。017 也只在 v6 一次自行引用到 `style.css`。**结论：** 反思模型（gpt-5.4-mini）能看到“看不见”，但很少追到全局样式表；库中 017 的对比度通用经验是一次合法但不易复现的结果，Long Memory 026 等任务若因它避开白字，只能说明“库里有这条经验时有用”，不能说明能稳定学到（假阳性风险，论文需如实说明）。
- **可信度与措辞不一致：** 标 established 的原因仍用 appears 等措辞；只在 prompt 里加规则，模型不遵守。可选：代码机械检查（出现 hedge 词即改 uncertain），未实施。
- **分步排查（用户提出，通用方法，不给答案）：** `FUNCTIONAL_CASE_INSTRUCTIONS` 要求先按步骤填写 `investigation`：task → reached_target（评测员是否真的到了目标）→ screenshots → errors → code_path（路由→入口→挂载→数据/处理→渲染，逐环）→ style_trace（仅“代码有内容、截图看不清”时：元素→父容器→入口引入的全局样式表）→ candidates（列 2–3 个可能原因并逐一用证据排除）→ conclusion → fix_check（按经验改这个网站的代码，能否单独让这项检查通过；不能则改写经验或标 uncertain）。参考：Zeller *Why Programs Fail*（科学调试）、Agans 调试九规则、鉴别诊断、5 Whys/RCA、AutoSD（Kang 等 2023）、Self-Debug（Chen 等 2023）、Chain-of-Verification（Dhuliawala 等 2023）——出处凭记忆列出，写论文前需核对。
- **prompt 版本：** 每次反思记录 `prompt_version`（全部反思指令的指纹）；每条功能 case 记录 `check_index` 与 `investigation`。
- **回归集（防“修新坏旧”）：** `config/reflection_regression/gold_v1.json`（人工对照代码与评测记录写的每项 failed/partial 的预期归因：established/uncertain/any、应出现的原因关键词、禁止的结论），`scripts/reflection_regression.py` 用当前 prompt 重反思 014/016/017/019/021（只读记忆库，只用 Azure 反思模型）并打分，结果在 `outputs/experiment/reflection_regression/<版本>-<时间>/`。标准答案只用于评估 prompt 版本，不进入 Long Memory；它是人的判断（已发现并改正 1 项：017 介绍其实存在），需用户审核；为防过拟合，改 prompt 只写通用方法，以后宜留出不参与调 prompt 的任务做最终检验。论文正式结果前冻结 prompt 并统一重反思/重跑。
- **结果：** `094741db72e4`（原版）13/18（人工校正后）；`5ab53d3d770d`（6 步）13/18，017 开始逐层查样式但停在父容器、014 在“代码有无”一步误判后跳过样式追踪；之后的 8 步版 `8b6fdccecf88`、加 fix_check 的 `d25660729756` 待测。
- **补充（2026-10-02 晚）：** 字段嵌错层的修复（模型把整条 case 写进 `investigation` 里，被话题检查误拦）属于格式修复，不改变内容。`e724c78964fc` 修复后的回归为 12/18。016 用同一版本两次分别为 5/5 和 1/5，说明单次回归不足以比较版本。

### 2026-10-02：压缩“只缩不删”，每条限长（试验中，只做过预览）
- **原因：** 000018（状态查询）、000026（投票确认、结果页）中，压缩删掉了需求功能，生成器恰好就没做这些功能。Long Memory 026 只得 0.40，没有结果页。
- **做法（`condense_packet`）：** 每个功能候选必须被某条 guidance 引用；只接受 `why=duplicate|not_applicable` 两种删除理由（“没位置”不算）。代码检查覆盖率和总字数，不满足就让模型重写一次。超字数时不再悄悄丢掉条目，也不再为了保住通用经验挤掉功能条目。每条是一句约 90 字符（`ITEM_MAX_CHARS`）的命令式短句：不写验证句（verify、ensuring…）、不写空泛修饰词、不重复需求里已经给出的值，超长的单独再缩一次。去掉 `[functional]` 等来源标签（出处仍在日志里）。guidance 开头约 150 字、结尾一句话。
- **上限：** 试过 2 倍，模型把上限当成目标长度（026 写到 839/648）。改回 1.5 倍加每条限长后，026 为 6 条 413/486 字（记忆部分约为需求的 1.3 倍，之前约 4 倍）；018 为 6 条 524/691 字。
- **未解决：** 检索不稳定。018 两次预览的候选数为 8 和 6，“状态查询”有时在压缩之前就没了。

### 2026-10-03：第一阶段封版归档；WebGen-Bench 线暂停
- **决定（用户）：** GUI 评测资源开销大、噪声大，暂停 WebGen-Bench 实验，后续可能转向 SWE 类基准做长期记忆。本地资源（生成器、Bolt、隧道、PM2）已停止；服务器 A 的 vLLM 未动。
- **总结写在根目录 `README.md` 开头**（小论文形式），快照在 `archive/phase1-webgen-2026-10/`。两个仓库（本仓库和 `bolt.diy-Fork` 子模块）各提交一次并打标签 `phase1-webgen-archive`。
- **可迁移到下一阶段的结论：** 注入要覆盖全部需求、靠缩短措辞而不是删条目来控制长度；反思要强制排查步骤并保证可信度与证据一致；prompt 修改要配回归集和多次运行，并记录 prompt 版本；先排除送达问题和评测环境问题，再讨论模型能力；结论不手写进记忆。
