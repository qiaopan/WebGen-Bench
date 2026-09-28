#!/usr/bin/env python3
"""Re-derive reflection cases for every trajectory in a snapshot DB with the current reflection rules.

Works on a COPY: old cases, experiences and their provenance rows are removed in the copy,
then each trajectory (chronological) is re-reflected from its stored evaluation results and
chat trace and stored as new cases. No website generation; Memory LLM + embeddings only.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import case_reflection_evidence, memory_llm_from_settings, setup_history  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from post_task_reflection import append_reflection, create_reflection  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Output directory (new)")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    parser.add_argument("--only-task-ids", help="Comma-separated; redo only these tasks, keep other cases")
    args = parser.parse_args()
    only = {v.strip() for v in args.only_task_ids.split(",")} if args.only_task_ids else None
    if args.out.exists():
        raise SystemExit(f"{args.out} already exists")
    args.out.mkdir(parents=True)
    database = args.out / "memory_snapshot.db"
    shutil.copy(args.source, database)

    con = sqlite3.connect(database)
    triggers = con.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
    for name, _ in triggers:
        con.execute(f'DROP TRIGGER "{name}"')
    if only is None:
        for table in ("memory_sources", "skills", "experiences", "reflection_cases"):
            con.execute(f"DELETE FROM {table}")
    else:
        marks = ",".join("?" * len(only))
        con.execute(f"DELETE FROM reflection_cases WHERE trajectory_id IN "
                    f"(SELECT trajectory_id FROM trajectories WHERE task_id IN ({marks}))", list(only))
    for _, sql in triggers:
        con.execute(sql)
    con.commit()
    con.row_factory = sqlite3.Row
    trajectories = [dict(row) for row in con.execute("SELECT * FROM trajectories ORDER BY started_at")]
    con.close()

    settings, llm, embedder = make_memory_clients(args.memory_config.resolve())
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    print(f"reflection model: {settings.reflection_llm['deployment']}; other memory steps: "
          f"{settings.memory_llm['deployment']}")
    reflections_path = args.out / "post-task-reflections.jsonl"
    events: list[dict] = []
    with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder, config=settings.memory,
                              log=events.append) as memory:
        for position, trajectory in enumerate(trajectories):
            if only is not None and trajectory["task_id"] not in only:
                continue
            reflection = create_reflection(reflection_llm, trajectory, case_reflection_evidence(trajectory),
                                        review=settings.memory.post_task_case_review,
                                        style=settings.memory.reflection_style,
                                        appearance_mode=settings.memory.appearance_reflection,
                                        setup_history=setup_history(trajectories[:position]))
            append_reflection(reflections_path, reflection)
            case_ids = memory.store(reflection)
            print(f"{trajectory['task_id']}: stored {len(case_ids)} cases "
                  f"(functional={len(reflection['functional_reflections'])}, "
                  f"appearance={'yes' if reflection['appearance_reflection'] else 'no'})")
    import json
    (args.out / "memory-events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")


if __name__ == "__main__":
    main()
