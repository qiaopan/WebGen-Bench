# Single-codebase experiment execution

## Safety boundary

All experimental conditions run from the same Git commit. The only intended
difference is `memory_mode`:

- `disabled`: no database connection, no retrieval, and no write;
- `learn`: retrieval and write are allowed, only for G1 and G3;
- `read_only`: retrieval is allowed but write is forbidden, only for G2/G4/G5.

The protocol and schedule are already encoded in
`config/experiment_protocol.json`. Validate it without calling any model:

```shell
python scripts/build_experiment_plan.py
```

Generate a machine-readable schedule when the live runner is ready:

```shell
python scripts/build_experiment_plan.py \
  --output outputs/experiment/run-plan.json
```

The plan contains 201 website-generation events for one complete staged pass:
41 `learn`, 80 `disabled`, and 80 `read_only`. Paired evaluation order is fixed:
odd-position websites run `disabled` then `read_only`; even-position websites
run `read_only` then `disabled`.

## Current generation and evaluation interfaces

The Bolt generator now accepts an explicit output directory and can run one
record from a group while preserving the record's original position:

```shell
python src/automatic_bolt_diy/eval_bolt_diy.py \
  --jsonl_path data/experiment_splits/groups/group_02_dev_evaluate.jsonl \
  --record_id 000004 \
  --download_dir outputs/experiment/stage1/development_evaluation/g2/disabled
```

Use the same group file during UI and appearance evaluation. This prevents a
20-site subset from being matched to the first 20 records of the original test
file:

```shell
python src/ui_test_bolt/ui_eval_with_answer.py \
  --in_dir outputs/experiment/stage1/development_evaluation/g2/disabled \
  --test_file data/experiment_splits/groups/group_02_dev_evaluate.jsonl

python src/grade_appearance_bolt_diy/eval_appearance.py \
  outputs/experiment/stage1/development_evaluation/g2/disabled \
  -t data/experiment_splits/groups/group_02_dev_evaluate.jsonl

python src/grade_appearance_bolt_diy/compute_grade.py \
  --in_dir outputs/experiment/stage1/development_evaluation/g2/disabled \
  --test_file data/experiment_splits/groups/group_02_dev_evaluate.jsonl
```

Every generation output directory records the Git commit, dataset hash, model,
provider, and Bolt URL. Reusing a directory with different settings fails rather
than silently mixing results.

## Remaining live-memory integration

The protocol switch and leakage rules are implemented, but the research-specific
memory adapter is intentionally not invented here. Before a live `learn` or
`read_only` event is executed, the Bolt runtime must expose the same three-state
`memory_mode` switch and prove in its run log that:

- `disabled` has zero database reads and writes;
- `learn` records its reads and writes;
- `read_only` has zero writes;
- evaluation feedback is never committed to memory.

Until that adapter and its assertions exist, the generated plan is a validated
schedule, not authorization to run paid experiments.
