#!/usr/bin/env python3
"""Fill appearance `score` left empty by the old grade regex (see DECISIONS.md, 2026-10-01).

Only records with check == "appearance", score None, and a readable grade in their
model_output (or the result.json named by `evidence`) are changed. Every touched file
is backed up as <name>.before-grade-backfill first.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from pathlib import Path

GRADE_RE = re.compile(r"Grade\W{0,6}?:\W{0,6}([1-5])", re.IGNORECASE)
BACKUP_SUFFIX = ".before-grade-backfill"


def _grade(record: dict) -> int | None:
    text = record.get("model_output")
    if not text and record.get("evidence") and Path(record["evidence"]).is_file():
        text = json.loads(Path(record["evidence"]).read_text(encoding="utf-8")).get("model_output")
    match = GRADE_RE.search(text or "")
    return int(match.group(1)) if match else None


def _fix(value) -> int:
    """Patch appearance records in place; return how many were filled."""
    if isinstance(value, list):
        return sum(_fix(item) for item in value)
    if not isinstance(value, dict):
        return 0
    count = sum(_fix(item) for item in value.values())
    if value.get("check") == "appearance" and value.get("score") is None:
        grade = _grade(value)
        if grade is not None:
            value["score"] = grade
            if grade < 5:
                value["failure_stage"] = "appearance"
                value["failure_type"] = "appearance_quality_issue"
                value["failure_reason"] = "外观评分低于满分；具体分析保留在 model_output 中"
            count += 1
    return count


def _backup(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)


def fix_json(path: Path, dry: bool) -> int:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        count = _fix(rows)
        new = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    else:
        data = json.loads(text)
        count = _fix(data)
        new = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if count and not dry:
        _backup(path)
        path.write_text(new, encoding="utf-8")
    return count


def fix_db(path: Path, dry: bool) -> int:
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT trajectory_id, evaluation_results FROM trajectories "
                          "WHERE evaluation_results LIKE '%appearance%'").fetchall()
        updates = []
        for trajectory_id, raw in rows:
            data = json.loads(raw)
            if _fix(data):
                updates.append((json.dumps(data, ensure_ascii=False), trajectory_id))
        if updates and not dry:
            _backup(path)
            db.executemany("UPDATE trajectories SET evaluation_results = ? WHERE trajectory_id = ?",
                           updates)
    return len(updates)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    total = 0
    for root in args.roots:
        for path in sorted(root.rglob("*")):
            if BACKUP_SUFFIX in path.name or not path.is_file():
                continue
            if path.name in ("progress.jsonl", "continual-report.json"):
                count = fix_json(path, args.dry_run)
            elif path.name == "memory.db":
                count = fix_db(path, args.dry_run)
            else:
                continue
            if count:
                print(f"{count:3d}  {path}")
                total += count
    print(f"total filled: {total}{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
