# WebGen long-memory experiment data split

## Sources and category discrepancy

- The training source is `data/train.jsonl`: 6,667 records across 21 observed
  `application_type` labels.
- The final-test source is `data/test.jsonl`: 101 records across 20 labels.
- `News Aggregators` occurs in train but not in the official test set. The paper
  text reports 20 application types, so the observed 21-label train distribution
  is recorded as a dataset discrepancy rather than silently merged or removed.

## Deterministic stratified split

Run `python scripts/create_experiment_splits.py`. With the default seed `792`,
the script independently shuffles every training category and selects seven
records per category. Each resulting group therefore has 21 records, one per
observed train category, and all seven groups are mutually disjoint.

| Stage | File | Records | Purpose |
| --- | --- | ---: | --- |
| 1 | `stages/stage1_memory.jsonl` | 21 | Build the initial long-memory DB |
| 1 | `stages/stage1_evaluate_train.jsonl` | 21 | Reused development comparison: no-memory vs long-memory |
| 2 | `stages/stage2_memory_append.jsonl` | 42 | Append two new groups to memory |
| 2 | `stages/stage2_evaluate_train.jsonl` | 21 | New development comparison: no-memory vs long-memory |
| 3 | `stages/stage3_memory_append.jsonl` | 42 | Append two final groups and freeze memory |
| 3 | `stages/stage3_final_test.jsonl` | 101 | One final comparison on the official test set |

Stage 1 method-development iterations reuse the same 21 memory-building records
and the same 21 held-out development records. Changing the sample after observing
results would turn the development procedure into an uncontrolled source of
variance. Memory is rebuilt from an empty DB when the memory algorithm or schema
changes; otherwise later stages append only their designated memory groups.

## Evaluation and leakage controls

The 6,667 training records have no non-empty `ui_instruct.task` entries. Thus the
two evaluate-train groups can directly support website generation and appearance
evaluation, but WebVoyager functional evaluation requires a separately generated
or human-authored task set. That task set must be created once, frozen before the
no-memory/long-memory comparison, and shared by both branches.

Evaluate-train inputs, generated evaluation tasks, trajectories, screenshots,
scores, and evaluator feedback must never be inserted into the memory DB. The
official 101-record test set is opened only after the method, prompts, retrieval
settings, stopping rules, and accumulated memory are frozen. Nothing derived from
the final test set may update memory. This prevents test-time leakage even though
the underlying model parameters remain fixed.

The generated `data/experiment_splits/manifest.json` records the random seed,
source-file SHA-256 hashes, selected IDs, counts, and leakage rules required to
reproduce the split.
