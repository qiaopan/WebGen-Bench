#!/usr/bin/env python3
"""Copy a memory DB and remove everything produced by/after the given tasks (COPY only).

Used to replay a task against the memory state that existed before it ran. The
source DB is never modified; append-only triggers are dropped in the copy and
restored after the deletes.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude-task-ids", required=True, help="Comma-separated, e.g. 000018,000019")
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} already exists")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.source, args.out)
    task_ids = [value.strip() for value in args.exclude_task_ids.split(",") if value.strip()]
    marks = ",".join("?" * len(task_ids))
    con = sqlite3.connect(args.out)
    triggers = con.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
    for name, _ in triggers:
        con.execute(f'DROP TRIGGER "{name}"')
    threshold = con.execute(f"SELECT MIN(started_at) FROM trajectories WHERE task_id IN ({marks})",
                            task_ids).fetchone()[0]
    if threshold is None:
        raise SystemExit("None of the excluded tasks exist in the source DB")
    # Experiences/skills are created by consolidation after a task, so cut by time.
    for table, key in (("experiences", "record_id"), ("skills", "record_id")):
        col = "experience_record_id" if table == "experiences" else "skill_record_id"
        con.execute(f"DELETE FROM memory_sources WHERE {col} IN (SELECT {key} FROM {table} WHERE created_at >= ?)",
                    (threshold,))
        con.execute(f"DELETE FROM {table} WHERE created_at >= ?", (threshold,))
    con.execute(f"DELETE FROM reflection_cases WHERE trajectory_id IN "
                f"(SELECT trajectory_id FROM trajectories WHERE task_id IN ({marks}))", task_ids)
    con.execute(f"DELETE FROM trajectories WHERE task_id IN ({marks})", task_ids)
    for _, sql in triggers:
        con.execute(sql)
    con.commit()
    kept = [row[0] for row in con.execute("SELECT task_id FROM trajectories ORDER BY started_at")]
    print(f"snapshot {args.out}: trajectories={kept} cases={con.execute('SELECT COUNT(*) FROM reflection_cases').fetchone()[0]} "
          f"experiences={con.execute('SELECT COUNT(*) FROM experiences').fetchone()[0]} triggers={len(triggers)}")


if __name__ == "__main__":
    main()
