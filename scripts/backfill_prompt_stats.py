#!/usr/bin/env python3
"""Fill run_facts.prompt_stats for runs recorded before it existed, and write one analysis row per
trajectory (archived reruns included) with its injected-memory size and accuracy.

The prompt comes from the trajectory's own run_config.generation_prompt; the condense numbers come
from the case_retrieval event whose rendered memory appears in that prompt. Only empty prompt_stats
are filled. Paper convention: accuracy = (Yes + 0.5*Partial) / functional checks.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from long_memory import connect_database, ensure_optional_tables  # noqa: E402
from memory_statistics import prompt_stats  # noqa: E402


def _condense_events(output: Path) -> list[dict]:
    path = output / "memory-events.jsonl"
    if not path.is_file():
        return []
    return [event for event in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                                if '"case_retrieval"' in line)
            if event.get("operation") == "case_retrieval"]


def _stats(prompt: str, requirement: str, events: list[dict]) -> dict:
    condense = next((e.get("guidance_condense") for e in reversed(events)
                     if e.get("task") == requirement and e.get("rendered_memory")
                     and str(e["rendered_memory"]).strip() in prompt), None)
    return prompt_stats(prompt, requirement, condense)


def _accuracy(evaluation: list) -> tuple[float | None, int | None]:
    checks = [e for e in evaluation if isinstance(e, dict) and e.get("check") != "appearance"]
    appearance = next((e.get("score") for e in evaluation
                       if isinstance(e, dict) and e.get("check") == "appearance"), None)
    if not checks:
        return None, appearance
    yes = sum(e.get("outcome") == "passed" for e in checks)
    partial = sum(e.get("outcome") == "partial" for e in checks)
    return round((yes + 0.5 * partial) / len(checks), 3), appearance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outputs", nargs="+", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for output in args.outputs:
        database = output / "memory.db"
        events = _condense_events(output)
        shutil.copy2(database, database.with_name(f"memory.db.before-prompt-stats-{time.strftime('%Y%m%d-%H%M%S')}"))
        with connect_database(database, read_only=False) as connection:
            ensure_optional_tables(connection)
            trajectories = connection.execute(
                "SELECT trajectory_id, task_id, attempt_no, run_status, task_request, run_config, "
                "evaluation_results FROM trajectories ORDER BY task_id, attempt_no").fetchall()
            filled = 0
            for tid, task_id, attempt, status, requirement, run_config, evaluation in trajectories:
                prompt = json.loads(run_config).get("generation_prompt") or ""
                if not prompt:
                    continue
                stats = _stats(prompt, requirement, events)
                filled += connection.execute(
                    "UPDATE run_facts SET prompt_stats=? WHERE trajectory_id=? AND prompt_stats='{}'",
                    (json.dumps(stats, ensure_ascii=False), tid)).rowcount
                active = connection.execute("SELECT COUNT(*) FROM run_facts WHERE trajectory_id=?",
                                            (tid,)).fetchone()[0] > 0
                accuracy, appearance = _accuracy(json.loads(evaluation or "[]"))
                condense = stats.get("condense") or {}
                rows.append({"output": output.name, "task_id": task_id, "attempt": attempt, "status": status,
                             "current": active, "condensed": bool(condense.get("applied")),
                             "requirement_chars": stats["requirement_chars"], "memory_chars": stats["memory_chars"],
                             "memory_ratio": stats["memory_ratio"], "memory_items": stats["memory_items"],
                             "condense_candidates": condense.get("candidates"),
                             "accuracy": accuracy, "appearance": appearance})
        print(f"{output.name}: filled {filled} run_facts rows")
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.csv}")


if __name__ == "__main__":
    main()
