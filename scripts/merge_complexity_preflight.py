#!/usr/bin/env python3
"""Merge ordered LLM-only complexity preflight reports into one audited report."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, required=True,
                        help="Full task JSONL, used for order and completeness checks")
    parser.add_argument("--reports", type=Path, nargs="+", required=True,
                        help="Preflight JSON reports in oldest-to-newest order")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    task_ids = [str(json.loads(line)["id"]) for line in args.tasks.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    latest: dict[str, dict] = {}
    for path in args.reports:
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("rows", []):
            latest[str(row["task_id"])] = row
    missing = [task_id for task_id in task_ids if task_id not in latest]
    if missing:
        raise ValueError("Reports do not cover: " + ", ".join(missing))
    rows = [{**latest[task_id], "position": position}
            for position, task_id in enumerate(task_ids, start=1)]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "complexity-preflight-final.json").write_text(
        json.dumps({"source_reports": [str(path.resolve()) for path in args.reports],
                    "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ("position", "task_id", "application_type", "primary_category", "complexity",
              "retrieval_strategy", "complexity_reason", "aspects")
    with (args.output / "complexity-preflight-final.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "aspects": " | ".join(row.get("aspects", []))})
    counts = Counter(row["complexity"] for row in rows)
    print("[merge] complete: " + ", ".join(
        f"{label}={counts[label]}" for label in ("simple", "medium", "complex")))


if __name__ == "__main__":
    main()
