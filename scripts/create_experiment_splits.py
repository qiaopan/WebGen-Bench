#!/usr/bin/env python3
"""Create deterministic, category-stratified WebGen experiment splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path


GROUP_LAYOUT = (
    ("memory_01", "stage1", "memory"),
    ("evaluate_01", "stage1", "evaluate_train"),
    ("memory_02", "stage2", "memory_append"),
    ("memory_03", "stage2", "memory_append"),
    ("evaluate_02", "stage2", "evaluate_train"),
    ("memory_04", "stage3", "memory_append"),
    ("memory_05", "stage3", "memory_append"),
)


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_ui_task(record: dict) -> bool:
    return any(item.get("task", "").strip() for item in record.get("ui_instruct", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/train.jsonl"))
    parser.add_argument("--test", type=Path, default=Path("data/test.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/experiment_splits"))
    parser.add_argument("--seed", type=int, default=792)
    args = parser.parse_args()

    train = load_jsonl(args.train)
    test = load_jsonl(args.test)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for record in train:
        by_category[record["application_type"]].append(record)

    categories = sorted(by_category)
    required_per_category = len(GROUP_LAYOUT)
    undersized = {
        category: len(records)
        for category, records in by_category.items()
        if len(records) < required_per_category
    }
    if undersized:
        raise ValueError(f"Categories with fewer than {required_per_category} records: {undersized}")

    selected_by_category: dict[str, list[dict]] = {}
    for category in categories:
        candidates = list(by_category[category])
        random.Random(f"{args.seed}:{category}").shuffle(candidates)
        selected_by_category[category] = candidates[:required_per_category]

    groups: dict[str, list[dict]] = {}
    for index, (group_name, _stage, _purpose) in enumerate(GROUP_LAYOUT):
        groups[group_name] = [selected_by_category[category][index] for category in categories]

    selected_ids = [record["id"] for records in groups.values() for record in records]
    if len(selected_ids) != len(set(selected_ids)):
        raise AssertionError("Train groups overlap")
    for group_name, records in groups.items():
        if len(records) != len(categories):
            raise AssertionError(f"{group_name} does not contain one record per category")
        if sorted(record["application_type"] for record in records) != categories:
            raise AssertionError(f"{group_name} category coverage is invalid")

    args.output.mkdir(parents=True, exist_ok=True)
    for group_name, records in groups.items():
        write_jsonl(args.output / "groups" / f"{group_name}.jsonl", records)

    stage_files = {
        "stage1_memory.jsonl": groups["memory_01"],
        "stage1_evaluate_train.jsonl": groups["evaluate_01"],
        "stage2_memory_append.jsonl": groups["memory_02"] + groups["memory_03"],
        "stage2_evaluate_train.jsonl": groups["evaluate_02"],
        "stage3_memory_append.jsonl": groups["memory_04"] + groups["memory_05"],
        "stage3_final_test.jsonl": test,
    }
    for filename, records in stage_files.items():
        write_jsonl(args.output / "stages" / filename, records)

    manifest = {
        "schema_version": 1,
        "seed": args.seed,
        "selection_method": "For each train application_type, independently shuffle with seed '<seed>:<category>' and take seven records.",
        "source": {
            "train": {"path": str(args.train), "records": len(train), "sha256": sha256(args.train)},
            "test": {"path": str(args.test), "records": len(test), "sha256": sha256(args.test)},
        },
        "train_categories": categories,
        "train_category_count": len(categories),
        "test_categories": sorted({record["application_type"] for record in test}),
        "test_category_count": len({record["application_type"] for record in test}),
        "train_records_with_nonempty_ui_tasks": sum(has_ui_task(record) for record in train),
        "test_records_with_nonempty_ui_tasks": sum(has_ui_task(record) for record in test),
        "groups": {
            group_name: {
                "stage": stage,
                "purpose": purpose,
                "records": len(groups[group_name]),
                "ids": [record["id"] for record in groups[group_name]],
            }
            for group_name, stage, purpose in GROUP_LAYOUT
        },
        "stage_files": {filename: len(records) for filename, records in stage_files.items()},
        "leakage_controls": [
            "All seven train groups are mutually disjoint.",
            "Stage 1 iterations reuse the same memory_01 and evaluate_01 records.",
            "Evaluate-train records and their feedback must never update memory.",
            "The 101 official test records are used only after the method and memory are frozen.",
            "Final-test prompts, UI tasks, trajectories, screenshots, and scores must never update memory.",
        ],
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Created {len(groups)} disjoint train groups ({len(selected_ids)} records)")
    print(f"Train categories per group: {len(categories)}")
    print(f"Final test records: {len(test)}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
