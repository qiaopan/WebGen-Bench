# Project Context

[English](PROJECT_CONTEXT.en.md) | [中文完整记录](PROJECT_CONTEXT.md)

> This is an English current-state guide. The complete operational record is maintained in [Chinese](PROJECT_CONTEXT.md).

## Goal

This project studies whether a website-generation agent can improve across tasks through Long Memory. The formal comparison is **No Memory versus Long Memory** under the WebGen-Bench generation and evaluation protocol. Memory may use only earlier tasks; it must never use final evaluation feedback to repair the same benchmark task.

## Current v7 method

v7 is the frozen website-generation method. It uses a requirement checklist, relevant experience retrieval, a small verified code pool, and post-task reflection. The generator receives the original requirement plus selected guidance; the original requirement remains binding. The code pool contains at most two short source-verified fragments from earlier successful sites in the same run.

## Main components

| Component | Responsibility |
|---|---|
| `src/reflection_case_memory.py` | Requirement checklist, retrieval, rewriting, deduplication, and utility |
| `src/code_memory.py` | Detect code facts and maintain the verified code pool |
| `src/post_task_reflection.py` | Produce evidence-grounded post-task reflections |
| `scripts/run_continual_memory.py` | Shared runner for No Memory and continual memory |
| `src/long_memory.py` | SQLite memory schema and provenance |
| `scripts/cluster/` | Slurm worker, queue, services, and output sync |

## Experimental safeguards

- Functional and appearance evidence remain separate.
- Similarity produces retrieval candidates only; it does not authorize automatic memory merges.
- The evaluation GUI trajectory and appearance result are retained as evidence.
- The actual Bolt chat export is the authority for the prompt delivered to the generator.
- Formal comparison arms use the same generator, evaluator, task set, and protocol.

## Active environment

Current formal WebGen runs are fully self-hosted on the University of Auckland H200 cluster: WebGen-LM-7B generates with Bolt.diy; Qwen2.5-VL-32B-Instruct evaluates functionality and appearance; Qwen2.5-VL-72B-Instruct-AWQ performs memory/reflection; bge-m3 embeds retrieval candidates.
