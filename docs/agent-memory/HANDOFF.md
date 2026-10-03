# 当前交接（更新于 2026-10-03：第一阶段封版归档）

## 阶段性归档（2026-10-03，用户决定）

- **WebGen-Bench 这条线暂停并封版。** 原因：资源开销大（每个任务每臂约 40–90 分钟，需要 Mac 生成器加 5090 上的 32B VLM 评测），且 GUI 评测噪声大。用户可能转向 SWE 类基准，在其上继续做长期记忆。
- **总结（小论文）在仓库根目录 `README.md` 开头**：设置、方法、结果表、发现 F1–F8、局限、后续方向、参考文献。结果快照在 `archive/phase1-webgen-2026-10/`（progress、run-metadata、memory.db、反思、检索事件、prompt、回归集结果、prompt 长度 CSV）。完整输出约 20 GB，仍在本机 `outputs/experiment/`，不在 git 中。
- **本地资源已全部停止（2026-10-03）：** Mac `llama-server`（`~/webgen-local-generator/bin/stop-generator.sh`）、Bolt（5186）、`keep_tunnel.sh` 和 8001 SSH 隧道、PM2 守护进程、残留的评测子进程。服务器 A 上的 Qwen2.5-VL vLLM 已由用户手动停止。
- **封版提交：** 本仓库（`qiaopan/WebGen-Bench`，分支 `reflective-multimodal-memory`）与子模块 `bolt.diy-Fork`（`qiaopan/bolt.diy`，分支 `diy-fork`，即 OpenAI-like provider 与 token 上限相关改动）各提交一次，并打标签 `phase1-webgen-archive`。

### 封版时的状态（如果以后要恢复这条线）
- **两条正式链：**
  - No Memory：`outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2`，读 `config/long_memory.json`，不要改这个文件（否则配置指纹不符）。
  - Long Memory：`outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1`，读 `config/long_memory_condensed.json`。`guidance_max_items` 为 6，`guidance_max_ratio` 为 1.5；指纹已同步，备份 `run-metadata.json.before-*`。
- **结果：** 见 README 第 4 节。Long Memory 018 已重置等重跑；No Memory 026 修复超时问题后重跑，最终记为构建失败；Long Memory 026 跑在压缩只缩不删之前（0.40，压缩删掉了结果页和投票确认），其反思跑在“字段嵌错层”的修复之前（丢了 2 条），**需要按当前代码重跑并重新反思**。
- **待跑队列：** L:000018、L:000026（重跑）、N:000027、N:000028、L:000027、L:000028，然后从 000029 交替（`outputs/experiment/full_queue_2026-10-01_after_first_screen_fix.txt`）。
- **恢复步骤：**
  1. `~/webgen-local-generator/bin/start-generator.sh`；
  2. `zsh scripts/keep_tunnel.sh &`（需要 `.env` 中的 `WEBGEN_EVAL_SSH_HOST`；先在服务器 A 上重新启动 Qwen2.5-VL 的 vLLM 服务）；
  3. `zsh scripts/start_bolt_provider.sh --provider local --port 5186`（带 30 分钟 fetch 超时；在 `tools/bolt-preload` 运行 `npm install` 后使用仓库内副本）；
  4. `QUEUE='L:000018 ...' zsh scripts/catchup_remaining.sh`（启动前会跑 preflight）。
- **规则（用户 2026-10-02）：** Long Memory 每个任务先只跑第一、二阶段（`scripts/preview_guidance.py --output <链> --task-id <id> --log <单独日志>`）给用户看，确认后再跑生成和评测。每个 pair 跑完后，按 DECISIONS“每个 pair 的标准分析流程”做五层归因。修复次数用完或我方代码出错时，立即停下报告。

### 未完成的方案与待决定事项（封版时）
1. **反思 prompt：** 当前版本 `e724c78964fc`（9 步 `investigation` + fix_check + “评测员的局限不算网站缺陷”），以及字段嵌错层的修复。回归 12/18，版本之间的差异小于运行之间的波动。下一步应对同一版本连跑 3 次以上，区分“稳定错”和“随机错”，只针对稳定错的项修改。016 在第 2 步“是否到达目标”与“首页无入口算网站缺陷”之间仍有冲突。
2. **可选的代码检查（未实施）：** 原因描述里出现 appears、seems、likely 等不确定措辞时，自动改为 uncertain。
3. **样式追踪的中性事实（未实施，方案 B）：** 把会继承全局颜色、自身又未设文字颜色的元素列为代码事实交给反思。
4. **014 的旧反思**（含“服务详情放首屏”经验）尚未替换。prompt 定下后，用 `scripts/replace_reflection.py` 替换，并按同一标准复查其他旧 case（在 `cause_confidence` 出现之前写的）。
5. **压缩（已实施，只做过预览）：** 覆盖每个需求功能（只接受“重复”或“不适用”两种删除理由）；每条约 90 字符的命令式短句，超长的单独再缩；guidance 开头和结尾已缩短，并去掉了来源标签。026 预览 6 条共 413/486 字。尚未经过一次完整生成的检验。
6. **检索不稳定：** 018 两次预览的候选数分别为 8 和 6，“状态查询”有时在压缩之前就丢了（记忆模型对相关性的判断不稳定）。尚未处理。
7. **回归集标准答案** `config/reflection_regression/gold_v1.json` 需要用户审核（017 介绍一项已改正）。
8. **压缩字数上限：** 2 倍上限的试验显示，模型会把上限当成目标长度。现在回到 1.5 倍，加上每条限长。

### 重跑原 Long Memory 任务的步骤（已用于 016/019/021/028）
备份 `memory.db` 与 `progress.jsonl` → 该任务 completed trajectory 的 `reflection_cases` 置 `archived`、派生 experience 置 `rejected`/`archived`（触发器不允许 candidate→archived）、删除其 `run_facts`/`check_facts`/`case_supports` → 从 `progress.jsonl` 去掉该任务行 → 目录改名 `tasks/<id>.pre-condense-backup`。`memory_sources` 只能追加，不可删改。runner 现在会为重跑新建 trajectory（attempt_no+1）。

### 工具（本 session 新增）
- `scripts/compare_task.py`：单任务三栏对比表。
- `scripts/backfill_prompt_stats.py`：补 `run_facts.prompt_stats` 并导出分析 CSV。
- `scripts/backfill_appearance_grade.py`：补历史外观 `score`（已执行，617 条）。
- `scripts/replace_reflection.py`：用新生成的反思替换某任务的反思（现在归档旧 case，不删除）；`scripts/finish_post_task.py` 的 `load_context` 现在取最新 attempt。
- `scripts/watch_run_events.sh`：只读观察。`scripts/paper_protocol_phase2.sh` 已过时（修复次数 1、`set -e`），不要用。

---

> 以下为 2026-09-29 及更早的历史交接记录，仅供参考；当前状态以上面的“阶段性归档”为准。

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

## 硬件变更与 Mac 本地生成器（2026-09-29，进行中，尚未启动/测试）

决策与理由见 DECISIONS.md 的“2026-09-29：服务器缩减后的硬件分工”。这里只记录当前状态与待办。

**Mac 侧（文件都在仓库外的 `~/webgen-local-generator/`）：**
- 已完成：官方 `luzimu/WebGen-LM-7B` 下载并核对（17 个文件大小与清单一致），转换为 BF16 GGUF，量化为 `gguf/WebGen-LM-7B-Q8_0.gguf`（8.1GB，8.50 BPW）。工具为 llama.cpp 0.5.0（build 11146，commit `7fe450e19305b828c199d602c23a8337aaa1f03b`，Homebrew 安装的 `llama-server`/`llama-quantize`）。全部参数与 SHA-256 见 `QUANTIZATION_RECORD.md`（论文引用用）。
- 已写好 `bin/start-generator.sh`、`status-generator.sh`、`stop-generator.sh`，仅做过语法检查。`llama-server` 参数：`--alias WebGen-LM-7B --host 127.0.0.1 --port 8000 -c 32768 --parallel 1 -ngl 99`。启动脚本会在 8000 端口已有响应时拒绝启动（防止误连残留的 SSH 隧道）。
- **首次实测（2026-09-29，模型加载后空载，未跑 Bolt/Chrome 自动化）：** 服务正常启动，`/v1/models` 返回 `WebGen-LM-7B`、`n_ctx=32768`、`ftype=Q8_0`；生成速度约 12 tok/s，预填充约 490 tok/s（2.9k token 提示）；启动前系统空闲内存 55%，启动后降到约 17%，内核内存压力级别为 2（warn，非 critical），wired 约 14GB、压缩内存约 6GB，交换空间已用 6.7/7GB（累计值，换入很少，未见明显抖动）。这些数字是在另有 ChatGPT/微信/多个 Chrome 进程开着的情况下测得；尚未测输出质量、满 32k 上下文的 KV cache 开销，以及叠加 Bolt + Selenium 后的表现。按 12 tok/s 粗估，一个 8k token 的网站仅解码就要约 11 分钟，多轮或构建修复重试有可能超过自动化的 20 分钟上限。
- **复测（同日，关掉 ChatGPT/微信等应用后，持续生成 3000 token）：** 用时 224 秒，解码约 13.5 tok/s；全程内核压力级别 1（正常）、空闲内存约 39%、wired 约 13.8GB（空载时只有约 3.8GB，说明模型权重只在生成时被钉住）、压缩内存约 1.2GB、交换空间未增长。前一次的“警告级别”主要来自其他应用占用，不是模型本身。仍未测：叠加 Bolt + Chrome + Selenium + node 后的压力，以及 8k 以上上下文的 KV cache 开销。

**服务器 A（`sc448960`，1×5090）：**
- 生成服务已停止，GPU 空闲。`~/webgen-generator/models/` 里已有 Qwen2.5-VL-32B-AWQ 权重（约 20GB），以及 `bin/vision-from-evaluator/` 下的 start/status/stop 脚本。
- **（2026-09-30 更新）Qwen-VL 已由 Codex 配置并在运行：** `vllm serve` 起在服务器 A 的 `127.0.0.1:8001`，`/v1/models` 返回 `qwen2.5-vl-32b-awq`，GPU 已用约 29.5/32GB（我方查看时已连续运行约 1 小时 12 分）。`bin/vision-from-evaluator/` 下三个脚本里的 `ROOT` 仍指向不存在的 `/home/qma258/webgen-evaluator`，我们没有修改它们；不要假定这些脚本可直接用，服务状态以 8001 端口实际响应为准。
- 服务器上没有 7B 权重（`models/` 里只有一个不完整的 `WebGen-LM-14B` 空壳，与本研究无关）。
- 启动 Qwen-VL 后，Mac 上只需一条隧道：`8001 -> 服务器 A 的 127.0.0.1:8001`。`scripts/run_nomemory_webgenlm_14_21.sh` 里的注释仍写着旧的“两条隧道、两台服务器”，尚未更新。

**运行进度快照（2026-09-30，只读检查得出，均为旧硬件/探索性质，不作效果证据）：**
- `.env` 里的角色配置：生成器 `http://127.0.0.1:8000/v1`（现在是 Mac）、功能评测 `http://127.0.0.1:8001/v1`（经隧道到服务器 A）、外观评测 Azure。无需改代码。
- Long Memory `outputs/experiment/longmem_ghtoken_batch1`（batch 1“公司宣传站”，manifest 顺序 000014–000021，共 8 个）：000015 完成（功能 3 passed/2 failed）、000016 生成失败（vue-tsc 构建错误）、000014 生成失败（同类）、000017 完成（2 passed/3 partial/1 failed）；**000018–000021 未跑**。完成顺序是 15、16、14、17，原因未查清；该输出目录里没找到 `memory.db`，记忆库位置未查清。
- No Memory `outputs/experiment/nomem_ghtoken_000014`（任务 14–21）：8 个里 7 个构建失败，仅 000018 完成（1 passed/5 failed）。失败几乎都是 7B 模型选了 Vue + TypeScript 模板，`vue-tsc` 严格检查不过；按现有规则，构建失败计为该任务全部检查 failed，所以汇总里 39 项只有 1 项通过，这不是评测异常。
- 这两次运行的 `run-metadata.json` 都写 `generator_model=WebGen-LM-7B`，但没有记录后端是 5090 BF16 还是别的，所以“旧运行用 BF16”是推断。

**下一步（按顺序，每步先说明并征得同意）：**
1. ~~在 Mac 上启动 `llama-server` 并测速度与内存~~：已完成（见上面的实测）。`llama-server` 目前仍在运行（PID 记录在 `~/webgen-local-generator/run/generator.pid`）。
2. ~~Qwen-VL 服务与 8001 隧道~~：服务已由 Codex 起好；**隧道已在本机建立**（`ssh -N -L 8001:127.0.0.1:8001 qma258@<服务器 A>`，后台进程，不能假定跨 session 存活，断了要重建）。
3. ~~preflight~~：2026-09-30 已通过，generator（Mac Q8_0）、memory/reflection、functional evaluator（Qwen-VL）、appearance evaluator、embedding 五项均 PASS。
3a. **尚未做：** 启动 Bolt（`scripts/start_bolt_provider.sh --provider local`）；弄清 Long Memory 记忆库的位置与续跑方式；给出 pre-run 对比表并取得确认。
4. 用**一个任务**实测单任务总耗时。HANDOFF 下面提到的自动化 20 分钟单任务等待上限，在 Mac 上可能不够（长网站 + 构建修复重试），需要评估是否调大。
5. 正式跑之前，按规则给出 pre-run 对比表并取得确认，注明这是新的 Mac Q8_0 profile，No Memory 与 Long Memory 两个 arm 都在此 profile 下运行。

**本机环境清理（同一 session）：** 删除了 uv 管理的 Intel 版 Python（3.11/3.12/3.13）、Intel 版 Homebrew（`/usr/local`）里的全部命令行包及 Intel 版 Python 3.14，改装 arm64 版（`/opt/homebrew`：go、cmake、ninja、minikube、kubectl、skaffold、grafana、pkgconf、libtool、lzip；git 落到系统自带的 arm64 版）。Ollama 是通用二进制，未动。`~/.zshrc` 里 `nvm` 的加载路径改为 `$NVM_DIR/nvm.sh`。**遗留：** `uv` 程序本身仍是 x86_64 版；`~/ai-agents-for-beginners/.venv` 因依赖已删除的 Intel Python 3.13 而失效；Anaconda 空壳的 cask 登记、VirtualBox（Intel 版）以及 Intel 版 Homebrew 本身需要 sudo，留给用户自己处理。

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
