# 第二阶段实验数据（学校 H200 集群，2026-10）

论文所用运行的关键文件，由 `scripts/archive_phase2_runs.py <运行名>` 从 `outputs/experiment/` 复制。生成的网站、截图和评测轨迹体积大，不进 git，保存在本地 `outputs/experiment/`（集群上的副本可能已清理）。

| 目录 | 论文中的用途 | 设置 |
|---|---|---|
| `cluster_nomem_webgenlm7b_r1` | No Memory，原顺序（主结果） | 101 题 |
| `cluster_longmem_v4_webgenlm7b_r1` | v4：清单 + 文字记忆 | 原顺序，101 题 |
| `cluster_longmem_v7_webgenlm7b_r1` | v7（论文 WF：整份文件代码记忆），原顺序 | 101 题 |
| `cluster_checklist_only_v7_webgenlm7b_r1` | 消融：只有清单 | 原顺序，101 题 |
| `cluster_manifest_longmem_v9_1_webgenlm7b` | v9.1（论文 F：最终方法），原顺序 | 101 题 |
| `cluster_order_blocks11_{nomem,longmem_v7,longmem_v9_1}` | 种子 11（领域挨着） | 各 101 题；No Memory 与 v7 成对 ABBA |
| `cluster_order_random29_{nomem,longmem_v7,longmem_v9_1}` | 种子 29（完全随机） | 各 101 题 |
| `cluster_order_blocks47_longmem_v9_1` | 种子 47，只跑 Long Memory | 101 题 |
| `cluster_order_interleave_longmem_v9_1` | 交错，只跑 Long Memory | 101 题 |
| `cluster_order_blocks11_longmem_v8`、`_v9` | v8、v9 中间版本（已停） | 61、46 题 |
| `cluster_order_blocks47_longmem_v7`、`cluster_order_blocks47_nomem`、`cluster_order_interleave_nomem` | **中途停止，论文不使用**（v7 关闭、No Memory 不再补跑） | 29、92、14 题 |

待加入：原顺序 v9.1 重复跑 `cluster_manifest_longmem_v9_1_webgenlm7b_r2`、固定前缀 `cluster_fixed_prefix_v9_1_webgenlm7b`（约 10-18）。

每个目录：
- `progress.jsonl`：每题一行，含评测结果（准确率按"通过 + 0.5×部分通过"/检查数计，`scored` 那条是外观分）。
- `continual-report.json`、`run-metadata.json`：汇总与运行配置（模型、协议、配置文件指纹）。
- `memory.db`：SQLite 记忆库（反思 case、经验、代码池 `code_memories` 及其使用记录）。No Memory 为空库。
- `memory-events.jsonl.gz`、`post-task-reflections.jsonl.gz`：每题的检索、注入和反思全过程。
- `prompts/<任务号>.txt`：每题发给生成器的完整 prompt。
- `task-order.json`（顺序实验）：执行顺序。
