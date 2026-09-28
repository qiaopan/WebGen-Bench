# 当前交接（更新于 2026-09-28）

## 当前目标

验证 Long Memory（跨任务记忆，仅 case-only 路线）相对旧 No Memory 基线能否改善网站生成。流程按阶段做以节省 token：Stage 1 retrieval（`scripts/memory_stage1_retrieval.py`）→ Stage 2 guidance（`scripts/memory_stage2_guidance.py`）→ Stage 3 生成+评测（`scripts/run_stage3_generation.sh`）。机制稳定后计划清空库、冻结流程，从 000014 起重跑（No Memory 与 Long Memory 用同一份修好的代码），并保留 held-out 任务做验证。

## 评测模型（2026-09-27）

- 生成器、记忆、功能评测与外观评测均使用独立的 Azure GPT-4o `2024-11-20` deployments：`webgen-generator-gpt4o`（capacity 700）、`webgen-memory-gpt4o`（500）、`webgen-functional-evaluator-gpt4o`（600）、`webgen-appearance-evaluator-gpt4o`（100）。分配按长代码生成优先、再多轮功能测试、再记忆处理和单次外观评分的吞吐量估计。
- Long Memory 完成任务后的 reflection 仍使用 `webgen-evaluator-gpt54-mini`；旧通用 `webgen-evaluator-gpt4o`（capacity 100）仅保留作兼容回退。
- `WEBGEN_FUNCTIONAL_EVALUATOR_MODEL` 与 `WEBGEN_APPEARANCE_EVALUATOR_MODEL` 优先于兼容变量 `WEBGEN_EVALUATOR_MODEL` / `WEBVOYAGER_API_MODEL`。任何将新旧运行并列的报告必须明确标注生成器和 evaluator 已改变，不能将分数直接当作同一量尺下的比较。

## 本地 5090 + Azure 的论文近似配置（2026-09-28）

- 生成：本地 OpenAI-compatible service 的 `WebGen-LM-7B`（`WEBGEN_GENERATOR_BASE_URL=http://127.0.0.1:8000/v1`）；Bolt provider 用 `scripts/start_bolt_provider.sh --provider local` 启动。该服务依赖两条由操作者保持的 SSH local-forward 隧道，不能假定跨 session 存活。
- 功能评测：本地 OpenAI-compatible service 的 `qwen2.5-vl-32b-awq`（`WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL=http://127.0.0.1:8001/v1`）。这与 WebGen-Agent 的 Qwen2.5-VL-32B 功能轨迹评测角色相近。
- 外观评分：Azure `webgen-appearance-evaluator-gpt4o`，经 `WEBGEN_APPEARANCE_EVALUATOR_*` 单独指定，保持 GPT-4o 外观评审，不与功能 VLM 混用。
- 记忆/反思与 embedding：仍为 Azure `webgen-memory-gpt4o` 和 `webgen-memory-embedding`；这一次不把 reflection 换成本地模型，保证 Long Memory 的控制变量明确。
- `scripts/preflight_reflective_models.py` 已按四个角色分别建 client，并在真实网络下通过 generator、memory/reflection、functional evaluator、appearance evaluator、embedding 五项连通性检查。不要从日志或文档复制 API key。

## 正在运行：8-task No Memory 论文近似基线（2026-09-28）

- 用户已明确授权运行 `000014`–`000021`。启动脚本：`bash scripts/run_nomemory_webgenlm_14_21.sh`；输出：`outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o`。脚本拒绝覆盖已存在的 output。
- runner 的实际参数必须保持 `--modes disabled`、`--generator-model WebGen-LM-7B`，并读取功能 Qwen-VL / 外观 Azure GPT-4o 的角色专用变量。`run-metadata.json` 是验证模型角色、disabled mode、reflection=false、guidance=false 的权威运行配置。
- 基线运行到每一个生成任务完成前不会有丰富 stdout：Selenium/Bolt 不转发 token。用 `bash scripts/watch_nomemory_webgenlm_14_21.sh` 在另一终端只读观察 queued / generation in progress / generated 和 `progress.jsonl` 的完成记录。不要仅因终端静默终止或重开同一 run。
- 观察时的状态：000014 正在 WebGen-LM-7B generation 阶段，尚未产生 `000001.zip` 或完成事件；这不是失败。若单任务超过自动化的 20 分钟等待上限、runner 退出、或出现 generation failure，保留当前 output，不覆盖，先检查 browser/Bolt 与下载 artifacts 后再决定 resume/repair。
- 本轮完成后，先由 `continual-report.json` 与每项 evaluator raw artifacts 汇总 functional pass/partial/fail、generation failures 和 appearance grades；只与同一 profile 下的后续 Long Memory arm 比较。论文数字可作为外部参考，不可宣称直接同尺。

## Shared-prefix Long Memory（2026-09-28）

- 新的 No Memory GPT-4o 单次基线已完成于 `outputs/experiment/nomem_14_21_gpt4o`：000014–000019、000021 正常生成和两类评测完成；000020 两次构建修复后仍失败，已如实记录为 generation failure，不是漏评。
- 为避免 000014 的随机重生成混淆后续比较，采用 shared-prefix 设计：从 No Memory 000014 的原始生成包、代码与评测证据建立只含该任务的新快照 `outputs/experiment/long_memory_shared_seed_000014_gpt4o/memory_snapshot.db`，并产生 7 条可追溯 cases。000014 是历史 seed，**不计为 Long Memory 测试分数**。
- 000015 的 Stage 1/2 已完成于 `outputs/experiment/stages_000015_shared_seed_gpt4o`：只保留了“表单提交可见确认”与“首屏可见的功能入口”两条经 task-aspect 约束改写的 guidance；Stage 3（Long Memory 生成+评测）尚未启动。

## Long Memory 连续运行与 appearance 支持证据（2026-09-28）

- 000015 的 GPT-4o Long Memory v1 生成与两类评测已落盘于 `outputs/experiment/stages_000015_shared_seed_gpt4o_gen_gpt4o_r1`：功能 4 pass / 0 partial / 1 fail，外观 3。失败是 Astro 静态 frontmatter 的 `formSubmitted` 没有 client hydration，提交后无可见确认；反思已正确产出“用 hydrated client component / Astro island 管理提交状态”的功能与 implementation case。runner 在 post-reflection candidate persistence 后未写 `progress.jsonl`，但生成、评测、反思和 case 都已落盘；该输出不能静默当作完整 runner 成功。
- appearance 去重不再只写 `case_supported` 日志：新增可选表 `case_supports`，保存被支持的旧 case、支持它的新 trajectory、观察、预防动作和 evidence refs；检索仍只取原 case，避免重复 prompt。旧 000015 的历史 `case_supported` 日志未回填该表。
- 000016 的 Stage 1/2 已完成于 `outputs/experiment/stages_000016_shared_seed_gpt4o`，使用 000014 shared seed + 000015 memory DB；当前 guidance 为客户端表单提交成功提示与首屏可见的公司/产品/新闻/联系入口。GPT-4o Stage 3 已完成于 `outputs/experiment/stages_000016_shared_seed_gpt4o_gen_gpt4o_r1`：功能 3 pass / 1 partial / 2 fail，外观 3。提交表单后的页内成功反馈已通过，表明 000015 的客户端状态反思被吸收；剩余失败是公司介绍不完整、产品项目不能打开详情，以及缺少可测试的页面导航。
- 探索阶段已收紧 post-task implementation reflection：缺链接、按钮、路由或 handler 只产生 framework-neutral 的 functional case；只有代码直接证明当前渲染/执行机制使已写交互无法运行时，才允许写 framework-level case。该改动用于 000017 之后的探索运行；000014–000016 保留为旧规则下的诊断证据，正式实验会在 protocol 冻结后重跑。

## 必须先知道的事：2026-09-26 发现的换行 bug

Bolt 输入框把 Enter 当作“发送”。旧代码用 Selenium 一次性输入带换行的文字，**第一个换行之后的内容全部丢失**。已在 `src/automatic_bolt_diy/automatic_web_gen.py` 用 `_type_message`（Shift+Enter）修复，并用两段消息（ALPHA/BRAVO）实验验证。

后果（详见 DECISIONS.md）：
- 此前所有 Long Memory 生成，生成器实际只看到需求原文；guidance、通用池、统计块、基础约束从未送达。这些结果**不能**作为记忆效果的证据，包括 000014 golden cases、14–19 continual chain、000018/000019/000020 的 stage 3 r1–r6。
- 旧 No Memory 基线（`outputs/experiment/continual_domain_blocks/continual-report.json` 的 disabled，2026-09-21 生成）是单段需求、无换行，完整送达，**仍然有效**。
- `000001.prompt.txt` 和 trajectory `run_config.generation_prompt` 记录的是“打算发送”的文本，不是模型实际收到的；权威是 Bolt exported chat（`000001.json`）。runner 现在会在事件里写 `prompt_delivered`，对不上时打印 WARNING。
- 共用的构建失败修复消息此前也只发出第一句，错误详情丢失，修复重试基本无效（所有组）。

## 本 session 完成的主要工作（都只作用于 Long Memory 组，No Memory 路径未改）

- 检索与改写：per-aspect 检索、per-(case,aspect) 改写、functional/appearance 分离；build aspect 已并入“通用池”。
- 反思：强模型 `reflection_llm`、代码证据与 grounding 检查、实现层 case（`[implementation]`）、可选 question-style。
- 统计记忆：同一 DB 内可选表 `run_facts`、`check_facts`（`src/long_memory.py` 的 `OPTIONAL_TABLES_DDL`，核心表校验仍严格；旧库可打开）。字段和聚合见 `src/memory_statistics.py`。
- 失败也产生记忆：生成未通过 → trajectory `execution_error`、检查计全 failed、`[implementation] Project builds…` case（`src/generation_failure_memory.py`），固定标签 `BUILD_FAILURE_LABEL`；不写 `check_facts`。
- 通用池：所有 `[implementation]` case，不做相关性把关，按优先级取 6 条候选（2 个名额留给历史累计严重度最高者）→ 改写成至多 3 条通用要求。
- 优先级公式：出现次数 × 严重度（failed 1.0，partial 0.5，构建失败=丢掉的检查数）。全部数值在 `config/long_memory.json`（`priority_window` 0=全部历史、`priority_half_life` 0=不衰减、`severity_failed`、`severity_partial`、`priority_alpha`、`common_pool_*`）。**半衰期暂时关闭**，等历史足够再测。
- 整体反思（`scripts/memory_retrospective.py`）：跨任务回看，引用统计必须与事实表一致；首次结果因 Astro 样本太少没能推出“避开 Astro”。
- 可选开关（默认关）：重试时查记忆（`repair_hint`）、guidance 自检补做（`--guidance-selfcheck`）、基础约束（`base_constraints_in_prompt`，现为 false）。
- 工具：`scripts/backfill_run_facts.py`（`--rebuild`）、`scripts/test_label_consistency.py`、`scripts/measure_guidance_compliance.py`、`scripts/reeval_single_check.py`、`scripts/add_failed_generation.py`。

## 最新有效实验：000020（换行修复后第一次）

输出：`outputs/experiment/stages_000020_r7`（stage1/2）、`stages_000020_r7_gen`（生成+评测）。库：`outputs/experiment/library_14_19_v1`（14–19，含 19 的构建失败记录，Astro）。

| | No Memory（旧基线） | Long Memory r7 |
|---|---|---|
| Functional passed/partial/failed | 3/2/0 | 3/2/0 |
| Appearance | 3 | 4 |
| guidance 遵守度（`compliance.json`） | — | 6/8 |

- `prompt_delivered: True`，react-vite，一次构建通过。
- 账户更新由 partial 变 passed（guidance 直接覆盖）；导航由 passed 变 partial（评测判断，属隐藏预期，随机性大）。
- 换行修复前的 r5/r6/自检运行等价于“只有需求原文”，结果也全是 3/2/0，可当作额外的 No Memory-like 样本；注意 r5 第 3 项评测为空记录，已用 `reeval_single_check.py` 补评（见 `stages_000020_r5_gen/evaluation_revision.json`）。

## 未解决问题

- 单任务单次结果波动大，尚不能下“记忆有效”的结论。建议先在 000020 上再带记忆跑 2 次看波动，再做 000021。
- 评测解析器把“评测代理没有回复”记为 failed（共用逻辑，未改）；看到 failed 先核对 `interact_messages.json` 是否为空。
- LLM 生成的问题标签只做过 n=9 的一致性检验（两次分组 100% 一致），但有 1 条明显错标；样本多了要做人工抽查。
- 隐藏预期（评测要求、公开需求未写）无法靠记忆完全补上；统计块已记录 `requirement_stated`，但 14–19 样本还少。
- 框架选择（Astro 对 React/Vite）仍是最大的不受控变量；Astro 只有 3 个样本，统计和整体反思都不足以支持“避开 Astro”，需要 20 之后的任务积累。
- guidance 自检补做尚未在换行修复后测试；若纳入正式对比，No Memory 也要做同样的自检以保证公平。
- 当前 worktree 是脏的（含此前 Copilot/Codex 的改动）；不要 reset/clean。

## 工作规则（用户要求）

- 改完代码只做编译检查，不要擅自运行（包括免费的本地检查），先说明并询问；Claude Code 的 token 也要节省。
- 付费 generation 前必须给 pre-run comparison table 并得到确认。
- 探索阶段不新跑 No Memory；旧基线只取 disabled 部分，其中的 continual 是旧结果不可用。
- 结论不得手写进 Long Memory：结论由代码统计或模型总结得出，且可核对。
