#!/usr/bin/env python3
"""Fill the statistics tables (run_facts, check_facts) from the trajectories already in a memory DB.

Stack is read from each trajectory's own generated archive, outcomes from its stored evaluation, cause labels
and per-label outcome counts from its stored reflection cases (one small Memory LLM call per trajectory,
reusing labels already in the table). A trajectory whose generation never built (execution_error) gets the
fixed build-failure label. --rebuild first clears both tables. Writes to the DB you name: use a copy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory import connect_database, ensure_optional_tables  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from memory_statistics import (BUILD_FAILURE_LABEL, build_check_rows, detect_stack, known_categories,  # noqa: E402
                               known_labels, label_causes, record_checks, record_run, setup_label)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--rebuild", action="store_true", help="clear run_facts and check_facts first")
    parser.add_argument("--reflections", type=Path, nargs="*", default=[],
                        help="post-task-reflections.jsonl files; give code/requirement grounding per case")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "data/experiment_splits/continual_domain_blocks/manifest.json")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    _, llm, _ = make_memory_clients(args.memory_config.resolve())
    from run_continual_memory import load_manifest
    tasks = {str(t["id"]): t for _, t in load_manifest(args.manifest.resolve(), None)}
    reflections = {}
    for path in args.reflections:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                reflections[item["trajectory_id"]] = item
    with connect_database(args.database, read_only=False) as connection:
        ensure_optional_tables(connection)
        if args.rebuild:
            connection.execute("DELETE FROM run_facts")
            connection.execute("DELETE FROM check_facts")
    with connect_database(args.database, read_only=True) as connection:
        done = {r[0] for r in connection.execute("SELECT trajectory_id FROM run_facts")}
        rows = [dict(r) for r in connection.execute(
            "SELECT * FROM trajectories WHERE agent_id='bolt' ORDER BY started_at, task_id")]
        for row in rows:
            row["cases"] = [dict(r) for r in connection.execute(
                "SELECT feature_object, outcome, root_cause_or_hypothesis FROM reflection_cases WHERE trajectory_id=? "
                "AND channel='functional' AND outcome IN ('partial','failure') ORDER BY created_at",
                (row["trajectory_id"],))]
    for row in rows:
        if row["trajectory_id"] in done:
            continue
        evaluation = json.loads(row["evaluation_results"] or "[]")
        counts = {"passed": 0, "partial": 0, "failed": 0}
        for item in evaluation:
            if item.get("check") != "appearance" and item.get("outcome") in counts:
                counts[item["outcome"]] += 1
        artifacts = json.loads(row["artifact_refs"] or "[]")
        archive = artifacts[0]["path"] if artifacts else ""
        stack = detect_stack(archive) if archive else "unknown"
        ok = row["run_status"] == "completed"
        outcomes: dict[str, dict[str, int]] = {}

        def add(label: str, kind: str, amount: int = 1) -> None:
            outcomes.setdefault(label, {})
            outcomes[label][kind] = outcomes[label].get(kind, 0) + amount

        if ok:
            functional = [c for c in row["cases"] if not c["feature_object"].startswith("[implementation]")]
            implementation = [c for c in row["cases"] if c["feature_object"].startswith("[implementation]")]
            with connect_database(args.database, read_only=True) as connection:
                existing = known_labels(connection, "bolt")
            labels = label_causes(llm, [c["root_cause_or_hypothesis"] for c in functional], existing)
            for label, case in zip(labels, functional):
                add(label, "failed" if case["outcome"] == "failure" else "partial")
            if implementation:
                labels = [*labels, setup_label(stack)]
                for case in implementation:
                    add(setup_label(stack), "failed" if case["outcome"] == "failure" else "partial")
        else:
            labels = [BUILD_FAILURE_LABEL, setup_label(stack)]
            add(BUILD_FAILURE_LABEL, "failed", counts["failed"])
            add(setup_label(stack), "failed", counts["failed"])
        record_run(args.database, agent_id="bolt", task_id=row["task_id"], trajectory_id=row["trajectory_id"],
                   stack=stack, generation_ok=ok, generation_attempts=None, failure_phase=None,
                   outcomes=counts, causes=labels, cause_outcomes=outcomes)
        if ok:
            reflection = reflections.get(row["trajectory_id"], {})
            cases = [c for c in [*reflection.get("functional_reflections", []), reflection.get("implementation_reflection")]
                     if isinstance(c, dict) and c.get("outcome") != "success"]
            checks = []
            for item in evaluation:
                name = str(item.get("check", ""))
                if name == "appearance" or item.get("outcome") not in ("passed", "partial", "failed"):
                    continue
                index = int(name.rsplit("_", 1)[-1])
                ui = tasks.get(row["task_id"], {}).get("ui_instruct", [])
                checks.append({"index": index, "outcome": item["outcome"],
                               "task": str(ui[index].get("task", "")) if index < len(ui) else name})
            with connect_database(args.database, read_only=True) as connection:
                categories = known_categories(connection, "bolt")
            record_checks(args.database, agent_id="bolt", task_id=row["task_id"], trajectory_id=row["trajectory_id"],
                          stack=stack, rows=build_check_rows(llm, categories, checks, cases))
        print(row["task_id"], "ok" if ok else "BUILD FAILED", stack, counts, outcomes)


if __name__ == "__main__":
    main()
