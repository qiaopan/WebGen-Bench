# 第二阶段实验数据（学校 H200 集群，2026-10）

论文所用运行的关键文件，由 `scripts/archive_phase2_runs.py <运行名>` 从 `outputs/experiment/` 复制。生成的网站、截图和评测轨迹体积大，不进 git，保存在本地 `outputs/experiment/`（集群上的副本可能已清理）。

| 目录 | 论文中的实验 | 设置 |
|---|---|---|
| `cluster_nomem_webgenlm7b_r1` | No Memory 基线（主结果） | WebGen-LM-7B，manifest 顺序，101 题 |
| `cluster_longmem_v4_webgenlm7b_r1` | v4：需求清单 + 文字记忆 | `config/long_memory_cluster_v4.json` |
| `cluster_longmem_v7_webgenlm7b_r1` | v7：最终方法（清单 + 代码池 + 记忆卫生） | `config/long_memory_cluster_v7.json` |

待加入（跑完后用同一脚本）：只有清单消融 `cluster_checklist_only_v7_webgenlm7b_r1`、顺序实验 `cluster_order_*`、固定前缀 `cluster_fixed_prefix_v7_webgenlm7b_r1`、32B `cluster_manifest_*_webgenlm32b_fp8`。

每个目录：
- `progress.jsonl`：每题一行，含评测结果（准确率按"通过 + 0.5×部分通过"/检查数计，`scored` 那条是外观分）。
- `continual-report.json`、`run-metadata.json`：汇总与运行配置（模型、协议、配置文件指纹）。
- `memory.db`：SQLite 记忆库（反思 case、经验、代码池 `code_memories` 及其使用记录）。No Memory 为空库。
- `memory-events.jsonl.gz`、`post-task-reflections.jsonl.gz`：每题的检索、注入和反思全过程。
- `prompts/<任务号>.txt`：每题发给生成器的完整 prompt。
- `task-order.json`（顺序实验）：执行顺序。
