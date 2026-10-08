#!/usr/bin/env python3
"""Compute automatic-retrieval hit ratio against reviewed case IDs.

Input JSON format:
{
  "000014": ["case-id-a", "case-id-b"],
  "000015": ["case-id-c"]
}

The script only reads JSONL logs and never calls an LLM or writes a database.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def selected_case_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    selected: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("operation") != "case_retrieval":
            continue
        selected = {str(value) for value in event.get("selected", [])}
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", type=Path, required=True,
                        help="JSON mapping task_id -> reviewed case IDs")
    parser.add_argument("--auto", nargs="+", metavar="TASK_ID=EVENTS_JSONL",
                        required=True)
    args = parser.parse_args()
    manual = json.loads(args.manual.read_text(encoding="utf-8"))
    total = hit = 0
    for entry in args.auto:
        task_id, raw_path = entry.split("=", 1)
        reviewed = {str(value) for value in manual.get(task_id, [])}
        automatic = selected_case_ids(Path(raw_path))
        intersection = reviewed & automatic
        total += len(reviewed)
        hit += len(intersection)
        ratio = len(intersection) / len(reviewed) if reviewed else 0.0
        print(json.dumps({"task_id": task_id, "reviewed": sorted(reviewed),
                          "automatic": sorted(automatic),
                          "intersection": sorted(intersection),
                          "hit_ratio": round(ratio, 4)}, ensure_ascii=False))
    print(json.dumps({"reviewed_case_count": total, "hit_case_count": hit,
                      "overall_hit_ratio": round(hit / total, 4) if total else 0.0},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
