# 让小模型越做越好：面向网站生成的跨任务长期记忆

**奥克兰大学（The University of Auckland）人工智能硕士（Master of Artificial Intelligence）毕业论文项目 · COMPSCI 792 Research Project**

作者：Qiaopan Ma · 导师：Qian Liu · 2026

> 本仓库是 [WebGen-Bench](https://arxiv.org/abs/2505.03733) 的 fork。我们在它上面实现并评估了网站生成 agent 的**跨任务长期记忆（Long Memory）**：做完一题就把评测结果反思成经验，下一题检索、注入 prompt，不改模型权重，也不改官方评测协议。原 WebGen-Bench README 保留在本文末尾。
>
> - 论文 LaTeX 源文件：[`docs/thesis/`](docs/thesis/README.md)
> - 组会 PPT 源文件（含演讲稿）：[`docs/reports/group_meeting_deck_2026-10/`](docs/reports/group_meeting_deck_2026-10/README.md)
> - 决策与交接记录：[`docs/agent-memory/DECISIONS.md`](docs/agent-memory/DECISIONS.md)、[`docs/agent-memory/HANDOFF.md`](docs/agent-memory/HANDOFF.md)
> - 第一阶段（2026-09）结果快照：[`archive/phase1-webgen-2026-10/`](archive/phase1-webgen-2026-10/)
> - 配套的 Bolt 改动：`bolt.diy-Fork` 子模块（分支 `diy-fork`）

## 摘要

网站生成 agent 每个任务都从零开始，同样的错误会在下一题重复出现。我们研究：**在官方评测协议下，一个 7B 的网站生成模型（WebGen-LM-7B）能否靠自己以前做过的任务积累经验，越做越好？**

我们先在学校 H200 集群上全部自部署，复现了官方 No Memory 基线（101 题准确率 28.5%，论文 28.4%）。分析它的失败发现：大量零分题不是难题，而是一处基础代码错误导致的整站白屏（例如 import 了没安装的包）；并且小模型几乎不听文字建议，却会照抄代码。纯文字的记忆（v4）前 30 题有效，后期因为空泛条目越攒越多，反而输给 No Memory。

最终方法（v7）由三部分组成：**需求清单**保证需求里的每个功能都可见；**代码池**在某个问题出现 ≥2 次后，从本链自己做对的网站里摘出经过核对的代码片段注入；**记忆卫生**（存储前去重、只留具体写法、按效用退役）防止空话累积。单次运行、101 题上：

| | No Memory | v4（文字记忆） | **v7（代码记忆）** |
|---|---|---|---|
| 准确率 | 28.5% | 30.9% | **40.0%** |
| 零分题 | 30 | 20 | **13** |
| 第 31–101 题准确率 | 29.5% | 27.8% | **40.4%** |

v7 相对 No Memory 逐题配对平均 +11.5 个百分点（95% bootstrap CI 6.0–16.9）。提升在功能而不在外观：两组都生成出可用网站的 68 题上，外观分 3.25 vs 3.22。

核心结论：**对小模型来说，记忆的形式比记忆的多少更重要**——经过核对的代码片段能迁移，文字经验不能。

## 1. 研究问题

1. **RQ1**：只用 agent 自己先前任务产生的经验，能否在官方 WebGen-Bench 协议下提升小模型的功能准确率？
2. **RQ2**：小模型真正用得上哪种形式的记忆：文字经验、需求清单，还是代码示例？
3. **RQ3**：收益是否随经验积累而保持或增长？是否对任务顺序稳健？

## 2. 实验设置

| 角色 | 模型 / 环境 |
|---|---|
| 生成器 | WebGen-LM-7B（BF16，vLLM），Bolt.diy，**只生成一次、不修复**（官方协议） |
| 功能评测 | Qwen2.5-VL-32B-Instruct，WebVoyager 式 GUI agent 逐项点击测试 |
| 外观评测 | Qwen2.5-VL-32B-Instruct（论文用 GPT-4o，这是唯一偏差；外观只在我们的组之间比较） |
| 记忆 / 反思 | Qwen2.5-VL-72B-Instruct-AWQ + bge-m3 embedding |
| 硬件 | 奥克兰大学 CS ML 集群，每个作业 2×H200，单个任务约 12 分钟；不调用任何商业 API |

- **任务：** WebGen-Bench 全部 101 个任务，按 manifest 的 20 个领域分块顺序执行。
- **指标：** 准确率 =（通过 + 0.5×部分通过）/ 检查数（官方口径）；外观 1–5 分；零分题数。比较按任务配对，不把检查当作独立样本。
- **对照组：** No Memory = 同一模型、同一评测，只给需求原文，不检索、不反思、不写记忆。
- **防泄漏：** 留一任务（leave-one-task-out）——检索永远排除当前任务自己的记录；评测结果不回流修复同一题。

## 3. 方法

### 3.1 出发点：No Memory 为什么失败

- **整站白屏来自基础错误。** Bolt 的 Vue 模板只声明了 `vue` 一个依赖，而生成器的回复从不修改 `package.json`（0/81）。一旦 import 了 `vue-router`，整站白屏、所有检查失败。
- **小模型不听文字，听代码。** 在原本白屏的任务上只加一句文字建议（正说、反说、放首尾都试过），最多救回 1/3；给一段 10 行左右的页面切换代码示例，救回 7/9。让模型先写规划（short CoT）则 5/5 丢掉了 Bolt 的文件格式。

### 3.2 流水线（每个任务）

1. **需求清单**：记忆模型把需求逐条拆开。
2. **检索经验**：功能经验按相似度取候选，由记忆模型判断是否适用，只保留 hard match，挂到对应的清单条目下；通用池只保留含具体写法的条目。
3. **代码池**：最多 2 段经过核对的代码片段（见 3.4）。
4. **生成 + 评测**：WebGen-LM-7B 生成一次，官方功能与外观评测。
5. **反思入库**：记忆模型按排查步骤反思每项未通过的检查；新经验去重、更新效用、用代码重新计算网站事实并更新代码池。

第 5 步的产物会被下一题的第 2、3 步读取，这是任务之间唯一的信息通道。

### 3.3 需求清单（`build_checklist`，`src/reflection_case_memory.py`）

需求原文放在 prompt 最前并声明优先；下面逐条列出清单，经验原文挂在对应条目下，而不是单独列一个"注意事项"——单独的列表会被小模型当成要做的全部范围。代码检查每个条目都和需求有共同实词（防止从别的任务带入需求里没有的功能），覆盖率低于 60% 就带着缺失的词重拆。

### 3.4 代码池（`src/code_memory.py`）

- **用代码而不是模型检测问题：** 每个任务结束后，对生成的网站计算未声明的包（`import:<pkg>`）、用了 Vue 函数却没 import（`vue-api`）、以及用 `@vue/compiler-sfc` 按 Vite 的方式编译得到的错误（`compile:*`）。
- **反复出现才固化：** 同一问题在 ≥2 个任务出现后才建立代码记忆（参考 Metis）。
- **写法来自自己做对的网站：** 从本链得分 ≥0.5、能编译、没有上述问题的网站里摘代码；失败的网站决定"什么时候需要"，成功的网站提供"怎么写"。
- **只给片段，不给整份文件：** 记忆模型挑关键行，代码核对——逐字来自源文件、≤15 行、不含 `<script>/<template>` 标签行、必须包含 import 行和一行真实调用。整份文件或只有一行 import 的示例会被小模型当成"已经写完"，直接交回模板（v6 的教训）。
- **按条件取用：** 每条代码记忆带名称和适用条件，由记忆模型按当前需求判断是否注入，像技能库一样（参考 Voyager）。

### 3.5 记忆卫生

- **只留具体写法：** 通用池条目没有代码写法（`@click`、`v-if`、`import`…）就丢掉；改写时只泛化"什么时候用"，不泛化"怎么做"。
- **存储前去重：** 新经验与相似的旧经验比较，同一根因、同一修法就记为对旧经验的支持，不新增（参考 Mem0）。
- **效用与退役：** 效用 =（注入次数 − 复现次数 + 1）/（注入次数 + 2）；注入 ≥5 次且效用 <0.3 的经验停止注入（参考 Memento、ExpeL）。
- **结论不手写：** 给反思模型的规则只教排查方法（沿代码链检查、从元素追到全局样式表、列出候选原因逐一排除），具体经验必须由系统从证据中产出。

### 3.6 版本演进

| 版本 | 改动 | 暴露的问题 |
|---|---|---|
| 第一阶段（Mac 本地，2026-09） | 三层记忆、分步反思、guidance 压缩 | prompt 换行 bug 使经验从未送达；压缩会删掉需求功能 |
| v3 | 源头去重、效用排序 | 文字经验仍救不回白屏 |
| v4 | + 需求清单 | 前 30 题好，后 71 题输给 No Memory |
| v6 | + 代码池、具体化过滤、退役 | 一行 import 示例 → 模型交回模板 |
| **v7（最终）** | 示例只给片段、必须带调用行；统计块不注入 | 约 4.6% 的组件仍漏 Vue import（见 §5） |

## 4. 结果

| 范围（准确率 / 外观 / 零分题） | No Memory | v4 | v7 |
|---|---|---|---|
| 第 1–30 题 | 26.0% / 3.26 / 11 | 39.3% / 3.29 / 1 | 39.0% / 3.38 / 4 |
| 第 31–60 题 | 36.3% / 3.16 / 6 | 35.0% / 3.20 / 5 | **45.3%** / 3.07 / 3 |
| 第 61–101 题 | 24.8% / 3.31 / 13 | 22.9% / 3.14 / 14 | **37.1%** / 3.20 / 6 |
| **全部 101 题** | 28.5% / 3.25 / 30 | 30.9% / 3.21 / 20 | **40.0% / 3.21 / 13** |

- **学习曲线与 gap 图：** [`docs/reports/learning_curve_v4_v7.png`](docs/reports/learning_curve_v4_v7.png)、[`docs/reports/gap_curve_v4_v7.png`](docs/reports/gap_curve_v4_v7.png)。后段三组准确率都下降，是题目更难；看同一题上与 No Memory 的差，v4 在第 40–60 题最多落后约 27 个百分点，v7 在第 60 题以后稳定领先 10–25 个百分点。
- **提升从哪里来：** 整站白屏或编译错的题数，No Memory 26、v4 19、v7 8。v4 共注入 102 条无代码写法的条目，v7 只有 31 条。
- **零分题：** v7 的 13 个零分题中有 10 个 No Memory 也是 0 分，多为该生成器做不出的难题。

## 5. 主要发现

1. **形式决定小模型能否用上记忆。** 文字经验正确也不被执行；代码片段被执行。
2. **文字记忆会随时间变坏。** 空泛条目越攒越多，挤占 prompt，v4 后段低于 No Memory。
3. **示例必须是片段。** 整份文件或只有 import 的示例被当成已写完的答案，模型直接交回模板。
4. **整站白屏能被纠正，单页缺 import 不能。** 按文件统计，v7 有 27/592、No Memory 有 27/586 个组件漏 Vue import（约 4.6%），出现位置没有规律，更像随机笔误。我们试了让示例随数据更新、同时示范 `ref` 和 `computed`（v8，开关 `WEBGEN_CODE_POOL_REFRESH`，默认关闭），4 题只改善 1 题。官方协议不允许生成后修复，因此停在 v7，把它写为生成器的残余错误率。
5. **基础设施问题会伪装成模型能力问题**（第一阶段）：Bolt 把换行当发送导致经验从未送达；Node 默认 300 秒超时让修复回复静默丢失；评测浏览器的深色模式让 Vite 默认样式变成白底白字。

## 6. 局限与进行中的实验

**原论文（WebGen-Bench）的局限：** 主结果都是单次运行、没有误差线，作者在 NeurIPS 自查清单中说明原因是"计算成本太高"；它在 Limitations（附录 B）中写的是只覆盖 TypeScript/JavaScript/CSS/HTML，以及只用了监督微调。WebGen-Bench 也是静态基准，不定义任务之间的交互，所以任务顺序不是它的变量。我们在这两点上更进一步：No Memory 重复 5 次（第 1 遍 + 每个顺序一次）以量化运行噪声；Long Memory 在"领域挨着"和"领域打散"两类顺序下各重复 2 次，两组逐题配对、报告置信区间。但每个顺序内 Long Memory 仍是单次运行。


- **单次运行、固定顺序。** 正在进行：
  - **消融"只有清单"**（v7 配置 + 不读写任何记忆，同一顺序）：区分提升来自需求拆解还是记忆积累。
  - **顺序鲁棒性**：除已有的 manifest 原顺序外，再跑"领域挨着"（打乱领域块与块内顺序，种子 11、47）和"领域打散"（101 题完全随机，种子 29；跨领域交错）各 2 次，按 11 → 29 → 47 → 交错 的优先级排队，每次从空库开始；Long Memory 与 No Memory 逐题背靠背、按 ABBA 轮换谁先跑，报告配对差与 bootstrap 置信区间。顺序文件在 `data/experiment_splits/task_orders/`（`scripts/make_task_orders.py` 生成）。
- 只用一种生成器（WebGen-LM-7B）和一种框架（Bolt.diy + Vue）。
- 代码池的触发条件很通用，效果接近"学到的固定前缀"；需要"从第 1 题起给固定前缀"的消融区分。
- 记忆模型（72B）强于生成器（7B）；外观评测用 32B 代替 GPT-4o。
- 方法在 WebGen-Bench 上迭代设计，存在对该基准过拟合的可能；正式运行从空库开始、只用先前任务，以降低这一风险。

### 后续计划（交论文后）

补 3 个实验后考虑投稿：短期投 LLM agent、记忆或代码生成相关的 workshop，补完后考虑 ACL/EMNLP Findings。
1. **固定前缀消融：** 从第 1 题起给 v7 最终的代码片段，不读写记忆，区分"记忆积累"和"prompt 里有代码"。
2. **第二个生成模型：** WebGen-LM-14B，其余不变，检验"代码优于文字"是否只对 7B 成立。
3. **留出验证：** 前 30 题定版，后 71 题单独报告，回应"边看结果边改方法"的过拟合质疑。

更远的方向：换评测 VLM、换智能体（OpenHands/Aider）、迁移到 SWE-bench。

## 7. 代码地图与复现

| 位置 | 内容 |
|---|---|
| `scripts/run_continual_memory.py` | 两臂共用的 runner（`--modes disabled` / `continual`） |
| `src/reflection_case_memory.py` | 需求清单、检索、改写、压缩、去重与效用 |
| `src/code_memory.py` | 代码事实（未声明的包、缺 import、编译错误）与代码池 |
| `src/post_task_reflection.py` | 任务后分步反思 |
| `src/long_memory.py`、`src/long_memory_schema.sql` | SQLite 记忆库 schema |
| `config/long_memory_cluster_v7.json` | 最终版本 v7；`..._checklist_only_v7.json` 为消融；v3–v6 为历史版本 |
| `scripts/cluster/` | Slurm 作业（`worker.sbatch`、`run_queue.sbatch`）、服务启动、队列（`enqueue.sh`、`filler.conf`）、健康检查、拉取结果 |
| `scripts/plot_learning_curve.py`、`scripts/plot_gap_curve.py` | 学习曲线与 gap 图 |
| `scripts/preview_guidance.py` | 只跑检索与注入，预览 prompt（只读记忆库） |
| `docs/thesis/` | 论文 LaTeX（UoA 模板） |

集群用法见 [`docs/agent-memory/HANDOFF.md`](docs/agent-memory/HANDOFF.md)「WebGen 第二阶段」。完整输出（生成的网站、评测轨迹、截图、记忆库）不在 git 中。

## 参考文献

已核对出处：

- Lu et al., 2025. *WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch.* arXiv:2505.03733.
- Du et al., 2025. *Context Length Alone Hurts LLM Performance Despite Perfect Retrieval.* Findings of EMNLP 2025, arXiv:2510.05381.
- Liu et al., 2024. *Lost in the Middle: How Language Models Use Long Contexts.* TACL 12.
- Wallace et al., 2024. *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions.* arXiv:2404.13208.
- Shi et al., 2023. *Large Language Models Can Be Easily Distracted by Irrelevant Context.* ICML 2023.

待核对（写进论文前逐条确认）：

- 经验记忆：ExpeL（Zhao et al., 2024）、ReasoningBank（2025）、Mem0（Chhikara et al., 2025）、Memento（Zhou et al., 2025）、Generative Agents（Park et al., 2023）。
- 代码 / 技能记忆：Voyager（Wang et al., 2023）、Agent Workflow Memory（Wang et al., 2025）、Metis（Dai et al., 2026，arXiv:2606.24151）。
- 指令遵守：Curse of Instructions（Harada et al., 2025）、IFScale（Jaroslawicz et al., 2025）；小模型推理：Li et al., 2025。
- 排查与验证：Zeller, *Why Programs Fail*；Self-Debug（Chen et al., 2023）；Chain-of-Verification（Dhuliawala et al., 2023）；Self-Refine（Madaan et al., 2023）。

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
