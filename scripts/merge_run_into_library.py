#!/usr/bin/env python3
"""Add finished runs to the working library (continual accumulation): trajectory, statistics rows, and cases.

For each --run-db, every trajectory that the library does not have yet is copied together with its
run_facts / check_facts rows. Its reflection cases are then re-derived with the CURRENT reflection code
(the same code for every run) and stored; the run's own case rows are not copied. Several runs of the same
task are all kept. The library is backed up first (memory_snapshot.db.bak_<n>); the run DBs are only read.
Cost: one reflection per added trajectory (Memory LLM + embeddings); no website generation.
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


def copy_rows(source: sqlite3.Connection, target: sqlite3.Connection, table: str, trajectory_ids: list[str]) -> int:
    if not trajectory_ids:
        return 0
    marks = ",".join("?" * len(trajectory_ids))
    rows = source.execute(f"SELECT * FROM {table} WHERE trajectory_id IN ({marks})", trajectory_ids).fetchall()
    if not rows:
        return 0
    columns = [c for c in rows[0].keys() if c in {r[1] for r in target.execute(f"PRAGMA table_info({table})")}]
    for row in rows:
        values = [row[c] for c in columns]
        if table == "trajectories":
            # (agent, task, attempt_no) is unique: a repeated run of a task becomes its next attempt.
            index = columns.index("attempt_no")
            values[index] = target.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM trajectories WHERE agent_id=? AND task_id=?",
                (row["agent_id"], row["task_id"])).fetchone()[0]
        target.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True, help="directory holding memory_snapshot.db")
    parser.add_argument("--run-db", type=Path, nargs="+", required=True)
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    database = args.library / "memory_snapshot.db"
    number = 1
    while (args.library / f"memory_snapshot.db.bak_{number}").exists():
        number += 1
    backup = args.library / f"memory_snapshot.db.bak_{number}"
    shutil.copy(database, backup)
    print(f"backup: {backup}")

    added: list[str] = []
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    have = {r[0] for r in con.execute("SELECT trajectory_id FROM trajectories")}
    with con:
        for run_db in args.run_db:
            source = sqlite3.connect(f"file:{run_db}?mode=ro", uri=True)
            source.row_factory = sqlite3.Row
            new = [r["trajectory_id"] for r in source.execute("SELECT trajectory_id FROM trajectories ORDER BY started_at")
                   if r["trajectory_id"] not in have]
            for table in ("trajectories", "run_facts", "check_facts"):
                print(f"{run_db.parent.name}: {table}: copied {copy_rows(source, con, table, new)} row(s)")
            have.update(new)
            added += new
            source.close()
    trajectories = [dict(r) for r in con.execute("SELECT * FROM trajectories ORDER BY started_at")]
    con.close()

    settings, llm, embedder = make_memory_clients(args.memory_config.resolve())
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    reflections_path = args.library / "post-task-reflections.jsonl"
    events: list[dict] = []
    with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder, config=settings.memory,
                              log=events.append) as memory:
        for position, trajectory in enumerate(trajectories):
            if trajectory["trajectory_id"] not in added:
                continue
            reflection = create_reflection(reflection_llm, trajectory, case_reflection_evidence(trajectory),
                                           review=settings.memory.post_task_case_review,
                                           style=settings.memory.reflection_style,
                                           appearance_mode=settings.memory.appearance_reflection,
                                           setup_history=setup_history(trajectories[:position]))
            append_reflection(reflections_path, reflection)
            case_ids = memory.store(reflection)
            print(f"{trajectory['task_id']} {trajectory['trajectory_id'][:8]}: stored {len(case_ids)} case(s) "
                  f"(functional={len(reflection['functional_reflections'])}, "
                  f"implementation={'yes' if reflection['implementation_reflection'] else 'no'}, "
                  f"appearance={len(reflection.get('appearance_reflections', []))}, "
                  f"appearance dropped={len(reflection.get('appearance_dropped_no_citation', []))})")
    import json
    with (args.library / "memory-events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))


if __name__ == "__main__":
    main()
