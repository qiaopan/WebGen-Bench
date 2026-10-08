#!/usr/bin/env python3
"""Create a fresh Long Memory snapshot by reflecting one completed No Memory run.

The source is read-only.  This supports a shared-prefix experiment: the same
completed task becomes history for a later Long Memory task without regenerating
the shared task or mixing its result into the Long Memory evaluation arm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from long_memory import initialize_database  # noqa: E402
from long_memory_integrations import (case_reflection_evidence, memory_llm_from_settings,
                                      setup_history)  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from post_task_reflection import append_reflection, create_reflection  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402
from run_continual_memory import evaluations, load_manifest, upsert_trajectory  # noqa: E402


def source_result(source: Path) -> dict:
    required = {
        "chat_path": source / "000001.json",
        "zip_path": source / "000001.zip",
        "prompt_path": source / "000001.prompt.txt",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Incomplete source run: {missing}")
    return {key: str(path.resolve()) for key, path in required.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True,
                        help="Completed task directory, e.g. .../tasks/000014/disabled")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--out", type=Path, required=True, help="New seed directory")
    parser.add_argument("--generator-model", required=True)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "data/experiment_splits/continual_domain_blocks/manifest.json")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()

    source = args.source_run.resolve()
    output = args.out.resolve()
    if output.exists():
        raise SystemExit(f"Seed output already exists: {output}")
    task = next((item for batch, item in load_manifest(args.manifest.resolve(), None)
                 if str(item["id"]) == args.task_id), None)
    if task is None:
        raise SystemExit(f"Unknown task ID: {args.task_id}")
    result = source_result(source)
    evaluation = evaluations(source, 1)

    output.mkdir(parents=True)
    database = output / "memory_snapshot.db"
    initialize_database(database)
    trajectory_id = upsert_trajectory(database, task, result, source, args.generator_model,
                                      evaluation, batch_number=1,
                                      delivered=True)

    settings, llm, embedder = make_memory_clients(args.memory_config.resolve())
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    from long_memory import connect_database
    with connect_database(database, read_only=True) as connection:
        row = connection.execute("SELECT * FROM trajectories WHERE trajectory_id=?", (trajectory_id,)).fetchone()
    trajectory = dict(row)
    reflection = create_reflection(
        reflection_llm, trajectory, case_reflection_evidence(trajectory),
        review=settings.memory.post_task_case_review,
        style=settings.memory.reflection_style,
        appearance_mode=settings.memory.appearance_reflection,
        setup_history=setup_history(()),
    )
    append_reflection(output / "post-task-reflections.jsonl", reflection)
    with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                              config=settings.memory) as memory:
        case_ids = memory.store(reflection)

    summary = {
        "source_run": str(source), "task_id": args.task_id,
        "trajectory_id": trajectory_id, "case_ids": case_ids,
        "generator_model": args.generator_model,
        "memory_model": settings.memory_llm["deployment"],
        "reflection_model": settings.reflection_llm["deployment"],
    }
    (output / "seed-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
