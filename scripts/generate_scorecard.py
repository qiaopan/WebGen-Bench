#!/usr/bin/env python3
"""Summarise per-task functional/appearance outcomes from two progress.jsonl
files (one No Memory run, one Long Memory run) side by side, for a given set
of shared task IDs. Read-only: never mutates progress.jsonl or memory.db.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

GRADE_RE = re.compile(r"Grade.*?(\d)", re.IGNORECASE | re.DOTALL)


def load_events(path: Path) -> dict[str, dict]:
    events: dict[str, dict] = {}
    if not path.exists():
        return events
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        task_id = record.get("task_id")
        if task_id:
            events[task_id] = record
    return events


def summarise(record: dict | None) -> dict:
    if record is None or record.get("status") != "complete":
        return {"passed": None, "partial": None, "failed": None, "appearance": None}
    if record.get("generation_failed"):
        return {"passed": None, "partial": None, "failed": None, "appearance": None, "start_failed": True}
    passed = partial = failed = 0
    appearance = None
    for entry in record.get("evaluation", []):
        if entry.get("check") == "appearance":
            match = GRADE_RE.search(entry.get("model_output", "") or "")
            if match:
                appearance = int(match.group(1))
            continue
        outcome = entry.get("outcome")
        if outcome == "passed":
            passed += 1
        elif outcome == "partial":
            partial += 1
        elif outcome == "failed":
            failed += 1
    return {"passed": passed, "partial": partial, "failed": failed, "appearance": appearance}


def fmt(summary: dict) -> str:
    if summary.get("start_failed"):
        return "START FAILED (excluded from accuracy, paper convention)"
    if summary["passed"] is None:
        return "not run"
    n = summary['passed'] + summary['partial'] + summary['failed']
    acc = (summary['passed'] + 0.5 * summary['partial']) / n if n else 0.0
    return (f"{summary['passed']} Yes / {summary['partial']} Partial / {summary['failed']} No, "
            f"accuracy={acc:.2f}, appearance={summary['appearance']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nomem-progress", type=Path, required=True)
    parser.add_argument("--longmem-progress", type=Path, required=True)
    parser.add_argument("--task-ids", required=True, help="Comma-separated task IDs")
    parser.add_argument("--out", type=Path, default=None, help="Optional path to also write the table as Markdown")
    args = parser.parse_args()

    task_ids = [t.strip() for t in args.task_ids.split(",") if t.strip()]
    nomem_events = load_events(args.nomem_progress)
    longmem_events = load_events(args.longmem_progress)

    lines = []
    lines.append("| task | No Memory (functional / appearance) | Long Memory (functional / appearance) |")
    lines.append("|---|---|---|")

    totals = {
        "nomem": {"passed": 0, "partial": 0, "failed": 0, "appearance_sum": 0, "appearance_n": 0, "start_failed": 0},
        "longmem": {"passed": 0, "partial": 0, "failed": 0, "appearance_sum": 0, "appearance_n": 0, "start_failed": 0},
    }

    for task_id in task_ids:
        nomem_summary = summarise(nomem_events.get(task_id))
        longmem_summary = summarise(longmem_events.get(task_id))
        lines.append(f"| {task_id} | {fmt(nomem_summary)} | {fmt(longmem_summary)} |")
        for key, summary in (("nomem", nomem_summary), ("longmem", longmem_summary)):
            if summary.get("start_failed"):
                totals[key]["start_failed"] += 1
                continue
            if summary["passed"] is None:
                continue
            totals[key]["passed"] += summary["passed"]
            totals[key]["partial"] += summary["partial"]
            totals[key]["failed"] += summary["failed"]
            if summary["appearance"] is not None:
                totals[key]["appearance_sum"] += summary["appearance"]
                totals[key]["appearance_n"] += 1

    def total_line(key: str) -> str:
        t = totals[key]
        avg = (t["appearance_sum"] / t["appearance_n"]) if t["appearance_n"] else None
        avg_str = f"{avg:.2f}" if avg is not None else "n/a"
        n = t['passed'] + t['partial'] + t['failed']
        acc = f"{(t['passed'] + 0.5 * t['partial']) / n:.3f}" if n else "n/a"
        return (f"{t['passed']} Yes / {t['partial']} Partial / {t['failed']} No, accuracy={acc}, "
                f"start failed={t['start_failed']}, appearance avg={avg_str} (n={t['appearance_n']})")

    lines.append("")
    lines.append(f"**No Memory totals:** {total_line('nomem')}")
    lines.append(f"**Long Memory totals:** {total_line('longmem')}")

    output = "\n".join(lines)
    print(output)
    if args.out:
        args.out.write_text(output + "\n")


if __name__ == "__main__":
    main()
