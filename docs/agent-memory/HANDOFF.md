**同步规则（用户 10-08）：** 用户说"同步"时，同时更新论文（`docs/thesis/`）、PPT（`docs/reports/group_meeting_deck_2026-10/` 并发布到 artifact）、`README.md`、HANDOFF/DECISIONS。

# 当前交接（更新于 2026-10-05：WebGen 第二阶段进行中；SWE 阶段已于 2026-10-05 封版；第一阶段已于 2026-10-03 封版）

[English current-state guide](HANDOFF.en.md) | [中文完整记录](HANDOFF.md)

## 2026-10-06 晚：v3 guidance 的具体做法保真（本地，未同步集群、未开始 Long Memory）

- 在既有 v3 的源头去重、可执行性过滤、`hard_match` 和 hard cap 之上，`src/post_task_reflection.py` 现要求已证实的 Vue 交互/视图状态问题写出最小代码构造，而不是“ensure/正确配置”一类结论：例如页面切换应明确 `ref` + `v-if`，提交结果应明确 handler 更新 state + `v-if`，列表明确本地数组 + `v-for`。这只是反思格式的通用规则；不手写任何任务结论。
- `src/reflection_case_memory.py` 的 adaptation 指令同样要求保留这些构造；压缩时检查候选中已有的 Vue token（`ref`、`v-if`、`v-for`、事件绑定等）是否在引用该候选的最终条目中消失。若消失，带缺失 token 只重写一次压缩请求；日志的 `guidance_condense.retried` 会留下前后记录。这样短 guidance 仍保留“怎么做”，而非只保留功能名称或泛化警告。
- 新增最小单测覆盖 token 检测；该测试、`py_compile` 和 `git diff --check` 已通过。已有三份历史测试文件整体有 5 项失败（测试桩假设旧的一次性 retrieval payload/旧默认 prompt 约束，与当前分阶段接口不一致），本次改动前即存在，未修改它们。
- **下一步：** 通过现有 28440/28441 隧道，用已完成 Long Memory 的 000032/035/038 先重新反思并预览 guidance；确认出现具体构造且不重复后，才做三题生成 + Vue 编译检查；不送评测、不改集群作业、不跑正式 Long Memory。若三题中至少 2 题代码覆盖优于 No Memory，再同步代码并向用户给出运行前对比表。

## WebGen 第二阶段：学校 H200 集群（2026-10-05 开始）

### 2026-10-11：v8 停止，v9 排队（详见 DECISIONS 同日条目）
- 种子 11 两组 101 题已完成：No Memory 27.9%（零分 29）、v7 33.1%（零分 21），配对 +4.4（CI [−2.0, 10.5]），v7 有 19 个脚手架。按问题分类（种子 11）：No Memory 缺 vue-router 24 题（22 题零分）、缺 Vue import 19；v7 脚手架 19、缺 import 15、vue-router 2、v-model 编译错 3。
- v8 停在 59/101（队列行已注释，备份 `filler.conf.bak-before-stop-v8`）；v9 已排在种子 29 前（备份 `filler.conf.bak-before-v9`），集群代码已与本地核对一致。诊断输出在集群 `outputs/experiment/diag_replay_code_pool_seed11/`。
- 10-11 放行前做了 31 题生成验证（只查代码，见 DECISIONS 同日条目）：脚手架 0/31，v-model-on-prop 仍出现 3 次。v9 已于 10-11 放行，排在种子 29 当前这题之后。跑完后与 v8 比较只看机制（脚手架、router 白屏、v-model 编译错次数、代码记忆建立时间与版本数），总分只作参考（运行间波动约 5 个点）。
- **10-12：v9 停在 45 题（用户决定），队列先跑种子 29。** 原因与 v9.1 修正见 DECISIONS 同日条目：v-model 记忆因 72B 写的适用条件永远不匹配而从未注入；v9.1 让编译错误类记忆由代码判定对所有 Vue 网站适用，生成检查 3/3 不再出现 v-model 编译错。10-13 用户决定：v9.1 种子 11（只跑 Long Memory，输出 `cluster_order_blocks11_longmem_v9_1`）排在交错顺序之后、固定前缀之前（备份 `filler.conf.bak-before-v91`），以保证 10-16 组会前四个顺序实验都完成；预计种子 29 10-13 早、种子 47 10-14 中午、交错 10-15 傍晚、v9.1 约 10-16 晚。

### 2026-10-16：队列现状；No Memory 全部停止；论文字数口径
- **两条队列并行（worker 23385）：** 主队列 `queue/filler.conf`：交错 v9.1（52/101，只跑 Long Memory）→ 原顺序 v9.1 r2；lane2 `queue/lane2/filler.conf`：种子 47 v9.1（91/101）→ 固定前缀（v9.1）；lane3 已 STOP。预计 10-17～18 全部完成。
- **No Memory 不再新跑（用户 10-16）：** 交错停在 14 题、种子 47 停在 90 题（lane2 已改为 `-`，备份 `filler.conf.bak-before-drop-nm47`）。论文用三次完整 No Memory（原顺序、种子 11、29：28.5/27.9/28.6%）。
- **已有结果（101 题，单次）：** v9.1 原顺序 35.2%（零分 20）、种子 11 35.4%（16）、种子 29 33.7%（18）；v7 原顺序 40.0%、种子 11 33.1%、种子 29 32.6%。
- **v7 原顺序偏高写为开发集效应（用户同意，已写入论文 5.6 节与 6 章局限）：** v7 是看原顺序的失败逐步改出来的，换顺序掉约 7 个点而 No Memory 不变。注意 v9.1 也是在种子 11 上修的；干净检验是种子 29、47、交错；v9.1 比 v7 只高 1～2 个点，不能写成显著更好。
- **论文字数（导师 10-16 确认）：** 封面、致谢、目录不计入字数统计。

### 2026-10-15：v9.1 种子 11、29 跑完；周五 PPT 与论文更新
- **结果：** 种子 11 v9.1 35.4% vs No Memory 27.9%，+7.4（CI [1.6, 13.1]，显著），零分 16；种子 29 33.7% vs 28.6%，+5.5（[−0.5, 11.6]），零分 18。脚手架 v7 19/16 → v9.1 0/0。v9.1 − v7：+3.0 / +1.0（不显著，只看机制）。单页漏 Vue import 增多（23/27 题 vs v7 17/19）、v-model 编译错约 6 题，属生成器笔误。两次运行已归档进 git。
- **PPT：** 周五版 https://claude.ai/artifact/EbBcUG5F5NjcVofWr5kSUc（37 页）：新增实验总表两页、顺序设计 + 五个顺序各一页；快照 `docs/reports/group_meeting_deck_2026-10-15/`（10-13 版保留在 `..._2026-10-16/`）。
- **论文：** 第 5 章新增 `sec:runs`（`tab:runs` 全部运行总表），`tab:order` 增加 v7/v9.1 两列，新增 v9.1 差距曲线图；第 7 章 RQ3 更新。
- **剩余时间表：** v9.1 原顺序约 10-16 早上 → v9.1 种子 47（成对）约 10-17 → v9.1 交错约 10-18。固定前缀（需要 v9.1 原顺序最终代码条目）与 32B（用 v9.1 配置）尚未重新排队，原顺序跑完后加入：固定前缀约 19 小时、32B 成对约 30 小时 + 切换，预计 **10-21 前后全部完成**；作业 11-05 到期。

### 2026-10-13：种子 29 跑完；PPT/论文同步
- 种子 29（随机）101 题：No Memory 28.6% / v7 32.6%，配对 +4.5（CI [−2.2, 11.3]），零分 29 / 21；前 30 题 31.6 / 29.5，第 31–101 题 27.3 / 33.9。v7 有 16 个脚手架（No Memory 0），全部在"缺包"整文件示例第 19 题开始注入之后；种子 11 为 19 个、第 36 题起。种子 11、29 及 v8、v9（停止）已归档进 git（`archive/phase2-webgen-2026-10/cluster_order_*`）。分析脚本 `scripts/analyze_order_run.py`（配对差、CI、零分、脚手架数、gap 图）。
- PPT（artifact v36）：`order-1`、`order-2` 填好并配 gap 图，`order-3/4` 标运行中，新增 `order-fix`（脚手架原因与 v8/v9/v9.1），`conclusion` 填好消融和顺序结论。论文 `tab:order` 两行、第 5 章新增顺序结果与 `sec:fix`（v8/v9/v9.1），第 7 章 RQ3。README 新增顺序表。

### 2026-10-16 晚：五个顺序的中期对比
- 脚本 `scripts/analyze_all_orders.py OUT.png`（No Memory 缺的题用原顺序 r1 的同题分数补，生成是确定性的）；图 `docs/reports/gap_all_orders.png`，已进论文 `fig:gap-all`，`tab:order` 填了种子 47（92 题）、交错（54 题）两行中期值。
- v9.1 − No Memory：原顺序 +7.1 [1.0, 13.1]；种子 11 +7.4 [1.6, 13.1]；种子 29 +5.5 [−0.5, 11.6]；种子 47 +10.4 [4.3, 16.6]；交错 +6.8 [−1.1, 14.7]。v9.1 − v7：原顺序 −4.4 [−9.7, 1.1]，种子 11 +3.0 [−3.0, 9.0]，种子 29 +1.0 [−5.0, 7.0]。即 v9.1 每个顺序都高于 No Memory；只在 v7 开发所用的原顺序上低于 v7。
- 种子 47、交错的中期数据只拉了 `progress.jsonl` 等三个文件到 `outputs/experiment/`；跑完后再用 `scripts/archive_phase2_runs.py` 归档。

### 待办清单（2026-10-16 重写；**交论文：10-19 周一**；做完一项就删掉）
**队列（10-16 23:15 对调后）：** 主队列：交错 v9.1（53/101，约 10-17 11:00）→ 固定前缀消融 v9.1（约 10-18 清晨）；lane2：种子 47 v9.1（91/101，约 10-17 02:00）→ 原顺序 v9.1 r2（约 10-18 上午）。均只跑 Long Memory；备份 `filler.conf.bak-before-swap-r2-fixed`（两条队列各一份）。
1. **种子 47、交错跑完（10-17）：** 拉取并归档 → `scripts/analyze_order_run.py`（与已有 No Memory 按题配对；种子 47 No Memory 有 92 题、交错 14 题，其余用确定性的已有 No Memory 分数，论文写明）→ 填论文 `tab:order` 两行和第 5、7 章结论、README 表。
2. **固定前缀、r2 跑完（10-18）：** 填 `tab:ablation` 固定前缀行；r2 与原顺序 v9.1 第一次的差值写进第 6 章"单次运行"一条（清掉该 `\todo`）。
3. **10-18 晚 / 10-19：** 全文通读、清掉所有 `\todo`、致谢；重新打包 `docs/thesis_overleaf.zip`，在 Overleaf 编译检查。字数口径：封面、致谢、目录、图表目录不计，参考文献计；10-16 PDF 约 11,580 词（摘要 335 + 正文约 10,040 + 参考文献 1,201）。
4. 32B 不再在交论文前做（时间不够），论文写为未来工作。
5. 删除任何集群输出目录前，先注释 `filler.conf` 中指向它的行。作业 23385 的 30 天上限（11-05）只是资源期限，不是截止日。

### 2026-10-13：周五（10-16）英文汇报版与参考文献核对
- 英文 10 分钟版 PPT：https://claude.ai/artifact/BWDmn48YPwAzEiL8KbKXx1 ，源文件 `docs/reports/group_meeting_deck_2026-10-16_en/`（13 页；只用 Arial/Georgia，避免导出 .pptx 乱码；讲稿约 550 词，基本照念页面文字）。学习曲线改为 No Memory / 只有清单 / v4 / v7 四条线，消融页改为柱状图（配对差与 CI）；画图脚本 `plot4.py`。
- 第 3、4 页按流程顺序写明 agent 与模型：Bolt.diy + WebGen-LM-7B 生成 → WebVoyager + Qwen2.5-VL-32B 功能评测 → 截图单次调用 + Qwen2.5-VL-32B 外观评分（论文为 GPT-4o）→ 记忆模块 Qwen2.5-VL-72B-AWQ + bge-m3。
- 参考文献已联网核对：ReasoningBank 为 Ouyang et al., ICLR 2026（arXiv:2509.25140）；ACE 为 Zhang et al., ICLR 2026；WebVoyager 补全作者；论文 bib 与两份中文 PPT 同步更正。Mem0 的 arXiv 号（2504.19413）未联网核对。

### 2026-10-10：种子 11 后段没有优势的原因；v8 验证与排队
- **现象：** 种子 11（领域挨着）79 题时 v7 33.7% vs No Memory 28.3%（配对 +4.5，CI [−3.0, 11.7]）；同一批题在 manifest 顺序下 v7 41.0%、No Memory r1 29.0%。No Memory 两次很稳，v7 换顺序掉约 7 个点。第 31–67 题 v7 无优势（29.9% vs 31.4%）。
- **原因：** 从第 36 题起代码池注入"缺包"条目，内容是一整份别站的 `App.vue`（30 行，来源为食物捐赠网站）；之后 v7 有 8 题交了原样 Vite 脚手架（No Memory 0 题），这 8 题 No Memory 35.8%、v7 2.5%；另 5 题是编译错（v-model 用在 prop/文件框）或缺包。其余 24 题 v7 45.0% vs No Memory 27.6%。manifest 顺序同样注入整份文件 76 次，只出 2 个脚手架（示例来自通用服务网站），差异原因推测为示例内容与当前题的相关度，单次运行，未证实。
- **v8 小验证（只生成、只查代码，未评测）：** 8 个脚手架题用 v7 原 prompt，只把整份 `App.vue` 换成 v8 片段（72B 挑出的 `ref` 状态 + 导航按钮 + `v-if` 行），8/8 生成真实页面、无未声明的包。脚本 `scripts/cluster/diag_v8_fragment.py`，作为 worker 一次性任务运行，输出在集群 `outputs/experiment/diag_v8_fragment_seed11/`。
- **v8 完整运行（用户决定提前）：** `filler.conf` 中种子 11 之后、种子 29 之前加 `P ... blocks_seed11.json cluster_order_blocks11_longmem_v8 - config/long_memory_cluster_v8.json`（只跑 Long Memory，与种子 11 的 No Memory、v7 按题比较）；原排在 32B 之后的"切回 7B + v8"两行已注释（备份 `filler.conf.bak-before-v8-early`）。预计种子 11 约 10-11 凌晨完成，v8 约 10-12 凌晨，其余顺延约一天，32B 约 10-19～20。
- **跑完要看：** 101 题里还有无脚手架；后段分数是否补回；v7 做得好的题有无变差（页面数、是否用 router）；缺 import 题数是否少于 v7；每次建立/更新代码记忆时挑出的行（`key_lines` 日志）是否合理。
- **注意：** 本地工作区有另一会话未提交的改动（README 中英文版、三个交接文档的 `.en.md`）；本条通过独立 worktree 提交，未动这些改动。

### 2026-10-09：清理后误重跑 v4（已修）
- 10-08 删除 v4、v7 输出目录时没有注释 `filler.conf` 中对应的 L 行，补位脚本把 v4 当作未完成，从头重跑约 12 小时（61 题），消融停在 44/101。10-09 已注释这两行（备份 `filler.conf.bak-before-skip-done`）、停掉 v4 重跑，消融从第 45 题继续；重跑的 v4 目录（4 GB）由用户删除，不作参考。**规则：删除任何输出目录前，先注释 `filler.conf` 中指向它的行。**

### 2026-10-08：实验数据进 git；集群存储
- 新增 `archive/phase2-webgen-2026-10/`（`scripts/archive_phase2_runs.py`）：No Memory r1、v4、v7 的关键文件（进度、汇总、配置、记忆库、压缩的事件与反思、每题 prompt），共约 16 MB；其余运行跑完后用同一脚本加入。已删除仓库里原作者上传的 `outputs.zip`（78 MB，与本项目无关；仍在 git 历史中）。
- 集群个人存储额度 290 GB（Cluster Policies），10-08 已用 245 GB（模型 195 GB）。已核对本地副本完整的旧运行（pipetest×3、v4dbg、旧只有清单、v6、旧 Long Memory r1、v4、v7、No Memory r1，约 27 GB）和 `cache/uv`（7.8 GB）已由用户在 10-08 删除，用量 245 → 211 GB。32B 跑完后可删 32B 权重（73 GB）。额度按人计，不按课程（764 与 792 共用 2 张卡）。

### 2026-10-09：只有清单（v7）消融跑完 101 题
- 准确率（前 30 / 第 31–101 / 全部）与零分：No Memory 26.0/29.5/28.5、30；只有清单 33.1/31.3/31.8、18；v7 39.0/40.4/40.0、13。外观 3.25/3.23/3.21。按题配对：只有清单 − No Memory +3.4（CI [−2.2, 8.7]，51/27/23），v7 − 只有清单 +8.1（[2.9, 13.2]，46/28/27）。
- 结论：清单主要减少整站失败、准确率提升不显著，且后段优势缩小（+7.1 → +1.8）；记忆是主要且显著的贡献，后段更大（+5.9 → +9.1）。37 题时"清单约 +7、记忆约 +6"的粗算作废。已归档进 git（`archive/phase2-webgen-2026-10/cluster_checklist_only_v7_webgenlm7b_r1`）；集群 `filler.conf` 中该行已注释（备份 `filler.conf.bak-before-abl-done`），集群副本可在存储不足时删除。已同步论文（`tab:ablation`、第 6、7 章）、PPT 消融页、README。

### 2026-10-08：消融中期结果与论文主线思路（待 101 题和固定前缀跑完后定稿）（已被上面的最终结果取代）
- 只有清单（v7）37/101 题时，同 37 题：No Memory 24.8%（零分 13）、只有清单 31.7%（8）、v7 37.7%（6）；第 1–30 题 26.0 / 33.1 / 39.0，第 31–37 题 20.2 / 26.6 / 33.0（后段仅 7 题）。粗算需求拆解约 +7、记忆约 +6 个百分点；记忆贡献比 18 题时（约 +4.5）变大，符合代码池在问题出现 2 次后才启用的预期。
- **论文主线（与用户讨论）：** 主线仍是记忆，清单作为方法组成部分、用消融说明。统一解释：7B 能执行"别人给好的具体内容"（72B 拆好的清单条目、核对过的代码片段），不能自己规划（short CoT 0/5）或执行抽象文字经验。注意清单由 72B 记忆模型生成，准确说法是"更强模型替小模型拆需求"。
- **定稿前要等：** ①只有清单跑完 101 题，看第 31 题以后是否像 v4 那样下滑；②固定前缀结果：若接近 v7，记忆的贡献应表述为"自动发现有效代码"而非"持续积累"。之后按同步规则写进论文第 5、6 章和 PPT 消融页、结论页。

### 2026-10-08：32B（FP8）已排进当前作业（见 DECISIONS 同日条目）
- 32B 权重已下载完成（10-08 23:04，`/data/qma258/models/WebGen-LM-32B`，14 个分片齐全，含缓存 73 GB）。下载作业 23432 一直卡在人工审批，已取消，改为在 worker 作业里 `srun --overlap --ntasks=1` 下载，约 2 分钟（注意：不加 `--ntasks=1` 会按作业任务数启动 8 份）。
- 队列末尾：`X scripts/cluster/switch_generator.sh /data/qma258/queue/switched-to-32b-fp8`，然后 P manifest 顺序 32B。目标配置 `$WG/queue/generator.env.next`。补位脚本的运行副本已原子替换为新版，并排了 `reload-filler-2`。
- **约 10-15 切换时要人工检查：** worker 日志里的 `SWITCH_DONE`/`SWITCH_FAILED`、`nvidia-smi` 显存、第一个 32B 任务是否正常。若 `FILLER_HALT`，补位停止，worker 空闲 60 分钟后会退出、释放卡。

### 2026-10-08：文献检索与定位
- 整理在 `docs/reports/literature_positioning_2026-10.md`（Metis、Super Library Agent、Memory Transfer Learning、Evo-Memory、AgentCL 已对照全文核对）。定位：强模型上文字/抽象经验更好（Metis、MTL），7B 上代码片段更好 → 记忆形式取决于模型能力；Super Library Agent 同用 WebGen-Bench 但目标是可维护性、24 题、准确率不显著、不研究顺序。注意 Metis 的代码是被执行的工具，与我们的提示内片段不同，不能写成"直接矛盾"。
- 已同步论文（第 2 章相关工作 4 段、第 6 章讨论、bib 4 条并补全 Metis 题名）、PPT（新增"相关工作与定位"页，修正"关键发现"页原先"与 Metis 一致"的错误说法，参考文献页）、README。
- 14B 下载作业 23430 已取消（10-08 用户决定不做 14B，见 DECISIONS）；32B 作为未来工作。

### 2026-10-08：固定前缀消融已排队（14B 已取消，下面的 14B 步骤留作 32B 参考）
- 集群 `filler.conf` 末尾加了固定前缀（备份 `filler.conf.bak-before-fixed-prefix`），整体：只有清单（v7）→ 种子 11 → 29 → 47 → 交错 → 固定前缀，预计约 10-15 全部完成。src、配置、`worker_lib.sh`、`start_services.sh` 已同步（v7 行为不变，见 DECISIONS）。
- 14B 待做：下载权重到 `/data/qma258/models/WebGen-LM-14B`（长任务需放进 Slurm 作业）；当前 worker 退出后，用 `WEBGEN_GENERATOR_WEIGHTS=WebGen-LM-14B`、`WEBGEN_GENERATOR_API_MODEL=WebGen-LM-14B`（注意 `.env` 里也有该变量）另提交 worker；先试启动确认显存，再按 manifest 顺序跑 Long Memory/No Memory 的 P 行。

### 2026-10-08：投稿评估与后续计划（用户讨论）
- 评估：作为硕士论文已扎实；投稿现在够 workshop，主会还差关键实验。主要质疑：只有一个 7B 生成器/基准/框架；代码池可能等于固定前缀；在同一基准上迭代（过拟合）；记忆模型 72B 强于生成器；与 Metis 的区别要写准。
- 计划：先按时交论文（10-16 更正：10-19 周一交）；之后补 ①固定前缀消融 ②WebGen-LM-14B ③留出验证（前 30 定版、后 71 报告，无需新跑），短期投 workshop，补完考虑 ACL/EMNLP Findings。会议截稿日期待查当期征稿。已写进 PPT 下一步页、论文 Future Work、README。

### 2026-10-08：顺序实验已排队（集群）
- 顺序文件 `data/experiment_splits/task_orders/{blocks_seed11,random_seed29,blocks_seed47,interleave}.json`（`scripts/make_task_orders.py`；同领域相邻对数：manifest 81/100，blocks 81，random 6，interleave 0）。
- `worker_lib.sh` 的 `filler_next` 新增 `P ORDER LM_OUT NM_OUT [LM_CFG]` 行：按顺序文件逐题，位置偶数 L→N、奇数 N→L；顺序文件复制到各输出目录 `task-order.json`。本地模拟 404 步核对通过。已同步集群，并排了一个空操作 `reload-filler` 让补位脚本重启加载新代码。
- 集群 `filler.conf`：只有清单（v7）→ P 种子 11 → P 种子 29 → P 种子 47 → P 交错（10-08 曾缩减为两个，讨论后恢复，备份 `filler.conf.bak-before-readd`）；No Memory r2（manifest）已删除。输出 `outputs/experiment/cluster_order_<名>_{longmem_v7,nomem}`。每个顺序约 30 小时：11、29 约 10-11 完成，全部约 10-13–14；10-16 组会。
- **作业上限：** 23385 于 10-06 开始，30 天上限约 11-05，足够。

### 2026-10-08：后续 Long Memory 的顺序鲁棒性计划（尚未启动）
- **（10-08 更新）最终设计见 DECISIONS「顺序鲁棒性实验的最终设计」：领域挨着（种子 11、47）vs 领域打散（种子 29 完全随机、交错）各 2 次，按 11 → 29 → 47 → 交错 的优先级排队；每个顺序 Long Memory/No Memory ABBA 成对；消融不随顺序重复。下面是 Codex 的原方案，仅作记录。**
- 用户确认一次完整 101-task global run 约 24 小时，成本不是主要约束。等 v7 或后继版本的 scaffold/import 问题修好且版本冻结后，做 4 次从空库开始的 Long Memory：当前 manifest/domain-block 顺序、seed=11 分层 shuffle、seed=29 分层 shuffle、跨 domain 轮换交错顺序；每次保存精确顺序、seed、检索/注入和评测原始结果。
- No Memory 做 3 次完整独立复跑，分别与前三种执行顺序配对，作用是量化生成器/基础设施/UI evaluator 波动；其 shuffle 本身不是 treatment。第四次若追求完全对称可加跑 No Memory。正式统计按 task 配对做 Long Memory−No Memory、bootstrap CI，并分 domain、来源域别及执行位置报告。完整决策和解释见 DECISIONS「2026-10-08：Long Memory 顺序鲁棒性正式实验」。
- **模型/agent 扩展的最终优先级（用户确认）：** 不做多模型×多 agent 全矩阵。先完成已冻结 WebGen-LM-7B + Bolt 的顺序鲁棒性主实验；其收益若稳定，再只加入一个生成 LLM、agent 仍固定 Bolt。候选定为 **WebGen-LM-14B**：同一 WebGen-LM 训练家族和输出协议，能最小化实现差异，直接检验长期记忆是否仅对 7B 有效。对它跑 domain-block 与跨-domain 交错两种顺序，且每种顺序 Long Memory/No Memory 都按 ABBA 交叉执行，共 4 个完整 global run。不要改用通用 Qwen2.5-Coder-32B 作这一主对照：WebGen 原论文中它的裸 Bolt 基线很低，容易把协议/生成失败误判为记忆失效。
- **agent 放后面的原因与边界：** 原 WebGen-Bench 虽做了 Bolt/OpenHands/Aider × 多 LLM 的基准矩阵，但那回答的是生成系统强弱；本项目先回答 memory 的因果效应。换 OpenHands/Aider 会同时改变文件操作、上下文、prompt 注入接口和 repair loop，等同重做 agent-specific memory integration，不能与 Bolt 结果直接归因比较。因此只在 7B 顺序鲁棒性和 14B 对照均成立后，做约 20 题的跨 agent integration pilot（按 domain 和 v7 胜/负/平分层）；接口送达与运行稳定后才决定是否扩至 101 题。
- **视觉模型的用途：** 不把不同视觉模型当作主生成实验的第一优先级。对已有全量截图用第二个强视觉模型复评 appearance；再从 v7 相对 No Memory 的胜/负/平中分层抽样，用第二个 GUI/视觉评测器复核功能结论，重点是白屏、interaction-budget exhaustion 与疑似误判。这是评测稳健性检查，可复用已有 artifacts，远低于重新生成完整 benchmark 的成本。

### 2026-10-08：v7 101 题跑完（最终结果，单次运行）
- 准确率（按检查数合计）/ 外观 / 零分：No Memory 28.5% / 3.25 / 30，v4 30.9% / 3.21 / 20，**v7 40.0% / 3.21 / 13**。前 30 题：26.0 / 39.3 / 39.0；后 71 题：29.5 / 27.8 / **40.4**（零分 19 / 19 / 9）。
- 按任务配对：v7−No Memory 平均 +11.5 个百分点（bootstrap 95% CI [6.0, 16.9]，胜 54、负 24、平 23）；v7−v4 +8.9（[2.9, 15.1]）。v7 的 13 个零分题中 10 个 No Memory 也是 0。
- 外观：只看两组都有可用网站且有外观分的 68 题，No Memory 3.25、v7 3.22 → 增益只在功能，不在外观（局限措辞据此确定）。注意外观均值只算有评分的任务，与 67 题中期报告的口径不同。
- 学习曲线已用 101 题重画（曲线是逐题平均，终点 40.8/31.9/29.3，与按检查数合计的数字略有差别）。论文初稿 `docs/thesis/`（Overleaf 包 `docs/thesis_overleaf.zip`）已更新这些数字；PPT 尚未更新（按 `docs/reports/ppt_todo.md` 阶段 1）。
- 工人作业 23385 已转入"只有清单（v7）"消融。
- 10-08 用户决定删掉队列第 5 项（旧版 v4 只有清单，4/101，已被 v7 版消融取代）：`filler.conf` 中注释掉，备份 `filler.conf.bak-drop-old-abl`。剩余队列：只有清单（v7）→ No Memory r2，预计 10-10 上午跑完，空闲 60 分钟后作业退出。

### 2026-10-08：v7 单页缺 import 为什么没压住（101 题分析，v8 方向）
- v7 有 22 题某页缺 Vue import，No Memory 23 题，基本相同；整站白屏则 26→8。按文件分类：`ref` 用了但整个文件没有任何 vue import 16 处；已有 `import { ref } from 'vue'` 却漏了 `computed` 8 处（另 onUnmounted、computed 无 import 各 1）。No Memory 是 ref 无 import 15、漏 computed 12，结构相同。
- 原因：代码池里的 `vue-api:any` 条目在第 6 题（来源 000018）建好后就再也没更新。代码一直是 `import { ref } from 'vue'` + `const bookingId = ref('')`，说明文字也停在"3 tasks"；但 support 已累积到 22 题，其中一半是漏 computed。示例只教了 ref，对漏 computed 没有帮助（甚至示范了"只 import ref"），对整文件不写 import 的小组件（Contact 等页面）模型也没照做。
- v8 本地试验（`WEBGEN_CODE_POOL_REFRESH=1`，`src/code_memory.py`：示例随缺失 API 分布重建、覆盖 ref+computed（无单个小组件同时用两者，按 API 各摘一段逐字拼接）、缺包示例只给片段、规则兜底去掉 `<script>` 包装）。做法：v7 原 prompt 只替换代码池段，6 题只生成+编译检查（输出在 scratchpad `v8gen/`）。结果：缺 import 4 题只修好 000032（但文件框 v-model 编译错仍在），000088（App.vue 漏 computed）、000069、000075（子组件漏 ref）与 v7 相同；回归 000010、000072 正常（无缺 import，页面数相同或多 1）。
- 结论：按文件统计，v7 有 27/592 个 .vue 文件漏 import（约 5%），No Memory 27/586，和是否用 defineProps/defineEmits 无关，App.vue 和子组件都有。这更像随机的"笔误"，不是可被示例纠正的误解；1/4 的改善可能是偶然。按官方协议不能生成后补 import，所以暂不把此项作为 v8 主改动（待用户决定）。

### 2026-10-08：组会 PPT
- 幻灯片 https://claude.ai/artifact/4hFFsiPiUgY397YXaZhNqE（33 页，源文件在 `docs/reports/group_meeting_deck_2026-10/`）。按实验阶段要补的内容（v7 跑完、消融跑完、顺序实验跑完、外观核对）记在 `docs/reports/ppt_todo.md`，到对应阶段直接按清单更新。

### 2026-10-08：v7 剩余 2 个脚手架的原因与修复（本地，未同步，候选冻结版）
- v7 的 000001、000011 交了脚手架（No Memory、v4 在这两题都写了真代码但也是 0 分）。000001 本地对照：去掉缺 import 示例仍是脚手架，去掉页面切换示例（整份别站的 `App.vue`）即生成 StockSearch/ReportDisplay → 原因是"完整文件"形式的示例，与 v6 的问题同源。
- 修复（`src/code_memory.py` `_pick_fragment`）：缺包类代码记忆也只给片段：记忆模型挑关键行，代码核对逐字、≤15 行、不含 `<script>/<template>` 标签行、须含模板里的行；72B 两轮都挑不对时退回规则摘取（去掉标签行、本站页面的 import、纯闭合标签）。另修：模型把多行放在一个字符串里时先拆行。说明句写中性事实"下面这个能用的文件不用那个包做到同样的事"。
- 验证（只查代码）：000001 生成真实网站；000011 不再是脚手架（11 个页面），但用了未声明的 vue-router（与 No Memory/v4 同样 0 分的题）。回归 000010/000072/000068（v7 高分且带示例）：都无 router、无缺 import，页面数与 v7 相近。
- 队列（用户决定）：v7 → **No Memory r2** → 只有清单。v7 70/101，约 12 分钟/题，还需约 6 小时。

### 2026-10-08：v7 在集群运行（67/101 时的中期结果）
- v6 跑 13 题（014–030）后被 v7 替换（v7 = v6 + 代码示例须含调用行、无 `<script>` 包装 + 统计块不注入；配置 `long_memory_cluster_v7.json`，输出 `cluster_longmem_v7_webgenlm7b_r1`，已拉到本地，不含 node_modules/zip）。`filler.conf`：v4 → v7 → 只有清单 → No Memory r2。
- 同 67 题（准确率/外观/零分）：No Memory 30.8%/2.42/18，v4 35.3%/2.79/8，**v7 42.6%/2.91/7**。第 31–67 题：34.3% / 31.2% / **45.7%**；第 51–67 题：33.7% / 27.8% / **48.4%**（零分 3/4/0）。逐题 v7 胜 No Memory 36、负 18、平 13。
- 后 37 题的代码问题（题数）：整站白屏/编译错 No Memory 6、v4 7、v7 1；缺 vue import 9、11、4。v7 有 2 题交脚手架（31–50 之间，原因待查）；统计块 0/67。
- 学习曲线图 `docs/reports/learning_curve_v4_v7.png`（脚本 `scripts/plot_learning_curve.py`，101 题跑完后重画）。单次运行，任务顺序固定。

### 2026-10-07 夜：v4 跑完、v6 上集群、代码示例修正、short CoT 放弃
- **v4 101/101 完成**（准确率/外观/零分）：全部 No Memory 29.3%/2.35/30，v4 31.9%/2.57/20；前 30 题 24.0% vs 40.8%；后 71 题 31.6% vs **28.1%**。v4 的优势全部来自前 30 题，后面略低于 No Memory。
- **v6 已上集群**（工人作业 23385，`filler.conf`：v4 → v6 → 只有清单 → No Memory r2，备份 `filler.conf.bak-v6`），从空库开始，输出 `cluster_longmem_v6_webgenlm7b_r1`。集群新装 `@vue/compiler-sfc` 3.5.43 于 `/data/qma258/opt/vue-compiler`，`worker_lib.sh` 导出 `WEBGEN_NODE`、`WEBGEN_VUE_COMPILER_PROJECT`。第一题 000014 正常（0.40，编译事实已算出，代码池为空属正常）。**v6 冻结运行，没有固定停止点；只有本地证明 v7 有效才换（用户决定）。**
- **代码示例修正（已在 v6 中）：** 原"缺 computed"代码记忆的示例里根本没用 computed（只挑第一个好网站、且 40 行上限滤掉了写对 computed 的组件）。现按失败任务中各 API 被漏 import 的次数挑示例（只取 `<script>`），再由记忆模型挑关键行、代码核对（逐字来自源文件、含最常漏 API 的 vue import、≤15 行，不通过重挑一次，再不行退回规则摘取）。存经验时只做一次。结果模型只挑了一行 `import { ref, computed } from 'vue'`。回归 5 题（只查代码）：066/075/067 无缺 import 且能编译；003 仍漏 `ref`（文件里一行 import 都没写）；032 文件上传框 `v-model` 编译错（只出现在 <2 题，代码池不建）。
- **v6 严重问题：一行 import 示例让模型直接交脚手架（v7 修复，仅本地）：** v6 的代码记忆示例只有 `<script setup>` + `import { ref } from 'vue'` + `</script>`，像一个写完的空组件。v6 中带该示例的 6 题里 020、026 输出原封不动的 Vite 脚手架（只有 App.vue/HelloWorld.vue），不带示例的前 6 题 0/6。026 本地对照：去掉统计块仍是脚手架，再去掉示例即生成 PollList/PollResults → 原因是示例，不是统计块。修复：模型挑的关键行必须再含一行调用该函数的代码（代码核对），且不加 `<script>` 包装，只给代码行。本地重生 026、020：都生成真实页面（026 PollList/PollResults；020 四个功能组件），020 仍有一个组件漏 `ref`（单页）。
- **统计块泄漏（v7 修复，仅本地，未同步集群）：** v6 有 3/10 个 prompt 带了"RECORDED OUTCOMES…"统计块（v4 1/101）。原因：`condense_packet` 在"没有 guidance 条目"和"压缩无可用结果"两条路径上原样返回 packet，统计块没被清空；按 10-01 决定统计只用于排序、不注入。已改为这两条路径也清空统计（`replace(packet, statistics="")`）。v6 冻结，不同步；**注意以后同步 src 到集群会把它带上，要等 v7 决定后再同步。**
- **short CoT 放弃（用户决定）：** 在 prompt 末尾要求"先按文件列出用到的 vue 函数再写代码"，5/5 都没有生成任何文件（WebGen-LM-7B 只回规划文字，丢了 Bolt 格式）；对照组旧 prompt 正常。
- **通用池小实验无结论：** 010/033/065 原样 vs 去掉通用池：0.25/0.25、0/0.40、0/0；差异来自是否漏 import（033 原样漏 ref，065 两份都漏 computed），不是通用池。待 v6 压住缺 import 后再用 v6 prompt 重做。

### 2026-10-07 晚：v5 本地打分（5 题，本地 32B 评测，单次）
- No Memory / v4 / v5：032 0.83/0/0（v5：v-model 用在 prop 上，编译错误）；003 0.80/0/0（v5：用了 computed 却没 import，运行时空白）；067 0.75/0/0.75；066 0.67/0.17/0.17；075 0.79/0.36/0.43。
- 结论：代码记忆让模型不再用 router，但 7B 会犯多种小错误，修掉一种常换成另一种（打地鼠）。v6 要扩大代码能检测的错误类型（例如 Vue API 用了没 import、v-model 用错位置），并接受官方协议下白屏无法清零。
- 本地评测注意：评测前挪开旧的 `extracted/`；任务文件用 No Memory 目录的 `task.jsonl`；复制任务时要带上 `000001.json` 聊天记录。

### 2026-10-07 傍晚：编译检查补漏
- 原来的编译检查只单独编译 template，不知道哪些是 prop，漏掉了"v-model 用在 prop 上"这类错误（v5 本地 000032 打分时白屏才发现）。`code_memory.py` 和本地检查都改为 `compileScript(..., inlineTemplate:true)`（和 Vite 一样把 script 和 template 一起编译），已同步集群（v5 尚未开始）。按新检查，v5 本地 5 题：003/067/066/075 能编译，032 仍白屏（Search.vue 的 v-model 用在 prop 上）。
- 本地评测报 "module is not defined" 的原因：生成脚本把网站解压到 `extracted/`，评测脚本在同一目录写 `ecosystem.config.js`，读到网站的 `"type": "module"`。评测前把旧的 `extracted/` 挪开即可。

### 2026-10-07 下午：v5 已排队（v4 之后）
- v5 = v4 + `code_memory`（`src/code_memory.py`：代码检测之前任务网站的"未声明的 import""模板编译错误"，≥2 个任务出现时，从自己以前成功的网站（分数 ≥0.5、无未声明 import、能编译）摘代码作示例；说明文字不点名包；按内容指纹缓存 `code_facts.json`；扫描上限 600 秒；必须有当前任务 id，否则不运行）+ `common_pool_concrete_only`（通用池只留含具体写法的条目）+ `checklist_min_coverage: 0.6`（清单覆盖需求实词低于 60% 或少于 2 条则带缺词重拆一次，再不行用句子兜底）。配置 `config/long_memory_cluster_v5.json`；v4 配置不含这些开关。
- 本地验证（v4 记忆库、留一任务、只生成 + 编译检查）：000032/003/067（v4 零分白屏）全部能编译、无 router；000066 正常；000075 第一次出现"缺结束标签"，只改标题措辞后消失，去掉代码记忆也正常 → prompt 微扰敏感，非系统性。000003 清单从 1 条重拆到 8 条（覆盖 0.35→0.96）。
- 评论家子代理两轮审查，第二轮无阻塞问题。论文须注明：示例由其他任务的最终分数挑选（留一任务，允许）；触发后几乎每个任务都带同一段 App.vue，接近固定前缀。
- 队列（更正，用户决定）：v5 只做本地调试版本（用 v4 的库），不上集群；集群队列为 v4 → 只有清单 → No Memory r2，v6 准备好后插队、从空库开始。
- 同步时附带：记忆模型调用的瞬时重试不再重复处理 429（单元测试发现）；`preview_guidance.py` 现用 `bolt_memory_prompt`（含标题），并有 `--prompt-out`。

### 2026-10-07 中午：队列 = v4 → 只有清单（无记忆）→ No Memory r2；v3 放弃（用户决定）
- 新开关 `memory_write`（默认 true）：false 时 runner 在 continual 模式下跑完提示流程后什么都不存（无 trajectory/反思/case/统计），每个任务都从空记忆开始。配置 `config/long_memory_cluster_checklist_only.json` = v4 + `memory_write:false`，输出 `cluster_checklist_only_webgenlm7b_r1`。用途：区分 v4 的提升来自清单（prompt 改写）还是记忆。
- v3 不再跑：没有清单的记忆组用旧 Long Memory r1 作参照；需要时再跑"v5 去掉清单"。
- 重试：记忆模型调用遇到坏 JSON/空回复/连接错误时最多试 3 次（`transient_retries` 有记录）；补位脚本整任务失败上限 2→3 次。
- v5 待做（代码可先写，v4 跑完后再跑）：①代码记忆（从自己成功的网站摘页面切换/文件上传写法，编译通过且 ≥2 任务出现才入库）；②合并/过滤泛泛的通用池条目（"确保表单字段有标签"60 次检索注入 31 次）；③"交互次数用完"难修，最低优先级。
- v4 零分任务（57 题时）：032（文件框 v-model 编译错）、003/067/096（vue-router）、002（待查）。

### 2026-10-07 上午：准确率口径更正（重要）
- 之前算准确率时把每个任务的外观评分记录（outcome=`scored`）当成功能检查计入分母，所有准确率都偏低；本节之前 HANDOFF 里的 24.7%、24.8/24.7、34.7/41.1、v4 38.5 vs 24.6 等数字作废。
- 正确口径（去掉 `scored`）：No Memory 101 题 28.5%（论文 28.4%）、外观 2.34、零分 30；旧 Long Memory 84 题 28.6%、2.02、零分 33；v4 57 题 38.5%、2.96、零分 4。三组共同 55 题：No Memory 33.8%/2.42/零分 14，旧 Long Memory 32.6%/2.16/19，v4 38.3%/2.96/4。
- v4 夜里崩溃的 6 题已全部重跑成功；清单步骤失败时改为"代码按需求句子拆清单"（仍是 v4 形式，记录 fallback），不再退回 v3 形式。

### 2026-10-07 早：v4 第一晚结果（初步，单次运行）
- 工人作业 23385 于 10-06 23:57 开始。v4 一夜完成 42 个有成绩的任务。与 No Memory 同 42 题：准确率 38.5% vs 24.6%，外观 2.95 vs 2.24，零分任务 3 vs 13，用 vue-router 2 vs 10。三组共同 40 题：No Memory 25.7%、旧 Long Memory 25.7%、v4 38.3%。
- 注意：本地诊断里"只给清单"4 题有 3 题用 router，集群上 v4 反而很少用 router，原因待查（集群 v4 的清单拆得更细、用需求原句？）。
- 6 个任务夜里崩溃（000004/020/026/033/034/055，崩在生成前，日志被覆盖）；复现 000020 正常跑完。已加：清单步骤异常时退回 v3 形式；每个任务单独日志 `runner-<id>.log`。已清掉 v4 的失败记录，这些任务会被重跑。它们按官方协议若最终失败要算 0 分，比较时必须计入。
- 监控脚本的告警解析 bug 已修，重新监控中。

### 2026-10-07 凌晨：v4 代码已写入（未实测）
- 开关 `requirement_checklist`（默认 false）；配置 `config/long_memory_cluster_v4.json` = v3 + 清单。已同步集群，v3 不受影响。
- `build_checklist`（`src/reflection_case_memory.py`）：记忆模型把需求拆成清单、把每条 guidance 原文挂到对应条目；代码检查：note 必须是 guidance 原文，没挂上的进"General notes"；清单条目和需求没有共同实词（排除 page/website 等泛词，颜色条目除外）就丢掉（防止从经验里带进需求没有的功能，如 056 的"导航栏"）；格式错重试一次，再错退回普通 guidance。没有 guidance 时也出清单。
- 假模型冒烟测试通过。用户决定直接上集群：filler.conf 顺序 v4 → v3 → N r2（v4 出崩溃 bug 时每个任务失败两次即跳过，自动转 v3）。第一个 v4 任务完成后检查 prompt 和清单。
- 已知风险：只给清单时本地 4 题有 3 题用 router（白屏）。

### 2026-10-07 凌晨：No Memory 跑完；队列改为 v3 → N r2（N r2 只为占住资源），v4 准备好后插队；v4 = 需求原文 + 清单 + 经验挂条目，全自动、不含人工经验（用户澄清）
- No Memory 101/101：准确率 24.7%、外观 2.34（32B）、全零分 30；论文基线 28.4%/2.5（GPT-4o）。配对 84 个：No Memory 24.8% vs 旧 Long Memory 24.7%；全零分 24 vs 33；只看非零分任务 34.7%（60）vs 41.1%（51）。即旧 Long Memory 在能运行的网站上更好，但多出 9 个零分任务，相互抵消。
- 前 30 个任务偏难（No Memory 22.2%、零分 37%、白屏占失败 41%），后 71 个 25.6%、零分 27%、"交互次数用完"占失败 49%。
- 之前报的"Long Memory 30% 左右"是早期少量任务的数字（前 11 个 28.5%），以后报告注明任务数与算法。
- 工人作业 23385 等 2 张 H200（节点只有 7×H200）。v4 = 原文需求 + 清单 + 经验挂条目 + 自摘代码示例（编译通过、≥2 任务出现才入库，参考 Metis）；冷启动时无代码示例的处理待定。

### 2026-10-06 23:00：需求拆成清单的诊断（只生成 + 编译检查，不评测；32B 拆解）
- v3 重建（`local_diag_v3c`，5 题）：与 No Memory 页面覆盖相近；056 仍因通用池"导航栏"一条用 vue-router 白屏（去掉该条即不用）。压缩时告诉记忆模型"只装了 vue"反而让 032 写出 "using Vue's router"，已撤回；改为压缩后再跑一次可执行性过滤（已同步集群）。
- 需求→清单、guidance 挂到对应条目（`local_diag_checklist`）：页面更全（038 首次有预订和预订记录），但 3/4 用 vue-router。
- 清单 + App.vue 的 ref/v-if 代码示例（`local_diag_checklist_code`，人写的上限诊断）：3/4 不用 router，035 多出托管页、038 有预订记录、056 四个功能页齐全；032 仍用 router。代码层面 2/4 优于 No Memory。
- 方向：v4 = 原文需求 + 清单（记忆模型拆解）+ 页面结构代码示例（需由反思产出，不能手写进记忆）。v3 今晚照常跑作对照。

### 2026-10-06 22:00：v3 Long Memory 已排进工人作业（用户决定：夜里先跑 Long Memory，再跑 No Memory，不停）
- `queue/filler.conf` 顺序：L `cluster_longmem_v3_webgenlm7b_r1`（`config/long_memory_cluster_v3.json`，新库从头）→ N r2 → N r3（旧的 v2 L 行已删，备份 `filler.conf.bak-v3`）。filler.conf 支持第三列为该 run 的 memory config，每个任务前会重置为默认。
- 已同步：v3（源头去重、效用、可执行性过滤、hard_match、hard cap、3 条/0.5 倍）+ Codex 的"具体做法保真"。
- **修了一个会让整夜崩溃的 bug：** `case_supports` 表原来只允许 appearance，新的功能经验去重一写入就报 CHECK 错。已改成允许 functional；旧库插入失败时改为存成新经验，不再崩溃。假模型冒烟测试（存→去重成支持→检索→改写→压缩→输出）通过。
- 估时：工人作业要等 No Memory 23372 结束并空出 2 卡；Long Memory 约 11 分钟/任务，101 个约 18–19 小时，之后 No Memory r2 约 10 小时。

### 交接给 Codex（2026-10-06 晚，Claude 写；用户外出，授权自行决定、事后汇报）
- **集群：** No Memory 23372 已完成 40/101（到 000062 附近），约 6 分钟/任务，预计还要 6 小时。工人作业 23385（2 卡）JobHeldUser，要等 23372 结束且有 2 张空卡。Long Memory 暂停（用户：排查清楚前不跑）。不要取消/重交作业。
- **本地诊断（只生成不评测，用户要求：看代码能判断就不送评测）：** 任务 000032/035/038，本地 Bolt 5186 + 集群 7B（隧道 38417）。快速检查：解压 `000001.zip`，用 `@vue/compiler-sfc` 编译模板，列出 `.vue` 文件看页面覆盖。
  - `local_diag_v3`：诊断脚本漏了 guidance 标题，结果作废（脚本已改为调用 `bolt_memory_prompt`）。
  - `local_diag_v3h`（v3 条目 + 正确标题）：032 编译错误（文件上传框用 `v-model`），035 只有买家/卖家，038 只有搜索/列表。
  - `local_diag_pitfalls`（标题改为 "KNOWN PITFALLS (NOT A FEATURE LIST)"、强调需求才是清单）：输出与 v3h **完全相同**。结论：标题/声明措辞对 7B 无效。
  - No Memory（集群）同 3 任务：032 四块齐全；035 买家/卖家/管理员；038 搜索/列表。所以 035/038 的窄覆盖主要是模型本身的习惯，不是 guidance 造成。
  - `local_diag_rewrite`（人工把负迁移条目改成具体做法：ref+v-if 页面切换、组件内示例数据、导航按钮等）：3 个都能编译、页面最全（038 有预订和记录）。是目前唯一明显优于 No Memory 的变体（只看代码，未评测）。
  - 本地评测脚本现报 `ReferenceError: module is not defined in ES module scope`，未修（用户说先不评测）。
- **建议下一步：** ①查 032 的 `v-model` 文件上传错误由哪条 guidance 引出（v3h 条目里有 "verifying consistency" 等）；②让反思/改写产出"具体做法"（像 rewrite 那样），而不是"注意某某"；先在这 3 个任务上只生成 + 编译检查，2/3 优于 No Memory 再扩到 5 个（加 000056、000058）；③通过后再同步 v3 代码到集群、给用户运行前对比表。
- **v3 代码（本地，未同步集群）：** `src/reflection_case_memory.py` 的源头去重/效用/可执行性过滤/hard cap，`src/long_memory_runtime.py` 新开关，`config/long_memory_cluster_v3.json`。详见 DECISIONS 10-06 两节。
- **用户规则：** 全用中文回复；不用 Azure；小样本（3 个）快速验证，不跑一小时的批次；能从代码看出问题就不评测。

决策见 DECISIONS「WebGen 第二阶段」。只用学校资源，**不调 Azure**。
- **登录：** `ssh csml3`（`~/.ssh/config` 里的连接复用；需要用户在终端输入"密码:2FA"建立一次，12 小时内有效；需校园网或 VPN）。工作目录 `/data/qma258`；**home 配额只有 100MB**，所有命令先 `source /data/qma258/env.sh`（把 HOME、各种缓存、PM2 指到 `/data`）。
- **集群上的内容：** 代码 `/data/qma258/webgen`（从 Mac 用 rsync 同步，不含 outputs、node_modules、密钥文件）；模型 `/data/qma258/models/`；Python 环境 `venvs/webgen`（runner，包版本与 Mac 一致）和 `venvs/vllm`（vLLM 0.30）；Node 26.10、Chrome 154 在 `opt/`。集群 `.env` 只有本地服务的地址和随机密钥；`bolt.diy-Fork/.env.local` 只有 GitHub token（用户同意沿用现有的）。
- **作业：** `sbatch scripts/cluster/run_queue.sbatch`（`QUEUE_FROM`/`QUEUE_COUNT` 选 manifest 位置，已完成的会跳过）；日志 `/data/qma258/jobs/queue-<作业号>.out`，服务日志 `/data/qma258/logs/services-<作业号>/`。输出 `outputs/experiment/cluster_nomem_webgenlm7b_r1`、`cluster_longmem_webgenlm7b_r1`（在集群上）。
- **规则：** 长时间或占资源的东西都要放进 Slurm 作业，终端里只跑几秒的检查。作业先被自动审批挂起十几秒（`PENDING_APPROVAL`）属于正常。
- **当前（2026-10-05 下午，用户决定）：** No Memory 与 Long Memory 各自排队、互不等待，**作业任何情况下都不主动停**（任务异常只记 `health-warnings.jsonl`；服务挂了自动重启，失败则每 10 分钟重试），跑完再分析。No Memory 作业 23368（`ARMS=N`，1 卡，端口偏移 0，已完成 014–016 会跳过）；Long Memory 作业 23369（`ARMS=L`，2 卡，`WEBGEN_PORT_OFFSET=20`，每个作业独立的 PM2_HOME 和评测锁）。两组不逐任务交替。我取消重交时丢了排队位置，另外两个用户的作业排到了前面。Long Memory 第 3、5 个任务后检查反思提取、入库、检索（`scripts/cluster/inspect_longmem.py`），只记录不中断。
- **工人作业 23385（2026-10-06 14:00 提交，用户决定）：**
  - **设置：** `scripts/cluster/worker.sbatch`，2×H200，上限 30 天，端口偏移 40。模型只加载一次，之后按文件名顺序执行 `/data/qma258/queue/pending/*.sh`；队列空闲 60 分钟自动退出（遵守 Cluster Policies）。
  - **加任务：** `bash scripts/cluster/enqueue.sh NAME ITEM.sh`，工具函数在 `worker_lib.sh`。
  - **已排两项：** 白屏诊断 `items/diag_whitescreen_r1.sh`（输出 `cluster_diag_whitescreen_r1`），以及新版本（A+B+C）Long Memory 完整第 1 遍 `items/longmem_v2_full_r1.sh`（输出 `cluster_longmem_v2_webgenlm7b_r1`）。
  - **当前状态：** 挂起（JobHeldUser，每人卡数上限），等 No Memory 23372 跑完后自动开始。
  - **代码：** A+B+C 已同步到集群（14:00），No Memory 加载正常。
- **白屏诊断：生成器只听代码示例，不听文字（10-06 下午，本地 Bolt + 集群 No Memory 的 7B，经隧道；人写的上限诊断，不进记忆）：**
  - **设置：** 原本白屏的任务，原 prompt 不变，只在 guidance 第一条加一句，只生成、不评测。输出在 `outputs/experiment/local_diag_*`，脚本在 scratchpad（`diag_generate*.py`）。
  - **文字说明基本无效：** "把 vue-router 加进 package.json"1/3；"不要用 vue-router，用 v-if"1/3；不提 router、只说"页面写在 App.vue，用 ref + v-if"0/3；同一句放在 prompt 开头加末尾 1/3。模型的回复从不改 `package.json`。
  - **代码示例有效：** 一段约 10 行的 App.vue 示例（`ref` + `v-if`，只用 vue）救回 **7/9**（000030/032/035/056/059/075/100 都没再 import 未装的包）；000034、000096 仍用了 router。
  - **结论：** 对 WebGen-LM-7B，记忆要注入可以照抄的代码示例，而不是文字建议。下一步让反思自己产出最小代码示例（规则只给方法），压缩时代码示例单独保留。
  - **待做：** 这 7 个网站的功能和外观评测。
  - **另：** Bolt 的 Vue 模板仓库 `thecodacus/bolt-vue-template` 只有 2024-12 一个提交，模板里就没有 vue-router，所以论文基线用的是同一模板。
- **Long Memory 暂停中（10-06 16:00，用户决定）：** 集群队列里，白屏诊断移到 `queue/hold/`，`filler.conf` 里 L 开头的行已注释，只跑 No Memory 第 2、3 遍。下一版方案见 DECISIONS"经验去重在源头做……"：源头去重 + 效用排序 + guidance 按需求定量 + 可执行性过滤 + 只用 hard_match。先在本地小测：用当时记录的候选，32B 代替 72B，7B 生成，32B 评测，任务 000032、000035、000038。通过后再恢复队列。
- **补位与新增修改（10-06 14:30）：**
  - **补位：** `queue/pending/zz-filler.sh` 在没有其他任务时，按 `queue/filler.conf` 的顺序一次跑一个任务：L v2 r1 → N r2 → L v2 r2 → N r3 → L v2 r3。有新任务时它先让出，跑完再接着补位；任务失败两次就跳过（`filler-failures.txt`）。
  - **新增两处修改（已同步）：**
    - 反思规则：截图里的编号框和标签由评测工具画出，不属于网站；与此相关的原因算评测员的局限。旧库里有 20 条这类经验仍是 active，进过 4 个 prompt。
    - 反思超长：截完代码仍超长时，再截掉 GUI 步骤的中间部分（保留开头和结尾），000047 实测可以放下。
- **2026-10-06 13:20（用户决定）：** 停掉 Long Memory 23369（已完成 88/101，其中 84 个有成绩、4 个反思崩溃，最后停在 000090），数据已拉到本地。No Memory 23372 随即开始，**让它跑完全部 101 个**（作为珍贵的完整基线）。反思截断修复上线后触发 3 次，之后没有再崩溃。
- **2026-10-06 11:30 状态：** No Memory 实际作业号是 23372（等 Long Memory 让出 GPU）。Long Memory 23369 已完成 76/101，正在跑 000082，平均约 11 分钟一个任务。000018、000020 的检查结果正常：能检索到更早任务的经验，没有检索到当前任务自己的记录，通用池和压缩也正常。数据已拉到本地（`scripts/cluster/pull_outputs.sh`），跑完后要再拉一次。
  - **反思超长：** 000011、000046、000047、000057 在反思时崩溃。原因是反思请求超过 72B 记忆模型的 32K 上限，其中最大的部分是评测员的 GUI 步骤，其次是网站代码。这几个任务的评测结果都完整保存在 `tasks/<id>/continual/extracted`，成绩可以照官方规则从磁盘算出来，缺的只是它们留给后续任务的记忆。
  - **修复：** 10-06 中午已同步到集群，从下一个任务起生效。请求超长时，`AzureMemoryLLM.generate` 依次把网站代码（代码文件和生成器的回复）截到 50%/25%/10% 后重试，截断情况记在 progress 的 `reflection_context_trims`。估计只够救约一半这类任务；如果评测步骤本身就太长，仍然会崩溃。
  - **000014、000015：** 成绩被 PM2 问题弄错了，000015 还往记忆库写了 3 条错误经验。
  - **待用户决定：** 这几个任务是重跑，还是在两组对比里都剔除。
- **白屏分析（10-06，基于 76 个任务）：**
  - **白屏情况：** 74 个有效任务里 26 个白屏，整个任务 0 分。其中 19 个是 import 了 `vue-router` 却没有声明，1 个缺 `prismjs`，6 个是 Vue 模板编译错误。
  - **根因是模型行为：** 81 个任务都是 Bolt 的 `vite-vue-typescript-starter` 模板，依赖只有 `vue`。模型自己的回复从来不写 `package.json`，也不发 shell 命令（0/81）。
  - **反思和注入：** 反思都正确归因到缺 `vue-router`，但做法写成"确保正确安装"，模型执行不了。注入也不稳定。prompt 里有、没有这条时，用 router 的比例分别是 34% 和 26%。
  - **No Memory：** 已跑的 3 个里有 1 个同样白屏。
  - **第一阶段为什么没暴露：** 我们自己的 `deterministic_repair`（jsx_syntax）会自动把 `vue-router` 补进 `package.json`，两组都有这个补丁。官方协议关掉了它。
  - **官方情况：** 论文报告 WebGen-LM-7B 的 start failure 是 0%。但按官方定义，出现报错遮罩的页面算"已启动、判 NO"，所以论文并没有报告白屏率。官方用的是同一个 Bolt fork，自动选模板默认开着。
  - **Long Memory 很可能放大了白屏：** guidance 提到 route/router 时，13/18 个任务用了 `vue-router`；不提时只有 7/58。链条前 6 个任务都没用。这些提到 router 的 guidance 正是从白屏反思改写来的（如 "ensure router configuration imports the router library"），形成恶性循环：白屏 → 经验提到 router → 模型更常用 router → 白屏。
  - **待验证：** No Memory 跑完后，在同一批任务上逐个对比两组用 router 的比例。
- **A+B（+C）改动（已同步到集群）：**
  - **A（代码事实）：** `generated_code_evidence` 的 `code_manifest` 新增 `imports_not_in_package_json` 和 `generator_written_files`，都是代码算出的中性事实。
  - **B（反思规则）：** 新增通用规则 "Fix within reach"，原因已确认时，做法必须是生成器写自己的文件就能完成的具体改动。加在 `FUNCTIONAL_CASE_INSTRUCTIONS` 和 `IMPLEMENTATION_INSTRUCTIONS`，第 4 步也引用了新事实。
  - **测试工具：** `scripts/cluster/rereflect_local.py`（用本地代码重做反思，不写库）、`store_reflections_copy.py`（写进记忆库副本），`preview_guidance.py` 新增 `--memory-url/--embedding-url`（走集群隧道，不读 `.env` 里的 Azure）。
  - **计划：** 先做诊断试跑，用约 10 个白屏任务加约 5 个正常任务验证生成器会不会照做；正式结果仍要从头跑完整 101 个任务。
- **双周汇报（2026-10-05）：** `docs/reports/2026-10-05_WebGen_supervisor_update.pptx`（14 页，生成脚本 `docs/reports/2026-10-05_supervisor_deck_build.js`，需要 pptxgenjs）。其中错误分类与频次基于第一阶段 8 个共同任务、按评测员最终结论人工归类，不是第二阶段数据。

## SWE-bench 长期记忆（2026-10-05 封版，用户决定）

**封版：** 用户回到 WebGen 后，把 SWE 代码提交封版。swe-bench 仓库分支 `long-memory-swe` 的提交 `4a49e9d`，标签 `swe-phase-archive`（**都还没有推送**到 `origin`，和第一阶段的做法一样）。封版时的状态和遗留问题写在该仓库 `docs/long_memory_swe.md` 开头的「Status」一节。`outputs/`（轨迹、记忆库、评测日志）在 git 忽略范围内，只留在本机。没有正在跑的 SWE 进程；Codex 的 No Memory 第 2 批停在 37/50（`outputs/verified-django-nomem-v17-batch2`），第 1 批 50 题还没有评测。以后恢复这条线时，先处理下面的遗留问题 1、2，再跑 dev 第 2 组或正式第 1 批。

已定的协议和方法见 DECISIONS「SWE 阶段」；方法细节见 swe-bench 仓库 `docs/long_memory_swe.md`。早期试跑（Lite 题池、mini-SWE-agent v2.0.0、gpt-5-mini 生成等）的输出都在 `swe-bench/outputs/` 下，只作记录，不作结果。

### 环境与账号
- **代码**：`/Users/ma/Downloads/792/swe-bench`（`qiaopan/SWE-bench` 的 fork；long-memory 相关的改动已在 `4a49e9d` 提交）。runner 为 `swebench/long_memory/run_mini.py`，报告脚本为 `scripts/stage_report.py`，补换行脚本为 `scripts/fix_patch_newline.py`，抽样脚本为 `scripts/sample_lite_subset.py`。虚拟环境：`.venv` 装 mini-swe-agent **1.7.0** 以及记忆和 Jina 相关依赖；`.venv-eval` 装官方评测（两者分开是因为 huggingface-hub 版本冲突）。
- **Docker**：用 Colima（`--vm-type vz --vz-rosetta`，6 CPU、12GB 内存、150GB 磁盘）。评测时要设 `DOCKER_HOST=unix:///Users/ma/.colima/default/docker.sock`。`~/.docker/config.json` 里去掉了残留的 `credsStore: desktop`（备份 `.before-colima`）。固定版本的数据在 `data/swebench_verified/`（revision `78f471bf…`），凭据在 `.env`（git 忽略，权限 600）。
- **Azure（学校 Azure for Students，余额约 $57，2027-02-28 到期）**：资源 `ai-qma2582452ai373736301557`（Japan East）。部署有 `swe-generator-gpt5-nano`（2000K TPM，生成用）、`swe-reflection-gpt5-mini`（500K，记忆用）、`swe-generator-gpt5-mini`（1500K，目前不用）。价格登记在 `config/litellm_model_registry.json`。第一阶段的 `webgen-*` 部署都还在，没有动。
- **同事账号 `tuojihu@163.com`**：中国大陆注册，所有 Azure AI 模型（OpenAI、DeepSeek、Kimi、Cohere）都会被拒（`CannotDeployDueToLocalRegulations`），GPU 配额为 0，只有普通虚拟机可用。$200 赠金 2026-11-03 到期。用户决定不再管；账号里留着一个空的资源组 `rg-swe-memory`。
- **学校 Slurm 集群（129 = `sc448961`，分区 `pilot`，1×5090）**：GPU 只对 `sbatch` 作业可见；home 目录已清空（用户授权）。重新部署 vLLM 时要用 `+cu129` 的 wheel（驱动 575）、只监听 127.0.0.1，并加 `--api-key`。不要用 Qwen3.6-35B-A3B（用户否决）。

### 当前状态（2026-10-05 晚）
- **题目清单**：test 为 `config/swebench_verified_django_test100.json`（第 1 批 50 道，官方 nano v1.7 解出 16/50）；dev 为 `config/swebench_verified_django_dev10.json`（第 1 组 12050、12741、13279、13933、14493；第 2 组 14500、15525、15695、16595、16938）。
- **分工（用户 2026-10-05）**：Codex 跑 No Memory，Claude 负责 Long Memory。两边共用同一份代码：今晚不要在 `swebench/long_memory/` 里改 No Memory 会用到的部分（agent 运行、官方配置、价格登记、题目清单）。No Memory 的运行设置不记录记忆部分，所以记忆代码的改动不影响它。
- **No Memory dev**：`outputs/dev-verified-nomem-v17.clean`（Codex），已跑 8 题，原样评测和补换行评测都是 2/8（12050、12741 ✅），官方 nano 在这 8 题上是 3/8。15525、15695 是空补丁（agent 提交前自己 `git commit` 了）；14500 跑了整个测试套件，输出过长，超过 272k token 上限而中断。这些都是模型行为，官方配置下同样会发生。
- **Long Memory dev 运行记录**：`dev-verified-longmem-v17`（旧代码，前 3 题 2/3）→ `-fix1`（第一轮修正，0/3；12050 的修复本身对，但 agent 提交前 `git commit` 了，交上去的是空补丁，反思也没发现）→ **`-fix2`（第二轮修正，当前版本，dev 第 1 组 5 题全部跑完）**。同样 3 道题，三次运行分别是 2/3、0/3、3/3，单次运行的波动很大。
- **当前代码（「一个池 + 两种名额」）**：`PROMPT_VERSION` 为 `swe-memory-753931812ae5`，schema 4（旧库打不开，需要新的输出目录），单元测试 24/24。去掉了路由调用和 bug 池/通用池之分，改为名额 A（高频，代码统计）+ 名额 B（相关，模型判断加逐字引用），反思新增报错原文和 effect，报告新增「事后核对」，详见 DECISIONS「一个经验池 + 两种名额」。报错原文的核对在 dev 试跑中收紧过两次（源代码行不算报错），这只是代码改动，不改变 PROMPT_VERSION。`run_mini.py` 只改了 Long Memory 才会用到的配置项和事件字段。已提交（`4a49e9d`）。
- **`dev-verified-longmem-v17-slots2`（新设计，dev 第 1 组 5 题，原样评测与补换行评测结果相同）**：4/5（12050、12741、13279、13933 ✅；14493 是空补丁），对照 fix2 3/5、No Memory 2/5、官方 nano 2/5。花费：生成 $0.046，记忆 $0.077。注入的都是工作过程类经验（动作格式、rg、编辑脚本），与 bug 本身无关，**分数差不能归功于记忆**。机制：名额 A 按设计生效（13279 注入 rg；13933 注入格式和 rg；14493 注入格式、rg 和编辑脚本），并数到了反思没写经验的那几次；注入之后，13933 和 14493 都没有再出现格式错误和 rg 报错（之前 12741 格式错误 9 次、13279 2 次；13279 注入了 rg 也还是碰了 1 次），样本小，只能算提示。名额 B 一共判断了 8 次，全部拒绝或引用核对不通过，在 5 道互不相关的题上属于正常。先跑的 `-slots`（2 题）因为发现源代码被当成报错而中止，只作记录。
- **dev 第 1 组 5 题对比**（原样评测 / 补换行，两者结果相同）：Long Memory `-fix2` 3/5（12050、12741、13279），No Memory 2/5（12050、12741），官方 nano 2/5（13279、14493）。唯一的差别是 13279，但注入给它的两条是 grep 和 AST 重构的经验，与它的 bug 无关，**不能归功于记忆**。花费：Long Memory 生成 $0.064、记忆 $0.108；No Memory 生成 $0.055。
- **机制核对（`-fix2`）**：反思都如实写了「没有复现」；提交这一步在跑，但这次没有遇到空补丁，所以还没有在真实数据上验证过；路由基本一致；bug 经验全部被正确拒绝（5 题的 bug 互不相关）；注入的每条都有出处、没有新词、确实送达。
- **12741 用了 506 秒的原因**（旧运行）：agent 只用了约 1 分钟，其余时间花在一次很慢的 gpt-5-mini 调用上。已加超时（`-fix2` 中有一次调用耗时 211 秒，靠超时重试完成）。

### 遗留问题（`-slots2` 观察到；封版时未决定，恢复时先处理）
1. **空补丁的经验被存档**：14493 提交前 `git commit` 了，补丁为空。反思的「提交」这一步发现了不对，但把原因归给「评测框架没收到改动」，标成了不确定，于是被存档。根源是反思模型不知道交上去的补丁就是最后那条提交命令（`git add -A && git diff --cached`）的输出。建议在第 6 步说明这一点（这是对证据的说明，不是答案）。No Memory 第 1 批有 5/50 题是这样丢的。
2. **框架提示类的问题是否一次就进名额 A**（比如动作格式错误：它不是任何命令的输出，代码能判断它和 bug 无关）：用户还没决定。
3. **名额 A 的条目带着原题的细节**（例如「按 'class ModelChoiceField' 定位」）：代表经验取的是最新一条，压缩时没有把它泛化。影响小，先观察。
4. **分组偏松、一条经验混了两个原因**：这次的 rg 和 grep -S 被写成了一条（13279）；还会出现。
5. **gpt-5-mini 有时很慢**：14493 的反思用了 398 秒（超时后重试），只影响时间。
6. **单次运行波动大**：正式比较要靠 50 题，并在论文里写明是单次运行。

### 下一步
1. （恢复时）先决定遗留问题 1、2，然后再跑 dev 第 2 组或正式第 1 批（先给运行前对比表）。
2. 每批跑完都要做两次评测：先运行 `scripts/fix_patch_newline.py --output <目录>`，然后原样评一次、补换行再评一次（run id 加 `-eol`），最后运行 `scripts/stage_report.py --output <目录>`。每次付费运行前先给运行前对比表。

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
