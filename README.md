# Helping Small Models Improve Across Website-Generation Tasks

[English](README.md) | [中文](README.zh-CN.md)

**Master of Artificial Intelligence thesis project, The University of Auckland · COMPSCI 792 Research Project**
Qiaopan Ma · Supervisor: Qian Liu · 2026

This repository forks [WebGen-Bench](https://arxiv.org/abs/2505.03733). It implements and evaluates **cross-task Long Memory** for a website-generation agent: after each task, the system reflects on evaluator evidence, stores reusable experience, and retrieves it for later tasks. It does not alter model weights or the benchmark's single-generation protocol.

> Chinese documentation is available throughout the repository. The operational Chinese records under [`docs/agent-memory/`](docs/agent-memory/) are canonical; their English companions are maintained as current-state reading guides.

- Thesis source: [`docs/thesis/`](docs/thesis/README.md)
- Presentation source: [`docs/reports/group_meeting_deck_2026-10/`](docs/reports/group_meeting_deck_2026-10/README.md)
- Documentation index: [`docs/README.md`](docs/README.md)
- Chinese project handoff: [`docs/agent-memory/HANDOFF.md`](docs/agent-memory/HANDOFF.md)
- English project handoff: [`docs/agent-memory/HANDOFF.en.md`](docs/agent-memory/HANDOFF.en.md)
- Phase-1 archive: [`archive/phase1-webgen-2026-10/`](archive/phase1-webgen-2026-10/)

## Abstract

Website-generation agents ordinarily start every request from scratch, so they repeat the same mistakes. We ask whether a 7B website generator can improve by learning only from its own earlier WebGen-Bench tasks.

We reproduced the official No Memory baseline on the University of Auckland H200 cluster: 28.5% functional accuracy on all 101 tasks, closely matching the paper's 28.4%. Our error analysis found that many zero-score sites were caused by a single basic code error that blanked the whole application. The small generator rarely followed textual advice, but it often copied short, concrete code fragments.

The final method, **v7**, combines a requirement checklist, a code-memory pool, and memory hygiene. On one 101-task run, it reaches 40.0% functional accuracy, versus 28.5% for No Memory and 30.9% for text-memory v4. The paired per-task v7 minus No Memory difference is +11.5 percentage points (bootstrap 95% CI [6.0, 16.9]). The benefit is functional rather than visual: for the 68 tasks with usable sites in both arms, appearance scores are 3.22 for v7 and 3.25 for No Memory.

**Main finding:** for this small model, the form of memory matters more than the amount of memory. Verified code fragments transfer; textual reminders alone do not.

## Research questions

1. Can an agent improve functional accuracy through experience produced by its own earlier tasks under the official WebGen-Bench protocol?
2. Which memory representation can a small generator use: textual lessons, requirement checklists, or code fragments?
3. Does the benefit persist as experience accumulates and under changes in task order?

## Experimental setup

| Role | Model / environment |
|---|---|
| Generator | WebGen-LM-7B (BF16, vLLM), Bolt.diy; one generation and no repair |
| Functional evaluation | Qwen2.5-VL-32B-Instruct WebVoyager-style GUI agent |
| Appearance evaluation | Qwen2.5-VL-32B-Instruct, score 1–5 |
| Memory and reflection | Qwen2.5-VL-72B-Instruct-AWQ + bge-m3 |
| Hardware | University of Auckland CS ML cluster, 2×H200 per job |

The benchmark has 101 tasks from 20 domains. Accuracy is `(passed + 0.5 × partial) / checks`, reported together with appearance and the number of zero-score tasks. Statistical comparisons are paired by task, never by treating the 647 checks as independent samples.

## Method

For every task, v7:

1. rewrites the original request into a requirement checklist while keeping the original request binding;
2. retrieves only relevant historical implementation experience;
3. injects at most two verified code fragments from the same run's earlier successful sites;
4. generates and evaluates the site once under the official protocol;
5. reflects on evaluator evidence and updates the memory bank for later tasks only.

The code pool is populated only after a failure pattern has occurred in at least two earlier tasks. Candidate snippets must come from a score-at-least-0.5, compilable site, must match the source exactly, be no longer than 15 lines, and include both an import and a real use of that API. Whole files and import-only examples made the 7B model return the Vite scaffold, so v7 injects fragments only.

## Results

| Scope | No Memory | v4 text memory | **v7 code memory** |
|---|---:|---:|---:|
| Tasks 1–30 | 26.0% / 3.26 / 11 | 39.3% / 3.29 / 1 | **39.0% / 3.38 / 4** |
| Tasks 31–60 | 36.3% / 3.16 / 6 | 35.0% / 3.20 / 5 | **45.3% / 3.07 / 3** |
| Tasks 61–101 | 24.8% / 3.31 / 13 | 22.9% / 3.14 / 14 | **37.1% / 3.20 / 6** |
| **All 101 tasks** | **28.5% / 3.25 / 30** | 30.9% / 3.21 / 20 | **40.0% / 3.21 / 13** |

Each cell reports functional accuracy / appearance / zero-score tasks. The learning and gap curves are in [`docs/reports/learning_curve_v4_v7.png`](docs/reports/learning_curve_v4_v7.png) and [`docs/reports/gap_curve_v4_v7.png`](docs/reports/gap_curve_v4_v7.png).

The checklist-only ablation is complete: No Memory / checklist-only / v7 achieve 28.5% / 31.8% / 40.0%. Checklist-only has a paired +3.4pp versus No Memory (CI includes zero), while v7 has +8.1pp versus checklist-only. Thus, the checklist helps, but the larger gain comes from memory.

## Current limitations and experiments

- The main v7 result is one run in the original domain-block order.
- The ongoing order-robustness experiment runs Long Memory and No Memory task-by-task in ABBA order under shuffled schedules.
- The generator and framework are currently fixed to WebGen-LM-7B and Bolt.diy.
- A fixed-prefix ablation separates accumulated memory from a code prefix present from task one.
- A stronger generator comparison is planned with WebGen-LM-32B under the same Bolt, memory, and evaluation pipeline.
- The method may overfit WebGen-Bench because it was iterated on this benchmark.

## Repository map

| Location | Purpose |
|---|---|
| `scripts/run_continual_memory.py` | Shared runner for No Memory and continual memory |
| `src/reflection_case_memory.py` | Checklists, retrieval, rewriting, deduplication, and utility |
| `src/code_memory.py` | Code facts and verified code-memory pool |
| `src/post_task_reflection.py` | Evidence-grounded post-task reflection |
| `src/long_memory.py` | SQLite memory schema and storage |
| `config/long_memory_cluster_v7.json` | Frozen v7 configuration |
| `scripts/cluster/` | Slurm worker, queue, health checks, and output sync |
| `docs/agent-memory/` | Canonical operational context, decisions, and handoff |

Generated websites, screenshots, evaluator trajectories, and memory databases are intentionally excluded from Git.

## Citation

This project builds on:

```bibtex
@article{lu2025webgenbench,
  title={WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch},
  author={Lu, Zimu and others},
  year={2025},
  eprint={2505.03733},
  archivePrefix={arXiv}
}
```

For the full Chinese project description and Chinese reference list, see [README.zh-CN.md](README.zh-CN.md).
