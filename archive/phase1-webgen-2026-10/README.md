# 第一阶段归档快照（2026-10-03）

完整输出（约 20 GB）在本机 `outputs/experiment/`，不进 git。这里只保留以后写论文或复核需要的关键文件。说明见仓库根目录 `README.md` 和 `docs/agent-memory/`。

| 路径 | 来源 | 内容 |
|---|---|---|
| `no_memory/` | `outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2` | `progress.jsonl`（每个任务的评测结果）、`run-metadata.json`（模型角色、配置指纹）、`continual-report.json`、`prompts/`（实际提交的 prompt） |
| `long_memory/` | `outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1` | 同上，另有 `memory.db`（全部 trajectory、case 和统计，含已归档的旧版本）、`post-task-reflections.jsonl`、`memory-events.jsonl`（检索、改写、压缩的完整记录） |
| `reflection_regression/<prompt版本>-<时间>/` | `outputs/experiment/reflection_regression` | 每个反思 prompt 版本在回归集上的反思原文和 `summary.json` |
| `prompt_length_analysis.csv` | `scripts/backfill_prompt_stats.py` | 每个 trajectory 的需求字数、注入记忆字数、倍数、条数和准确率 |

注意：

- Long Memory 的 `progress.jsonl` 中各任务来自不同的协议版本（见根目录 README 第 4 节）。
- No Memory 026 的修复超时问题已修复后重跑，最终记为构建失败；更早的运行已备份在本机任务目录中。
