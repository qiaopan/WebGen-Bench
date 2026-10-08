# 面向网站生成的跨任务长期记忆：第一阶段报告（WebGen-Bench，2026-09 至 2026-10）

> **状态：已封版归档（2026-10-03）。** 本仓库是 [WebGen-Bench](https://arxiv.org/abs/2505.03733) 的 fork，在其上实现并试验了网站生成 agent 的跨任务长期记忆（Long Memory）。由于 GUI 评测的资源开销和噪声过大，这条线暂停，后续可能转向 SWE 类基准。原 WebGen-Bench README 保留在本文末尾。
>
> - 结果快照：[`archive/phase1-webgen-2026-10/`](archive/phase1-webgen-2026-10/)（进度记录、记忆库、反思、prompt、回归集结果）
> - 决策与交接：[`docs/agent-memory/DECISIONS.md`](docs/agent-memory/DECISIONS.md)、[`docs/agent-memory/HANDOFF.md`](docs/agent-memory/HANDOFF.md)
> - 配套的 Bolt 改动：`bolt.diy-Fork` 子模块（分支 `diy-fork`）

## 摘要

我们研究：一个网站生成 agent 能否把已完成任务的评测结果反思成经验，在后续任务中复用，从而生成更好的网站。系统用 WebGen-LM-7B（Mac 本地 Q8_0）在 Bolt.diy 中生成网站，用 Qwen2.5-VL-32B 做 GUI 功能评测、GPT-4o 做截图外观评分；Long Memory 在每个任务后把每项未通过的检查反思成带证据的 case，下一个任务开始前检索、改写、压缩成几条 guidance 注入 prompt。

在两臂都生成出网站的 7 个任务上，当前 Long Memory 平均准确率 0.53，No Memory 0.40；Long Memory 在 4 个任务上更好、3 个更差。**这个差异不能作为结论**：样本只有 7 个，同一任务单次结果波动很大（同一任务 Long Memory 5 次运行在 0.08 到 0.67 之间），而且各任务的 Long Memory 结果来自不断调整的不同协议版本。

本阶段更有价值的是一组方法层面的发现：

1. **注入内容的“覆盖”比“长度”更关键。** guidance 太长会让 7B 生成器只写首页；但压缩时删掉某个需求功能，生成器就只实现 guidance 提到的那部分，被删的功能直接缺失。
2. **小模型的反思能看到现象，却很难追到根因**，而且同一 prompt 多次运行结果差异很大。需要回归集来评估 prompt 版本。
3. **基础设施问题会伪装成模型能力问题。** 例如 Bolt 的 Node 默认 300 秒超时让所有构建修复回复静默丢失；评测浏览器的深色模式让 Vite 默认样式变成白底白字。

## 1. 问题与动机

WebGen-Bench 要求模型从一段自然语言需求生成可交互网站，再由 GUI agent 按隐藏的检查清单逐项测试。WebGen-Agent 等工作用同一任务的评测反馈反复修复网站；我们关心的是另一个问题：**不使用当前任务的隐藏评测，只靠先前任务积累的经验，能否提升新任务的结果？** 这与 ReasoningBank、ExpeL 等“从经验中学习”的思路一致，但对象是代码生成加 GUI 评测这一高噪声场景。

## 2. 实验设置

| 角色 | 模型 / 环境 |
|---|---|
| 生成器 | WebGen-LM-7B，官方权重自行量化为 Q8_0，llama.cpp 运行于 Apple M5 24GB，经 Bolt.diy（OpenAI-like provider）生成项目 |
| 功能评测 | Qwen2.5-VL-32B-Instruct-AWQ（vLLM，RTX 5090），WebVoyager 式 GUI agent，每项检查约 15 步交互 |
| 外观评测 | Azure GPT-4o，截图 1–5 分 |
| 记忆（检索 / 改写 / 压缩） | Azure GPT-4o + embedding |
| 反思 | Azure gpt-5.4-mini |

- **任务：** WebGen-Bench 101 个任务按 20 个 domain block 排序（`data/experiment_splits/continual_domain_blocks/manifest.json`）。本阶段两臂共同覆盖 000014–000021、000026 共 9 个任务，其中 000018 的 Long Memory 当前无有效结果。
- **两臂：** No Memory（`--modes disabled`，不检索、不反思、不写记忆）与 Long Memory（`--modes continual --post-task-reflection --memory-representation case_only`，压缩配置 `config/long_memory_condensed.json`）。两臂使用同一生成器、评测器和构建修复流程（最多 5 次修复）。
- **计分（论文口径）：** accuracy = (Yes + 0.5·Partial) / 检查数；构建失败（start failed）单独统计，不计入准确率。
- **防泄漏：** 不使用当前任务的隐藏评测修复当前任务；检索、统计时只排除当前任务自身（leave-one-task-out）。计划从 000029 起两臂逐任务交替执行，谁先跑也交替。

## 3. 方法：Long Memory

### 3.1 记忆结构

三层，存于同一个 SQLite（`src/long_memory_schema.sql`）：

- `trajectories`：每次运行的不可变记录，包括 prompt、产物和评测结果。
- `reflection_cases`：每项失败或部分通过的检查对应一条 case，记录功能、触发、预期、观察、原因、预防做法、证据和原因可信度。
- `experiences` / `skills`：更高层的候选知识，经过 candidate → active/rejected 的准入。

另有 `memory_sources`（只追加的出处记录）以及统计表 `run_facts` / `check_facts`。

### 3.2 任务后反思（`src/post_task_reflection.py`）

- 每项未通过的检查单独调用一次反思模型。它只看到这项检查自己的评测轨迹、最后的截图、网站源码，以及代码事实（例如入口引入的全局样式表在 `:root/body` 上的全部声明）。
- 反思前必须按顺序填写 `investigation`，共 9 步：
  1. 读任务；
  2. 评测员是否真的到达目标，没到的话为什么；
  3. 看截图；
  4. 查报错；
  5. 沿代码链检查：路由 → 入口 → 挂载 → 数据或处理函数 → 渲染；
  6. 样式追踪：只在代码里有内容、截图上却是空白或看不清时做，按元素 → 父容器 → 全局样式表的顺序；
  7. 列 2–3 个候选原因，逐一用证据排除；
  8. 写结论；
  9. fix_check：只按这条经验改代码，这项检查能否通过。
- `cause_confidence` 只有网站缺陷被直接证据证实时才标 `established`。评测员自身的局限（交互次数用完等）一律标 `uncertain`，这类 case 存档但不参与检索。
- 每条经验另外调用一次路由：原因在所有页面共享的文件（入口、全局样式、路由、根布局）里，就标 `site_wide`，否则标 `feature`。site_wide 的经验按根因分组，每组只留一条进入通用池。
- 构建失败由代码直接生成固定标签的 `[implementation]` case，不交给模型起名。
- 每次反思记录 `prompt_version`（全部反思指令的指纹）。

### 3.3 检索与改写（`src/reflection_case_memory.py`）

1. 需求拆成至多 3 个功能 aspect 和 1 个外观 aspect。
2. 每个 aspect 用 embedding 取候选，由记忆模型判为 hard_match、soft_transfer 或 reject。每个 aspect 选一条，优先选还没被其他 aspect 选中的。
3. 对每个（case, aspect）组合，改写成当前任务可执行的做法。必须保留原 case 中“缺的那个元素”和原有的限定语，不能加入与需求冲突的要求。
4. 早期代码里写死过一个“首屏展示所有功能”的外观 aspect，它产生了与导航冲突的 guidance，已删除。

### 3.4 通用池与统计

- **通用池：** 收所有 `[implementation]` case，不经相关性判断。取至多 6 个候选（出现在 ≥2 个任务的“广泛”经验，加 2 个保底名额），按“出现次数 × 严重度”排序（failed 记 1.0，partial 记 0.5，构建失败按丢掉的检查数计），再泛化改写成适用于任何网站的要求。
- **统计：** 只记录事实和样本量，只用于排序，不直接注入 prompt。

### 3.5 压缩与注入

把检索和通用池的候选合并成至多 6 条 guidance，总长度不超过需求的 1.5 倍。规则如下：

- 每条以它对应的需求部分开头（如“Voting: …”“Every page: …”），是一句约 90 字符以内的命令式短句，不写验证句、不写空泛修饰词。
- **覆盖优先：** 每个功能候选都必须被某条 guidance 引用，只有“重复”或“不适用”可以删。代码会检查覆盖和每条长度，不满足就让模型重写一次。
- 通用池前两条保底。
- prompt 中需求原文在最前；guidance 开头写明“需求优先，这些注意事项不是完整清单”，结尾再提醒一句“需求列出的都要做”（利用 Lost in the Middle 的首尾效应）。

## 4. 结果（截至 2026-10-02）

| 任务 | No Memory | Long Memory（当前） | 其他 Long Memory 运行（已归档） |
|---|---|---|---|
| 000014 | 0.40（外观 3） | 0.60（3），未压缩旧版 | — |
| 000015 | 0.40（3） | 1.00（3），未压缩旧版 | — |
| 000016 | 0.50（2） | 0.17（2） | 未压缩 0.25；诊断副本（压缩）0.83 |
| 000017 | 0.58（3） | 0.33（3） | 去掉首屏 aspect 前 0.58 |
| 000018 | 0.67（3） | 待重跑 | 5 次：0.33 / 0.17 / 0.17 / 0.08 / 0.67 |
| 000019 | 0.33（3） | 0.42（4） | 未压缩 0.33 |
| 000020 | 0.50（3） | 0.40（4） | — |
| 000021 | 0.10（3） | 0.80（3） | 未压缩 0.10 |
| 000026 | 构建失败 | 0.40（2） | 未压缩 0.80（4） |

在两臂都有网站的 7 个任务（014、015、016、017、019、020、021）上：No Memory 平均 0.40，Long Memory 平均 0.53。**注意：** Long Memory 的 014、015 是未压缩旧协议，016–021 是 10 月 1 日的几个中间版本，026 又是 10 月 2 日的版本；同一任务多次运行差异很大。因此这张表只能说明“可能有正向信号”，不能作为记忆有效的证据。正式结论需要冻结协议、整体重跑，并对每个任务做多次运行。

## 5. 主要发现

**F1. prompt 送达本身就可能出错。** Bolt 的输入框把 Enter 当成“发送”，9 月 26 日之前带换行的 prompt 只送达了第一段，此前所有 Long Memory 生成实际上只看到了需求原文。已改为用 Shift+Enter 输入换行，并用聊天导出核对 `prompt_delivered`。

**F2. guidance 太长会喧宾夺主。** 未压缩的 guidance 约为需求的 5.7 倍，000016 两次都只生成了首页（0.25）；压缩后的诊断版生成了全部 5 个页面（0.83）。这与“上下文越长、表现越差”的文献一致（Du et al., 2025；Liu et al., 2024）。

**F3. 但 guidance 也会被当成“要做的全部”。** 000018 中压缩删掉了“状态查询”，000026 中删掉了“投票确认”和“结果页”，生成器恰好只实现了 guidance 提到的功能，被删的那些直接缺失。由此得出的规则是：压缩时**只缩短、不删除需求功能**。实现后，026 的 guidance 从需求的约 4 倍降到约 1.3 倍，且 6 条覆盖了全部功能。

**F4. 人为写死的设计假设会经由记忆放大。** 代码里写死的“首屏展示所有功能”外观 aspect，被改写成“落地页展示全部内容，不需要导航”，导致 000018 没有导航、000017 改用标签页。删除后，相应的导航检查恢复通过。

**F5. 评测环境本身会制造失败。** 评测浏览器使用深色模式，Vite 默认的 `src/style.css`（`:root { color: rgba(255,255,255,.87) }`）在白色卡片里变成白底白字。代码中内容完整，评测员却看不到，判为 failed。所有生成项目都残留这个文件，约一半引入了它，两臂都受影响。

**F6. 小模型的反思可靠性有限。** gpt-5.4-mini 能从截图看出“文字看不见”，但多数时候追不到全局样式表；它会把“看起来…”这样的猜测标成 established；分步输出变长后，还会把 JSON 字段嵌错层（已在代码里修复）；同一 prompt 两次运行可以分别得到 5/5 和 1/5。我们为此建了一个人工核对的回归集（5 个任务、18 项检查，`config/reflection_regression/gold_v1.json`、`scripts/reflection_regression.py`），各 prompt 版本的得分在 12–13/18 之间，版本之间的差异小于运行之间的随机波动。库中唯一一条“文字对比度”通用经验，只是某一次运行碰巧追到了 `style.css`，不易复现。用它解释后续任务的改善会有假阳性风险。

**F7. 基础设施问题会伪装成模型能力问题。**
- 修复前，Bolt 会先做一次非流式的“上下文优化”摘要调用；Node.js 内置 fetch 默认 300 秒收不到响应头就超时，AI SDK 再重试 2 次。Mac 上的 7B 写摘要超过 5 分钟，于是所有修复回复都静默丢失，6 次构建的代码完全相同。现已通过预加载把超时提高到 30 分钟（`tools/bolt-preload/`）。
- runner 把“修复次数用完”也当成可重试的故障，从头重新生成；在 temperature 0 下只会得到同样的项目。现改为直接记为构建失败。

**F8. “页面写了却没有入口”是这个 7B 生成器最常见的错误**（000016、000021、000026），即使 guidance 明确要求导航，也不总被遵守。

## 6. 局限

- 样本小（7–9 个任务），每个任务每臂只跑一次；GUI 评测和生成的随机性都很大。
- Long Memory 协议在实验过程中多次修改，链中混有不同版本的结果；正式比较需要冻结后整体重跑。
- 回归集的标准答案是人工判断（已发现并改正 1 处），而且只覆盖 5 个任务。
- 评测本身存在混杂因素：交互次数上限、深色模式、对下拉框的操作能力等，它们对两臂的影响不一定相同。
- 资源开销：每个任务每臂约 40–90 分钟（Mac 上生成约 10 token/s，加上 32B VLM 评测），101 个任务两臂合计需要数百小时。

## 7. 经验与后续方向

这一阶段可以迁移到下一阶段（例如 SWE 类基准）的做法：

1. 注入的记忆要**覆盖当前任务的全部要求**，长度只能靠缩短措辞来控制，不能靠删条目。
2. 反思要强制走排查步骤并留下记录（`investigation`），可信度要与证据一致，不确定的经验存档但不参与检索。
3. 改 prompt 时要配**回归集和多次运行**，避免“修好新任务、弄坏旧任务”；每条记忆都记录生成它的 prompt 版本。
4. 先确认“送达”和“评测环境”没问题，再讨论模型能力。
5. 结论不要手写进记忆：系统只给通用排查方法，具体经验必须由系统自己从证据中产出。

SWE 类基准用测试用例判定，结果更确定、成本更低，更适合检验“经验能否跨任务迁移”。

## 8. 代码地图与复现

| 位置 | 内容 |
|---|---|
| `scripts/run_continual_memory.py` | continual runner（两臂共用）；构建失败记录与不重试规则 |
| `scripts/catchup_remaining.sh` | 队列执行（启动前跑 preflight） |
| `scripts/preview_guidance.py` | 只跑第一、二阶段，预览 guidance（只读记忆库） |
| `scripts/compare_task.py` | 单任务两臂对比表 |
| `scripts/reflection_regression.py` + `config/reflection_regression/gold_v1.json` | 反思 prompt 回归集 |
| `scripts/replace_reflection.py`、`scripts/finish_post_task.py` | 替换或补做某任务的反思 |
| `scripts/backfill_prompt_stats.py` | 注入长度统计，导出 `prompt_length_analysis.csv` |
| `scripts/start_bolt_provider.sh` + `tools/bolt-preload/` | 启动 Bolt（带 30 分钟 fetch 超时） |
| `scripts/keep_tunnel.sh` | 评测服务器 SSH 隧道守护（登录信息放在 `.env` 的 `WEBGEN_EVAL_SSH_HOST`） |
| `config/long_memory.json` / `config/long_memory_condensed.json` | No Memory 与 Long Memory 的配置（改动会改变配置指纹） |

运行前用 `scripts/preflight_reflective_models.py` 检查五个角色均可用。完整输出目录（约 20 GB）不在 git 中，关键文件见 `archive/phase1-webgen-2026-10/`。

## 参考文献

已核对出处：

- Lu et al., 2025. *WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch.* arXiv:2505.03733.
- Lu et al., 2025. *WebGen-Agent: Enhancing Interactive Website Generation with Multi-Level Feedback and Step-Level Reinforcement Learning.* arXiv:2509.22644.
- Du et al., 2025. *Context Length Alone Hurts LLM Performance Despite Perfect Retrieval.* Findings of EMNLP 2025, arXiv:2510.05381.
- Liu et al., 2024. *Lost in the Middle: How Language Models Use Long Contexts.* TACL 12.
- Wallace et al., 2024. *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions.* arXiv:2404.13208.
- Shi et al., 2023. *Large Language Models Can Be Easily Distracted by Irrelevant Context.* ICML 2023.

待核对（凭记忆列出）：

- Curse of Instructions、ManyIFEval、IFScale（多条指令同时遵守）。
- ReasoningBank、ExpeL、Generative Agents、Reflexion（从经验中学习）。
- Zeller, *Why Programs Fail*；Agans, *Debugging: The 9 Indispensable Rules*；Kang et al., 2023 AutoSD；Chen et al., 2023 Self-Debug；Dhuliawala et al., 2023 Chain-of-Verification（排查与验证方法）。

---

# 原 WebGen-Bench README（上游）


This repository contains the code for reproducing the paper [WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch](https://arxiv.org/abs/2505.03733).

The dataset is also at 🤗 [luzimu/WebGen-Bench](https://huggingface.co/datasets/luzimu/WebGen-Bench) and on [WebGen-Bench (Kaggle)](https://www.kaggle.com/datasets/zimulu/webgen-bench). But for the running of this repo, you do not need to download the data from these sources, as the data is already placed under the `data` directory.

|Data | HF Links |
|---|---|
|WebGen-Bench | 🤗 [luzimu/WebGen-Bench](https://huggingface.co/datasets/luzimu/WebGen-Bench) |
|WebGen-Bench_train_data | 🤗 [luzimu/WebGen-Bench_train_data](https://huggingface.co/datasets/luzimu/WebGen-Bench_train_data) |

The **model weights** can be downloaded from:

|Models | HF Links |
|---|---|
|WebGen-LM-7B | 🤗 [luzimu/WebGen-LM-7B](https://huggingface.co/luzimu/WebGen-LM-7B) |
|WebGen-LM-14B | 🤗 [luzimu/WebGen-LM-14B](https://huggingface.co/luzimu/WebGen-LM-14B) |
|WebGen-LM-32B | 🤗 [luzimu/WebGen-LM-32B](https://huggingface.co/luzimu/WebGen-LM-32B) |

(The code under `src` was executed on a Windows 11 system. It should also run on Linux with minor adjustments. The code under `src-remote` was executed on a Linux server. This README often uses `deepseek/deepseek-chat-v3-0324:free` as an example. You can replace it with other models.)

The experiment outputs are placed under `outputs.zip`. It includes the output of the LLM-based agents that were tested in the paper. 

If you wish to deploy Qwen2.5-VL-32B-Instruct yourself for UI agent testing, or you wish to reproduce the training of WebGen-LM, you can download the necessary models using `src-remote\download\download.py`.

## Related Works

- **WebGen-Agent**: An advanced website generation agent that autonomously creates websites from natural language instructions. It iteratively generates website codebases and refines them using visual and functional feedback, including screenshot-based VLM feedback and GUI-agent feedback.  
  GitHub: [mnluzimu/WebGen-Agent](https://github.com/mnluzimu/WebGen-Agent)  
  Paper: [WebGen-Agent: Enhancing Interactive Website Generation with Multi-Level Feedback and Step-Level Reinforcement Learning](https://arxiv.org/abs/2509.22644)

- **FullStack-Agent**: A unified agent system for full-stack web development, consisting of FullStack-Dev, FullStack-Learn, and FullStack-Bench. It targets production-level full-stack website generation by evaluating and improving frontend, backend, and database functionalities.  
  GitHub: [mnluzimu/FullStack-Agent](https://github.com/mnluzimu/FullStack-Agent)  
  Paper: [FullStack-Agent: Enhancing Agentic Full-Stack Web Coding via Development-Oriented Testing and Repository Back-Translation](https://arxiv.org/abs/2602.03798)

## Testing Proprietary and Open-Source Models

### Installation

First, install Node.js following [Node.js Download Page](https://nodejs.org/en/download/).

Then, install pm2:
```batch
npm install -g pm2
```

To install WebVoyager:

```shell
conda create -p env\webvoyager python=3.10 -y
conda activate env\webvoyager
cd webvoyager
pip install -r requirements.txt
pip install numpy
# we encoungered a minor conflict, which we patched up by commenting proxies=proxies, in "env\webvoyager\lib\site-packages\openai\_base_client.py", line 738
```

### Testing Bolt.diy
<a name="test-bolt">
</a>

#### Installing and Starting Bolt.diy

First, install our forked version of Bolt.diy. Minor adjustments had been made to it in order to support automatic evaluation. 

```shell
git clone https://github.com/mnluzimu/bolt.diy-Fork.git
cd bolt.diy-Fork
npm install -g pnpm
pnpm install
```

Before starting the service, first copy the `.env.example` file and rename it as `.env.local`. Then configure the api keys and base urls. You should configure the LLM provider API of your choice in `.env.local`. (For example, create an openrouter api key at [Open Router AIP](https://openrouter.ai/settings/keys) and past it at `OPEN_ROUTER_API_KEY`.)

Also, remember to configer `VITE_GITHUB_ACCESS_TOKEN` with your github api, which will be used for importing templates.

Then run:

```shell
pnpm run dev
```

This will output something like:

```terminal

> bolt@0.0.7 dev D:\research\bolt\opensource\bolt.diy-Fork
> node pre-start.cjs  && remix vite:dev


★═══════════════════════════════════════★
          B O L T . D I Y
         ⚡️  Welcome  ⚡️
★═══════════════════════════════════════★

📍 Current Version Tag: v"0.0.7"
📍 Current Commit Version: "08d88c1"
  Please wait until the URL appears here
★═══════════════════════════════════════★
 warn  Data fetching is changing to a single fetch in React Router v7
┃ You can use the `v3_singleFetch` future flag to opt-in early.
┃ -> https://remix.run/docs/en/2.13.1/start/future-flags#v3_singleFetch
┗
  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

You can get the url of the Bolt.diy service after `Local:` (in this case: `http://localhost:5173/`).

#### Starting Automatic Testing

You can start automatic testing of Bolt.diy by running the following command, for example:

```batch
python src\automatic_bolt_diy\eval_bolt_diy.py ^
    --jsonl_path data\test.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenRouter ^
    --desired_model deepseek/deepseek-chat-v3-0324:free
```

This example command would output the results under `downloads\OpenRouter\deepseek-chat-v3-0324_free_test`, including `.json` and `.zip` files for each test sample. The testing can sometimes be aborted due to connection issues, so you are recommanded to use `src\automatic_bolt_diy\loop.bat` by replacing the command inside the loop to achieve automatic restarting.

#### Evaluating Generated Websites with an UI Agent

You can deploy Qwen2.5-VL-32B-Instruct on a server with four GPUs using `src-remote/deploy/deploy_qwenvl_32b.sh`. After installation following commands in `src-remote/deploy/install.sh`.

Then we use the WebVoyager UI agent to perform test case operations and assess the outcome. Assuming you have installed the `env\webvoyager` conda environment previously, you can run `src\ui_test_bolt\run_ui_eval_with_answer.bat`, for example:

```batch
src\ui_test_bolt\run_ui_eval_with_answer.bat downloads\OpenRouter\deepseek-chat-v3-0324_free_test
```

This example command would output the UI agent testing results under `downloads\OpenRouter\deepseek-chat-v3-0324_free_test\extracted\results`.

#### Computing the Accuracy

Then you can compute the accuracy as well as other statistics such as yes rate, partial rate, and no rate using `src\ui_test_bolt\compute_acc.py`. For example:

```shell
python src\ui_test_bolt\compute_acc.py downloads\OpenRouter\deepseek-chat-v3-0324_free_test
```

This example would print the results in terminal, as well as record the results in `downloads\OpenRouter\deepseek-chat-v3-0324_free_test\extracted\table.md`.

#### Evaluating Appearance Score

Generate the appearance score of the websites using:

```shell
python src\grade_appearance_bolt_diy\eval_appearance.py downloads\OpenRouter\deepseek-chat-v3-0324_free_test -t data\test.jsonl
```

This would generate the screeshot and `result.json` file under `downloads\OpenRouter\deepseek-chat-v3-0324_free_test\extracted\000007\shots`. Then compute average appearance score using:

```shell
python src\grade_appearance_bolt_diy\compute_grade.py src\grade_appearance_bolt_diy\eval_appearance.py downloads\OpenRouter\deepseek-chat-v3-0324_free_test
```

### Testing OpenHands

You can test OpenHands using our forked repo [OpenHands-WebGen-Fork](https://github.com/mnluzimu/OpenHands-WebGen-Fork). You should configure it based on [OpenHands README](https://github.com/mnluzimu/OpenHands-WebGen-Fork/blob/main/README.md), then run:

```shell
docker pull docker.all-hands.dev/all-hands-ai/runtime:0.25-nikolaik
cd OpenHands-WebGen-Fork
python src/test_webgen-bench/test_webgen_bench.py
```

### Testing Aider

You can test Aider using our forked repo [Aider-WebGen-Fork](https://github.com/YunqiaoYang/Aider-WebGen-Fork). You should configure it based on [Aider README](https://github.com/YunqiaoYang/Aider-WebGen-Fork/blob/main/README.md), then run:

```shell
cd .\working_dirs
python ..\src\batch_generate.py
```

## Training WebGen-LM

### Data Deduplication and Decontamination

This part is *not necessary for reproducing training*. It is our data deduplication and decontamination process, which was conducted to ensure that the training set is not contaminated by the test set. We place the files for deduplication and decontamination under `src-remote\process_train\deduplicate`.

```shell
pip install sentence-transformers scikit-learn editdistance
python src-remote/process_train/deduplicate/rule_deduplication.py
python src-remote/process_train/deduplicate/decontamination_ngram.py
python src-remote/process_train/deduplicate/test_decontamination_semantic.py --test_file data/test.jsonl --train_file data/train_processed/train_decontaminated_ngram5.jsonl --sim_threshold 0.55 --output_file data/train_processed/train_decontaminated_ngram5_semantic.jsonl --contaminated_file data/train_processed/train_contaminated_ngram5_semantic.jsonl
```

### Generating Training Data

(If you do not need to generate your own data, you can *skip this section* and directly use the data under `data/train_data`.)

#### Data Generation

First, generate training data using:

```batch
python src/automatic_bolt_diy/eval_bolt_diy.py ^
    --jsonl_path data/train.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenRouter ^
    --desired_model deepseek/deepseek-chat-v3-0324:free
```

Remember to replace `http://localhost:5173/` with the actual url of your bolt.diy service. This will output data under `downloads\OpenRouter\deepseek-chat-v3-0324_free_train`.

#### Data Filtering

Then, filter the data by generating the appearance score of each website using:

```shell
python src\grade_appearance_bolt_diy\eval_appearance.py downloads\OpenRouter\deepseek-chat-v3-0324_free_train -t data\train.jsonl
```

This would generate the screeshot and `result.json` file under `downloads\OpenRouter\deepseek-chat-v3-0324_free_train\extracted\000007\shots`. Then extract the filtered files using:

```shell
python src\grade_appearance_bolt_diy\filter_based_on_result.py downloads\OpenRouter\deepseek-chat-v3-0324_free_train
```

This would copy the filtered files under `downloads\OpenRouter\deepseek-chat-v3-0324_free_train\deepseek-chat-v3-0324_free_train_filtered`.

#### Converting to Training File Format

(We uplated the `downloads\OpenRouter\deepseek-chat-v3-0324_free_train\deepseek-chat-v3-0324_free_train_filtered` to a Linux server and executed the following files there.)

Convert the filtered files into the training format by running:

```shell
python src-remote/process_train/process_for_train/get_train.py 
```

### Finetuning

#### Installation

Create a conda environment:

```shell
conda create -p env/trainenv python=3.10
conda activate env/trainenv
```

First, install pytorch from [Pytorch Official Website](https://pytorch.org/) based on your cuda version. Then install other dependencies:

```shell
pip install -r requirements.txt
```

#### Training

The training scripts are under `src-remote/train`. You likely need to modify the files based on your own cluster before running:

```shell
bash src-remote/train/train_WebGen-LM-7B.sh
bash src-remote/train/train_WebGen-LM-14B.sh
bash src-remote/train/train_WebGen-LM-32B.sh
bash src-remote/train/train_Qwen2_5-Coder-32B-Instruct_ablation_150samples.sh
bash src-remote/train/train_Qwen2_5-Coder-32B-Instruct_ablation_300samples.sh
```

### Evaluation

This is the same as [Testing Bolt.diy](#test-bolt). The only difference is that you should host the trained model yourself using vllm. As in `src-remote/deploy/deploy_coder.sh`:

```shell
vllm serve models/Qwen2_5-Coder-32B-Instruct_app-bench_train_batch13_filtered_decontaminated_new \
    --dtype auto \
    --host 0.0.0.0 \
    --port 8000 \
    --pipeline-parallel-size 1 \
    --tensor-parallel-size 4 \
    --cpu-offload-gb 0 \
```

You should also configure the `.env.local` file in `bolt.diy-Fork` by setting the values of `OPENAI_LIKE_API_BASE_URL` to `http://IP_ADDRESS:PORT/v1`. Then you can start inference by running:

```shell
python src\automatic_bolt_diy\eval_bolt_diy.py ^
    --jsonl_path data\test.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenAILike ^
    --desired_model Qwen2_5-Coder-32B-Instruct_app-bench_train_batch13_filtered_decontaminated_new
```

Everything after is similar to [Testing Bolt.diy](#test-bolt).

## Citation

If you find our project useful, please cite:

```
@misc{lu2026fullstackagentenhancingagenticfullstack,
      title={FullStack-Agent: Enhancing Agentic Full-Stack Web Coding via Development-Oriented Testing and Repository Back-Translation}, 
      author={Zimu Lu and Houxing Ren and Yunqiao Yang and Ke Wang and Zhuofan Zong and Mingjie Zhan and Hongsheng Li},
      year={2026},
      eprint={2602.03798},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2602.03798}, 
}
@misc{lu2025webgenagentenhancinginteractivewebsite,
      title={WebGen-Agent: Enhancing Interactive Website Generation with Multi-Level Feedback and Step-Level Reinforcement Learning}, 
      author={Zimu Lu and Houxing Ren and Yunqiao Yang and Ke Wang and Zhuofan Zong and Junting Pan and Mingjie Zhan and Hongsheng Li},
      year={2025},
      eprint={2509.22644},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2509.22644}, 
}

@misc{lu2025webgenbenchevaluatingllmsgenerating,
      title={WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch}, 
      author={Zimu Lu and Yunqiao Yang and Houxing Ren and Haotian Hou and Han Xiao and Ke Wang and Weikang Shi and Aojun Zhou and Mingjie Zhan and Hongsheng Li},
      year={2025},
      eprint={2505.03733},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2505.03733}, 
}
```
