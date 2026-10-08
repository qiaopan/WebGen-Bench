#!/usr/bin/env python3
"""How stable are the LLM-made problem labels? Label the same causes twice, task by task, each run with its
own growing vocabulary (as in the real pipeline), then compare which causes end up sharing a label.
Reads causes from a DB (never writes). Memory LLM calls only."""
from __future__ import annotations

import argparse
import itertools
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from memory_statistics import label_causes  # noqa: E402


def label_run(llm, groups: list[list[tuple[str, str]]]) -> dict[str, str]:
    vocabulary: dict[str, int] = {}
    out: dict[str, str] = {}
    for group in groups:
        existing = [label for label, _ in sorted(vocabulary.items(), key=lambda item: -item[1])]
        labels = label_causes(llm, [text for _, text in group], existing)
        for (case_id, _), label in zip(group, labels):
            out[case_id] = label
            vocabulary[label] = vocabulary.get(label, 0) + 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    _, llm, _ = make_memory_clients(args.memory_config.resolve())
    con = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT t.task_id, c.case_id, c.root_cause_or_hypothesis FROM reflection_cases c JOIN trajectories t "
        "USING (trajectory_id) WHERE c.channel='functional' AND c.feature_object NOT LIKE '[implementation]%' "
        "AND c.outcome IN ('partial','failure') ORDER BY t.started_at, c.created_at").fetchall()
    by_task: dict[str, list[tuple[str, str]]] = {}
    for task, case_id, cause in rows:
        by_task.setdefault(task, []).append((case_id, cause))
    groups = list(by_task.values())
    first, second = label_run(llm, groups), label_run(llm, groups)
    ids = [case_id for group in groups for case_id, _ in group if case_id in first and case_id in second]
    agree = total = 0
    for a, b in itertools.combinations(ids, 2):
        total += 1
        agree += (first[a] == first[b]) == (second[a] == second[b])
    print(f"causes labelled: {len(ids)}; pairwise agreement between two runs: {agree}/{total} = {agree / max(total, 1):.0%}")
    print(f"distinct labels: run1 {len(set(first.values()))}, run2 {len(set(second.values()))}")
    text = {case_id: cause for group in groups for case_id, cause in group}
    for case_id in ids:
        print(f"[{first[case_id]} | {second[case_id]}] {text[case_id][:120]}")


if __name__ == "__main__":
    main()
