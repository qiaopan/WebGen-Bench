#!/usr/bin/env python3
"""Compare automatic case retrieval with the reviewed/manual case source.

This is read-only: it never calls an LLM and never changes a database.  It is
intended for the 000014--000017 alignment audit before enabling automatic
retrieval in an experiment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_RUNS = {
    "000014": "outputs/experiment/confirmed_000014_aspect_gate_r1/memory-events.jsonl",
    "000015": "outputs/experiment/golden_source_000015_impl_r1/memory-events.jsonl",
    "000016": "outputs/experiment/confirmed_000016_prompt_audit_r1/memory-events.jsonl",
    "000017": "outputs/experiment/confirmed_000017_prompt_audit_r1/memory-events.jsonl",
}


def load_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="*", default=[],
                        help="task_id=memory-events.jsonl entries")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    runs = dict(DEFAULT_RUNS)
    for item in args.runs:
        task_id, path = item.split("=", 1)
        runs[task_id] = path
    report = []
    for task_id, raw_path in sorted(runs.items()):
        events = load_events(Path(raw_path))
        retrievals = [e for e in events if e.get("operation") == "case_retrieval"]
        latest = retrievals[-1] if retrievals else None
        report.append({
            "task_id": task_id,
            "run_events": raw_path,
            "automatic_retrieval_found": bool(latest),
            "selected_case_ids": (latest or {}).get("selected", []),
            "decisions": (latest or {}).get("decisions_by_channel", {}),
            "candidate_counts": {
                channel: sum(len(group) for group in groups)
                for channel, groups in (latest or {}).get("candidates_by_channel", {}).items()
            },
            "implementation_adaptations": (latest or {}).get("implementation_adaptations", []),
            "note": "Compare selected_case_ids with the manually reviewed case list for this task; this script does not infer human labels.",
        })
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    for item in report:
        print(f"\nTask {item['task_id']}  source={item['run_events']}")
        print(f"  automatic retrieval: {'yes' if item['automatic_retrieval_found'] else 'no'}")
        print(f"  selected cases: {', '.join(item['selected_case_ids']) or '(none)'}")
        print(f"  candidate counts: {item['candidate_counts']}")
        print("  manual comparison: fill from the reviewed case list; no labels are inferred automatically")


if __name__ == "__main__":
    main()
