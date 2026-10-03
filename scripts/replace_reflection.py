#!/usr/bin/env python3
"""Replace one Long Memory (case_only) task's stored reflection with a newly generated one.

Generation and evaluation are untouched. Archives the task's current cases and removes its other reflection-derived rows (case
supports, statistics facts), stores the new reflection,
re-runs the candidate review and statistics, and updates the task's progress event. The database is
copied before any change.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finish_post_task as fpt  # noqa: E402
from run_continual_memory import append_reflection, guidance_run_info, record_statistics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--reflection", type=Path, required=True, help="JSON from create_reflection")
    args = parser.parse_args()
    output, task_id = args.output.resolve(), args.task_id
    database, destination = output / "memory.db", output / "tasks" / task_id / "continual"
    backup = database.with_name(f"memory.db.before-replace-reflection-{task_id}-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(database, backup)

    reflection = json.loads(args.reflection.read_text())
    ctx = fpt.load_context(output, task_id)
    trajectory_id = ctx["trajectory_id"]
    if reflection.get("trajectory_id") != trajectory_id:
        raise SystemExit("reflection belongs to a different trajectory")

    connection = ctx["connect"](database)
    with connection:
        old_cases = [r[0] for r in connection.execute(
            "SELECT case_id FROM reflection_cases WHERE trajectory_id=?", (trajectory_id,))]
        marks = ",".join("?" for _ in old_cases) or "''"
        removed = {
            "case_supports": connection.execute(
                f"DELETE FROM case_supports WHERE supporting_trajectory_id=? OR supported_case_id IN ({marks})",
                (trajectory_id, *old_cases)).rowcount,

            "check_facts": connection.execute("DELETE FROM check_facts WHERE trajectory_id=?", (trajectory_id,)).rowcount,
            "run_facts": connection.execute("DELETE FROM run_facts WHERE trajectory_id=?", (trajectory_id,)).rowcount,
            # Provenance (memory_sources) is append-only and later tasks may already cite these cases,
            # so the replaced cases are archived (kept, never retrieved) rather than deleted.
            "reflection_cases_archived": connection.execute(
                "UPDATE reflection_cases SET status='archived' WHERE trajectory_id=? AND status<>'archived'",
                (trajectory_id,)).rowcount,
        }
    connection.close()

    reflection["replaces_previous_reflection"] = True
    append_reflection(output / "post-task-reflections.jsonl", reflection)
    with fpt.case_memory(ctx) as memory:
        case_ids = memory.store(reflection)
        review = memory.review_recurring_failures(case_ids)
        candidate = memory.persist_experience_candidate(review)

    failed_items = [item for item in [*reflection.get("functional_reflections", []),
                                      reflection.get("implementation_reflection")]
                    if isinstance(item, dict) and item.get("outcome") != "success"]
    adapter = type("ReplayedAdapter", (), {"last_memory": ctx["packet"]})()
    zip_path = str(destination / "000001.zip")
    record_statistics(database, ctx["llm"], ctx["task"], trajectory_id, zip_path, ctx["evaluation"],
                      [str(item.get("likely_cause_or_limitation", "")) for item in failed_items],
                      destination, generation_ok=True,
                      guidance=guidance_run_info(ctx["llm"], adapter, zip_path, ctx["prompt_delivered"]),
                      cases=failed_items)

    progress = output / "progress.jsonl"
    lines = []
    for line in progress.read_text().splitlines():
        event = json.loads(line)
        if event.get("task_id") == task_id:
            event.update({"reflection_id": reflection["reflection_id"], "case_ids": case_ids,
                          "accepted_reflection_count": reflection["accepted_reflection_count"],
                          "raw_reflection_count": reflection["raw_reflection_count"],
                          "consolidation_review": review, "experience_candidate_record_id": candidate,
                          "reflection_replaced": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        lines.append(json.dumps(event, ensure_ascii=False))
    progress.write_text("\n".join(lines) + "\n")
    print(json.dumps({"backup": str(backup), "removed": removed, "new_case_ids": case_ids,
                      "candidate": candidate}, indent=2))


if __name__ == "__main__":
    main()
