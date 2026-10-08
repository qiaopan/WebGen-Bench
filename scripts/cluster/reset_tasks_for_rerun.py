#!/usr/bin/env python3
"""Undo the recorded results of some (task, arm) pairs so a later queue job runs them again.

For tasks whose result is known to be wrong for reasons outside the model (the HEALTH_BLOCK entries in
health-warnings.jsonl). Same procedure as the Phase 1 re-runs (HANDOFF): back up memory.db and
progress.jsonl; drop the tasks' progress rows; in Long Memory archive their active reflection cases and
delete their run_facts / check_facts / case_supports rows (memory_sources and trajectories are
append-only and stay); move tasks/<id>/<mode> aside. Without --apply it only prints what it would do.

Run it while the queue is between database writes (e.g. while the next task is generating), or after
the job ended: the runner appends to progress.jsonl when a task finishes.

Usage: reset_tasks_for_rerun.py OUTPUT_DIR {disabled|continual} TASK_ID [TASK_ID ...] [--apply]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("mode", choices=("disabled", "continual"))
    parser.add_argument("task_ids", nargs="+")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ids = set(args.task_ids)
    progress = args.output / "progress.jsonl"
    rows = progress.read_text(encoding="utf-8").splitlines()
    keep = [r for r in rows if not (json.loads(r).get("task_id") in ids and json.loads(r).get("mode") == args.mode)]
    print(f"progress.jsonl: drop {len(rows) - len(keep)} row(s) for {sorted(ids)} {args.mode}")

    db_path = args.output / "memory.db"
    plan = []
    if args.mode == "continual" and db_path.is_file():
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            marks = ",".join("?" * len(ids))
            trajectories = [r[0] for r in db.execute(
                f"SELECT trajectory_id FROM trajectories WHERE task_id IN ({marks})", sorted(ids))]
            tmarks = ",".join("?" * len(trajectories)) or "''"
            for label, sql in (
                    ("archive active reflection_cases", f"SELECT COUNT(*) FROM reflection_cases WHERE status='active' AND trajectory_id IN ({tmarks})"),
                    ("delete run_facts", f"SELECT COUNT(*) FROM run_facts WHERE trajectory_id IN ({tmarks})"),
                    ("delete check_facts", f"SELECT COUNT(*) FROM check_facts WHERE trajectory_id IN ({tmarks})"),
                    ("delete case_supports", f"SELECT COUNT(*) FROM case_supports WHERE supporting_trajectory_id IN ({tmarks})")):
                count = db.execute(sql, trajectories).fetchone()[0]
                plan.append((label, count))
                print(f"memory.db: {label}: {count}")
    moves = [(args.output / "tasks" / t / args.mode, args.output / "tasks" / t / f"{args.mode}.rerun-backup-{stamp}")
             for t in sorted(ids) if (args.output / "tasks" / t / args.mode).is_dir()]
    for src, dst in moves:
        print(f"move {src} -> {dst.name}")
    if not args.apply:
        print("dry run: nothing changed (add --apply)")
        return

    shutil.copy2(progress, progress.with_name(f"progress.jsonl.before-rerun-{stamp}"))
    if args.mode == "continual" and db_path.is_file():
        backup = db_path.with_name(f"memory.db.before-rerun-{stamp}")
        with sqlite3.connect(db_path, timeout=60) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
        with sqlite3.connect(db_path, timeout=60) as db:
            marks = ",".join("?" * len(ids))
            trajectories = [r[0] for r in db.execute(
                f"SELECT trajectory_id FROM trajectories WHERE task_id IN ({marks})", sorted(ids))]
            tmarks = ",".join("?" * len(trajectories)) or "''"
            db.execute(f"UPDATE reflection_cases SET status='archived' WHERE status='active' AND trajectory_id IN ({tmarks})", trajectories)
            for table, column in (("run_facts", "trajectory_id"), ("check_facts", "trajectory_id"),
                                  ("case_supports", "supporting_trajectory_id")):
                db.execute(f"DELETE FROM {table} WHERE {column} IN ({tmarks})", trajectories)
    progress.write_text("".join(r + "\n" for r in keep), encoding="utf-8")
    for src, dst in moves:
        src.rename(dst)
    print(f"done; backups end in -{stamp}")


if __name__ == "__main__":
    main()
