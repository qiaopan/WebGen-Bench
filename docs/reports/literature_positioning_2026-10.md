# 文献检索与定位（2026-10-08）

目的：投稿前确认"小模型 + 网站生成 + 跨任务记忆，代码形式有效、文字无效"这一定位是否站得住。检索用网页搜索；第 1 节和第 3 节的 Metis、Super Library Agent、Memory Transfer Learning、Evo-Memory、AgentCL 已对照全文核对（10-08）；第 2 节标"未核对"的条目只看过摘要或二手概述。

## 1. 最接近、必须引用并说明区别的工作

| 工作 | 做了什么 | 与我们的区别 |
|---|---|---|
| **Metis**（Dai et al., 2026，arXiv 2606.24151，全文已核对） | 文字记忆打底，反复出现的计划才固化为**可调用的工具**（智能体执行它们），经编译/依赖检查；AppWorld。受控研究（训练集 90 题，执行 GPT-4o、反思 Claude Sonnet 4.6，指标 TGC）：样本内 Oracle 设置 No Memory 63.3、代码 75.6、文字 78.9；**流式设置（只用更早任务建的记忆）代码 53.3、文字 73.3**，作者解释代码"高效但在任务变化下脆弱"、单条轨迹提炼的工具会过拟合并把缺陷传给所有调用者。dev 集消融：No Memory 56.1、只文字 62.3、只代码 60.2、完整 66.7 | 强模型上**文字迁移更稳、代码更脆**；我们在 7B 上相反：文字几乎不被执行，代码片段有效。**注意机制不同**：Metis 的代码是被执行的工具，我们的代码是放进 prompt、让生成器模仿的片段（不被执行）。论文里要写成"不同形式的代码记忆"，不能说成同一件事的相反结果 |
| **Super Library Agent**（Sung et al., 2026，arXiv 2608.29310，Findings of EMNLP 2026，全文已核对） | **同样用 WebGen-Bench**：从 101 题聚成 14 个主题组，取 3 组各 8 题（24 题），每组作为一个顺序任务流，维护共享代码库；主模型 deepseek-v4-flash；准确率 76.04 → 77.21、外观 3.84 → 3.86，配对检验差异不显著（p=0.484），作者明确说没有功能指标显著不同；收益在可维护性（代码量 −9%、token −6.7% 等）；每组 3 次独立运行（均值 ± 标准差）；作者自己指出每组来自同一主题组，是"对共享库有利的设置" | 目标是**功能不下降的前提下提高可维护性**，没有失败经验的记忆，准确率没有显著提升；强模型、24 题、同主题组内、不研究顺序。我们：7B、全部 101 题、官方协议、从失败中学习、准确率配对 +11.5（CI 6.0–16.9），并把领域挨着/打散作为变量——正好回应它"同主题组有利"的说明 |
| **Memory Transfer Learning**（Kim et al., 2026，arXiv 2604.14004，全文已核对） | 编码智能体跨领域记忆；四种表示从具体到抽象：Trajectory（命令与代码及其执行结果）、Workflow、Summary、Insight（不含具体文件的通用经验）；模型 GPT-5-mini、DeepSeek V3.2、Qwen3-Coder-480B-A35B；6 个编码基准；GPT-5-mini Pass@3 平均：零样本 0.523 → Insight 0.560（最好）；Trajectory 在 Terminal-Bench 2、MLGym 上低于零样本（负迁移）；**没有测试小模型** | 强模型上最抽象的 insight 最好、最具体的轨迹会负迁移；我们在 7B 上看到空泛文字经验有害、经过核对的具体代码片段有效。可作为"模型能力不同，适合的抽象层次不同"的佐证；注意我们的代码片段不是原始轨迹，而是挑选、核对过的几行 |
| **WebGen-Agent**（Lu et al., 2025，arXiv 2509.22644） | 同一题内用截图和 GUI 反馈反复修复（Claude-3.5-Sonnet 26.4% → 51.9%） | 同题修复，用的是评测反馈；我们只跨题、不修复、不用当前题的评测结果 |

## 2. 记忆与持续学习的一般工作（背景、方法来源）

- 经验/洞察记忆：ExpeL（Zhao et al., 2024）、ReasoningBank（2025）、Memento（Zhou et al., 2025）、Mem0（Chhikara et al., 2025）。
- 技能/代码记忆：Voyager（Wang et al., 2023）、Agent Workflow Memory（Wang et al., 2025）、CODESKILL（2026，技能库，SWE-bench 等，未核对全文）、"User as Code"（2026，可执行记忆，个性化场景）。
- 编码智能体自我演化：综述 *Self-Evolving Coding Agents*（arXiv 2608.03392）；SWE-Exp、MemCoder 等（数字来自二手概述，未核对）。
- 小模型记忆：LightMem（arXiv 2604.07798）面向小模型，但是文字记忆、问答任务。

## 3. 任务顺序

- **Evo-Memory**（Wei et al., 2025，arXiv 2511.20857，已核对）：第 4.2.3 节比较易→难与难→易两种序列，称基线在不同序列间差异很大，并强调"任务序列设计对公平评估的重要性"。
- **AgentCL**（Shu et al., 2026，arXiv 2606.02461，已核对）：同领域但复用关系未知的"常规流"与先放子任务再放复杂任务的"依赖流"；依赖流下各记忆方法区分得更清楚，"没有暴露复用机会的任务流，就无法公平诊断记忆表示"。
- **When Continual Learning Moves to Memory**（arXiv 2604.27003）：A→B 协议，前向迁移与遗忘的权衡。
- **MoRAM**（arXiv 2506.21035，非智能体）：用多种任务顺序的最终准确率标准差衡量顺序敏感度。
- 未找到在**网站生成**上把任务顺序作为变量、并与 No Memory 逐题配对的工作。

## 4. 结论：定位是否站得住

**站得住，但要换一种说法。**

- 不能说"没人做过代码记忆"（Metis、Voyager 等）或"没人在 WebGen-Bench 上做跨任务复用"（Super Library Agent）。
- 能说、且有文献支撑的新意：
  1. **记忆形式与模型能力的交互**：强模型（Metis，GPT-4o）上文字记忆迁移更稳、代码更脆；高层 insight 迁移最好（Memory Transfer Learning）。我们在 7B 生成器上观察到相反的情况：文字经验几乎不被执行、空泛条目随时间变得有害，经过核对的代码片段才有效，而且片段的形式（不能是整份文件）决定成败。
  2. **在官方 WebGen-Bench 协议、全部 101 题、7B 开源模型上**，从失败中学习的跨任务记忆把准确率从 28.5% 提到 40.0%（配对 +11.5，CI 6.0–16.9）；Super Library Agent 用强模型、24 题的同主题任务流，目标是可维护性，准确率差异不显著。
  3. **把任务顺序作为实验变量**（领域挨着 vs 打散、两组逐题 ABBA 配对），这在网站生成记忆中没有找到先例；持续学习文献（Evo-Memory、AgentCL）支持顺序会影响结论。
- 建议标题方向：强调"形式取决于能力"，例如 *What Memory Can a Small Model Use? Code over Text for Cross-Task Website Generation*。

## 5. 对论文的影响（10-08 已同步到论文与 PPT）

- 第 2 章相关工作：加 Super Library Agent、Memory Transfer Learning、Evo-Memory/AgentCL；重写与 Metis 的对比（Metis 的流式迁移结果与我们相反）。
- 第 6 章讨论：加"记忆形式 × 模型能力"一段；用更强的 WebGen-LM-32B 做对比的意义因此更大（未来工作；14B 与 7B 在该基准上几乎一样强，不选）。
- 参考文献：补上述条目，并核对全文。

## 来源

- [Metis（arXiv 2606.24151）](https://arxiv.org/abs/2606.24151)，[HTML](https://arxiv.org/html/2606.24151)
- [Super Library Agent（arXiv 2608.29310）](https://arxiv.org/abs/2608.29310)，[HTML](https://arxiv.org/html/2608.29310)
- [Memory Transfer Learning（arXiv 2604.14004）](https://arxiv.org/abs/2604.14004)
- [WebGen-Agent（arXiv 2509.22644）](https://arxiv.org/pdf/2509.22644)
- [WebGen-Bench（arXiv 2505.03733）](https://arxiv.org/pdf/2505.03733)
- [Self-Evolving Coding Agents（arXiv 2608.03392）](https://arxiv.org/pdf/2608.03392)
- [CODESKILL（arXiv 2605.25430）](https://arxiv.org/html/2605.25430v2)
- [User as Code（arXiv 2606.16707）](https://arxiv.org/html/2606.16707v1)
- [Lightweight LLM Agent Memory with Small Language Models（arXiv 2604.07798）](https://arxiv.org/html/2604.07798v3)
- [Evo-Memory（arXiv 2511.20857）](https://arxiv.org/pdf/2511.20857)
- [AgentCL（arXiv 2606.02461）](https://arxiv.org/html/2606.02461)
- [When Continual Learning Moves to Memory（arXiv 2604.27003）](https://arxiv.org/abs/2604.27003)
- [MoRAM / Little by Little（arXiv 2506.21035）](https://arxiv.org/pdf/2506.21035)
- [Training with Pseudo-Code for Instruction Following（arXiv 2505.18011）](https://arxiv.org/html/2505.18011)
