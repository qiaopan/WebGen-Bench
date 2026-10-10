# Current Durable Decisions

[English](DECISIONS.en.md) | [中文完整记录](DECISIONS.md)

> This is an English guide to active decisions. The complete decision history, rationale, and superseded decisions are maintained in [Chinese](DECISIONS.md).

## Experimental validity

- Long Memory may learn only from earlier tasks. It may not use final evaluation feedback to repair the same task.
- Compare Long Memory and No Memory with matched generator, evaluator, task, and protocol settings.
- Report paired task-level effects and confidence intervals. Do not treat individual checks as independent samples.
- Separate logic failures, interaction-budget exhaustion, start failures, and appearance limitations in analysis.

## Frozen v7

v7 is the formal method for current ablations and order experiments. It retains original requirements, adds a checklist, injects specific rather than generic experience, and uses verified code fragments only after a recurring failure pattern appears. Candidate v8 import/scaffold changes are not part of the formal experiment.

## Order robustness

Task order is an algorithmic treatment for Long Memory because it determines what history is available. The formal 7B experiment uses four empty-bank schedules: original domain-block order, two seeded domain-block shuffles, and a cross-domain interleaved order. Long Memory and No Memory run task-by-task in ABBA order.

## Model and agent scope

Order robustness is the priority. If it holds, add one generator while keeping Bolt and the whole memory/evaluation pipeline fixed. The current repository README records the planned stronger-model comparison.

Do not use a full cross-agent matrix as the next study. Changing to OpenHands or Aider creates a new agent-specific memory integration because it changes file operations, context, prompt insertion, tools, and repair loops. First run a roughly 20-task stratified integration pilot; expand only if memory delivery and evaluation remain stable.

## Measurement robustness

Before regenerating sites solely to study visual quality, reuse existing screenshots for a second visual-model appearance regrade. For functional robustness, sample v7 wins, losses, and ties for a second GUI/vision evaluation, with emphasis on blank pages, interaction-budget exhaustion, and apparent misgrading.
