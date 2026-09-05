#!/usr/bin/env python3
"""Create a deterministic five-group staged split from WebGen-Bench test data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path


GROUP_SIZES = {
    "group_01_memory_seed": 21,
    "group_02_dev_evaluate": 20,
    "group_03_memory_append": 20,
    "group_04_final_test_a": 20,
    "group_05_final_test_b": 20,
}
DEV_EVALUATE = "group_02_dev_evaluate"
FINAL_GROUPS = {"group_04_final_test_a", "group_05_final_test_b"}


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


def technical_primary(record: dict) -> str:
    return record.get("Category", {}).get("primary_category", "Unknown")


def task_primary_counts(record: dict) -> Counter[str]:
    return Counter(
        item.get("task_category", {}).get("primary_category", "Unknown")
        for item in record.get("ui_instruct", [])
    )


def feature_counts(records: list[dict]) -> dict[str, Counter[str]]:
    result: dict[str, Counter[str]] = {
        "application_type": Counter(),
        "technical_primary": Counter(),
        "task_primary": Counter(),
    }
    for record in records:
        result["application_type"][record["application_type"]] += 1
        result["technical_primary"][technical_primary(record)] += 1
        result["task_primary"].update(task_primary_counts(record))
    return result


def objective(groups: dict[str, list[dict]], population: list[dict]) -> float:
    """Measure distribution drift; lower is better."""
    overall = feature_counts(population)
    score = 0.0
    weights = {
        "application_type": 4.0,
        "technical_primary": 2.0,
        "task_primary": 2.0,
    }
    for records in groups.values():
        observed = feature_counts(records)
        share = len(records) / len(population)
        for family, family_weight in weights.items():
            for label, total in overall[family].items():
                expected = total * share
                score += family_weight * ((observed[family][label] - expected) ** 2) / max(expected, 1.0)

        expected_tasks = sum(len(item.get("ui_instruct", [])) for item in population) * share
        observed_tasks = sum(len(item.get("ui_instruct", [])) for item in records)
        score += 1.5 * ((observed_tasks - expected_tasks) ** 2) / max(expected_tasks, 1.0)

    final_records = [record for name in FINAL_GROUPS for record in groups[name]]
    final_observed = feature_counts(final_records)
    final_share = len(final_records) / len(population)
    for family, family_weight in weights.items():
        for label, total in overall[family].items():
            expected = total * final_share
            score += 2.0 * family_weight * ((final_observed[family][label] - expected) ** 2) / max(expected, 1.0)
    return score


def is_valid(groups: dict[str, list[dict]], categories: set[str]) -> bool:
    if any(len(groups[name]) != size for name, size in GROUP_SIZES.items()):
        return False
    dev_counts = Counter(record["application_type"] for record in groups[DEV_EVALUATE])
    if set(dev_counts) != categories or any(count != 1 for count in dev_counts.values()):
        return False
    final_categories = {
        record["application_type"]
        for name in FINAL_GROUPS
        for record in groups[name]
    }
    return final_categories == categories


def make_candidate(records: list[dict], seed: int, attempt: int) -> dict[str, list[dict]]:
    rng = random.Random(f"{seed}:{attempt}")
    categories = sorted({record["application_type"] for record in records})
    by_category = {
        category: [record for record in records if record["application_type"] == category]
        for category in categories
    }
    for category_records in by_category.values():
        rng.shuffle(category_records)

    groups = {name: [] for name in GROUP_SIZES}
    for category in categories:
        groups[DEV_EVALUATE].append(by_category[category].pop())

    final_reserved = []
    for category in categories:
        final_reserved.append(by_category[category].pop())
    rng.shuffle(final_reserved)
    groups["group_04_final_test_a"].extend(final_reserved[:10])
    groups["group_05_final_test_b"].extend(final_reserved[10:])

    remainder = [record for category in categories for record in by_category[category]]
    rng.shuffle(remainder)
    capacities = [
        ("group_01_memory_seed", 21),
        ("group_03_memory_append", 20),
        ("group_04_final_test_a", 10),
        ("group_05_final_test_b", 10),
    ]
    cursor = 0
    for name, count in capacities:
        groups[name].extend(remainder[cursor : cursor + count])
        cursor += count
    return groups


def optimise_split(records: list[dict], seed: int, attempts: int) -> tuple[dict[str, list[dict]], float]:
    categories = {record["application_type"] for record in records}
    if len(categories) != 20:
        raise ValueError(f"Expected 20 test application types, found {len(categories)}")
    counts = Counter(record["application_type"] for record in records)
    if min(counts.values()) < 2:
        raise ValueError("Every application type needs at least two records")

    best_groups: dict[str, list[dict]] | None = None
    best_score = math.inf
    for attempt in range(attempts):
        groups = make_candidate(records, seed, attempt)
        if not is_valid(groups, categories):
            raise AssertionError("Candidate violates split constraints")
        score = objective(groups, records)
        if score < best_score:
            best_groups = groups
            best_score = score
    assert best_groups is not None
    for group in best_groups.values():
        group.sort(key=lambda record: record["id"])
    return best_groups, best_score


def group_summary(records: list[dict]) -> dict:
    tasks = [item for record in records for item in record.get("ui_instruct", [])]
    return {
        "records": len(records),
        "ui_tasks": len(tasks),
        "application_types": dict(sorted(Counter(record["application_type"] for record in records).items())),
        "technical_primary": dict(sorted(Counter(technical_primary(record) for record in records).items())),
        "ui_task_primary": dict(
            sorted(
                Counter(
                    item.get("task_category", {}).get("primary_category", "Unknown")
                    for item in tasks
                ).items()
            )
        ),
        "ids": [record["id"] for record in records],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=Path, default=Path("data/test.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/experiment_splits"))
    parser.add_argument("--seed", type=int, default=792)
    parser.add_argument("--attempts", type=int, default=50000)
    args = parser.parse_args()

    test = load_jsonl(args.test)
    if len(test) != sum(GROUP_SIZES.values()):
        raise ValueError(f"Expected 101 test records, found {len(test)}")
    groups, score = optimise_split(test, args.seed, args.attempts)

    for name, records in groups.items():
        write_jsonl(args.output / "groups" / f"{name}.jsonl", records)

    stage_files = {
        "stage1_memory_seed.jsonl": groups["group_01_memory_seed"],
        "stage1_dev_evaluate.jsonl": groups["group_02_dev_evaluate"],
        "stage2_memory_append.jsonl": groups["group_03_memory_append"],
        "stage3_final_test.jsonl": groups["group_04_final_test_a"] + groups["group_05_final_test_b"],
    }
    for filename, records in stage_files.items():
        write_jsonl(args.output / "stages" / filename, records)

    all_ids = [record["id"] for records in groups.values() for record in records]
    if len(all_ids) != len(set(all_ids)) or set(all_ids) != {record["id"] for record in test}:
        raise AssertionError("Groups must be disjoint and cover all 101 records")

    manifest = {
        "schema_version": 2,
        "seed": args.seed,
        "search_attempts": args.attempts,
        "balance_objective": round(score, 6),
        "protocol_name": "five-group stratified staged split",
        "not_standard_five_fold_cross_validation": True,
        "source": {"test": {"path": str(args.test), "records": len(test), "sha256": sha256(args.test)}},
        "hard_constraints": [
            "The five groups are mutually disjoint and together contain all 101 official test records.",
            "The 20-record development-evaluation group contains exactly one website from every application type.",
            "The combined 40-record final test contains every application type at least once.",
            "Group sizes are fixed at 21, 20, 20, 20, and 20.",
        ],
        "balanced_dimensions": [
            "application_type",
            "Category.primary_category",
            "ui_instruct.task_category.primary_category",
            "number of UI tasks",
        ],
        "groups": {name: group_summary(records) for name, records in groups.items()},
        "stages": {
            "stage_1_method_development": {
                "memory_write": ["group_01_memory_seed"],
                "paired_no_memory_vs_long_memory_evaluation": ["group_02_dev_evaluate"],
            },
            "stage_2_memory_expansion_and_freeze": {
                "memory_append": ["group_03_memory_append"],
                "paired_confirmation_evaluation": ["group_02_dev_evaluate"],
            },
            "stage_3_final_evaluation": {
                "memory_frozen": True,
                "paired_no_memory_vs_long_memory_evaluation": [
                    "group_04_final_test_a",
                    "group_05_final_test_b",
                ],
            },
        },
        "leakage_controls": [
            "Development-evaluation and final-test samples, tasks, trajectories, screenshots, scores, and feedback never update memory.",
            "Only groups 01 and 03 may write to the long-memory database.",
            "No-memory and long-memory conditions use the same prompts, UI tasks, evaluator, limits, and sample order.",
            "The method, prompts, retrieval settings, stopping rules, and memory database are frozen before stage 3.",
            "Final results are reported for the combined 40-site final test; groups 04 and 05 also provide two replicate summaries.",
        ],
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Created five disjoint groups covering all 101 test records")
    for name, records in groups.items():
        print(f"{name}: {len(records)} websites, {sum(len(r.get('ui_instruct', [])) for r in records)} UI tasks")
    print(f"Balance objective: {score:.6f}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
