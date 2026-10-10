# Current Handoff

[English](HANDOFF.en.md) | [中文完整记录](HANDOFF.md)

> English current-state guide, updated 2026-10-09. The complete chronological handoff and all operational detail are maintained in [Chinese](HANDOFF.md).

## Current result

The frozen v7 Long Memory run completed all 101 WebGen-Bench tasks. Functional accuracy is **40.0%**, versus **28.5%** for No Memory and **30.9%** for v4 text memory. The paired v7 minus No Memory task-level difference is +11.5 percentage points, with bootstrap 95% CI [6.0, 16.9]. v7 has 13 zero-score tasks, compared with 30 for No Memory.

The appearance result does not support a benefit: on the 68 tasks with usable sites in both arms, No Memory scores 3.25 and v7 scores 3.22. The claim is therefore limited to functional improvement.

## Current work

The active cluster worker is running order-robustness experiments. Long Memory and No Memory are paired task-by-task with an ABBA order. The first active schedule is the seed-11 domain-block shuffle. Each run starts from an empty memory database and records the exact order, retrieval/injection data, and raw evaluation output.

The checklist-only v7 ablation is complete: it reaches 31.8% accuracy, versus 28.5% for No Memory and 40.0% for v7. The checklist helps, but the larger gain comes from Long Memory.

## Next experimental priorities

1. Finish the four order schedules for WebGen-LM-7B + Bolt and report paired task-level differences with bootstrap confidence intervals.
2. Run the fixed-code-prefix ablation to separate accumulated memory from a prefix present from task one.
3. If order robustness holds, test one stronger generator while holding Bolt, memory, and evaluators fixed.
4. Do not run a full OpenHands/Aider comparison yet. Agent replacement changes file operations, context, prompt injection, and repair behavior; it first requires a small integration pilot.

## Important constraints

- Do not modify frozen v7 while order experiments run.
- Do not auto-repair generated code after generation; that would violate the official protocol.
- Preserve unrelated worktree changes and use `outputs/experiment/*/continual-report.json` and `progress.jsonl` as the source of truth.
- Before a new paid generation run, provide a comparison table and obtain user confirmation.
