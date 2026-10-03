#!/usr/bin/env python3
"""Finish the post-evaluation steps of one Long Memory (case_only) task whose run crashed after its
cases were stored: experience-candidate review, statistics, and the progress event.

Nothing is regenerated or re-evaluated. Generation, evaluation, trajectory, reflection and stored
cases are read from what the crashed run already wrote; the memory packet used for the prompt is
rebuilt from that run's ``case_retrieval`` log entry.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_continual_memory as rcm  # noqa: E402
from run_continual_memory import (AzureEmbedder, AzureMemoryLLM, CasePacket, ReflectionCaseMemory,  # noqa: E402
                                  RetrievedCase, append_event, connect_database, evaluations,
                                  guidance_run_info, load_long_memory_settings, prompt_delivered,
                                  record_statistics)

MANIFEST = rcm.ROOT / "data" / "experiment_splits" / "continual_domain_blocks" / "manifest.json"


def last(path: Path, predicate) -> dict:
    found = [row for row in (json.loads(line) for line in path.read_text().splitlines() if line.strip())
             if predicate(row)]
    if not found:
        raise SystemExit(f"nothing matching in {path}")
    return found[-1]


def load_context(output: Path, task_id: str) -> dict:
    """Everything a post-task step needs, rebuilt from the run's own artifacts and logs."""
    database, destination = output / "memory.db", output / "tasks" / task_id / "continual"
    task = json.loads((output / "tasks" / task_id / "task.jsonl").read_text().splitlines()[0])
    manifest = json.loads(MANIFEST.read_text())
    batch_number = next(i for i, b in enumerate(manifest["batches"], start=1) if task_id in b["task_ids"])
    with connect_database(database, read_only=True) as connection:
        # A rerun keeps the earlier attempt as provenance; post-task steps act on the latest one.
        rows = connection.execute("SELECT trajectory_id FROM trajectories WHERE task_id=? AND "
                                  "run_status='completed' ORDER BY attempt_no DESC LIMIT 1",
                                  (task_id,)).fetchall()
    if not rows:
        raise SystemExit(f"no completed trajectory for {task_id}")

    retrieval = last(output / "memory-events.jsonl",
                     lambda e: e.get("operation") == "case_retrieval" and e.get("task") == task["instruction"])
    patterns = {a["case_id"]: a["implementation_pattern"] for a in retrieval.get("implementation_adaptations", [])
                if isinstance(a, dict) and a.get("applicable") and a.get("implementation_pattern")}
    common = retrieval.get("common_pool", {}).get("patterns", [])
    packet = CasePacket(
        tuple(RetrievedCase(cid, {"implementation_pattern": patterns.get(cid, "")}, 0.0)
              for cid in retrieval.get("selected", [])),
        common=tuple(p["implementation_pattern"] for p in common),
        common_case_ids=tuple(dict.fromkeys(c for p in common for c in p.get("source_case_ids", []))))

    rcm.load_dotenv(rcm.ROOT / ".env")
    settings = load_long_memory_settings(rcm.ROOT / "config" / "long_memory.json")
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    client = rcm.OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                        base_url=os.environ.get("WEBGEN_MEMORY_BASE_URL") or f"{endpoint}/openai/v1",
                        timeout=120, max_retries=2)
    result = {"zip_path": str(destination / "000001.zip"), "chat_path": str(destination / "000001.json"),
              "prompt_path": str(destination / "000001.prompt.txt")}
    return {"task": task, "batch_number": batch_number, "trajectory_id": rows[0]["trajectory_id"],
            "packet": packet, "settings": settings, "database": database, "destination": destination,
            "llm": AzureMemoryLLM(client, settings.memory_llm["deployment"],
                                  max_tokens=settings.memory_llm["max_completion_tokens"]),
            "embedder": AzureEmbedder(client, settings.embedding["deployment"],
                                      dimensions=settings.embedding["dimensions"]),
            "log": rcm.JsonlRunLog(output / "memory-events.jsonl"),
            "evaluation": evaluations(destination, 1), "prompt_delivered": prompt_delivered(result),
            "connect": lambda path: rcm.connect_database(path, read_only=False)}


def case_memory(ctx: dict) -> ReflectionCaseMemory:
    return ReflectionCaseMemory(str(ctx["database"]), "bolt", llm=ctx["llm"], embedder=ctx["embedder"],
                                config=ctx["settings"].memory, log=ctx["log"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    output, task_id, mode = args.output.resolve(), args.task_id, "continual"
    progress = output / "progress.jsonl"
    if any(json.loads(l).get("task_id") == task_id for l in progress.read_text().splitlines() if l.strip()):
        raise SystemExit(f"{task_id} already has a progress event")
    ctx = load_context(output, task_id)
    trajectory_id = ctx["trajectory_id"]
    store = last(output / "memory-events.jsonl",
                 lambda e: e.get("operation") == "case_store" and e.get("trajectory_id") == trajectory_id)
    reflection = last(output / "post-task-reflections.jsonl", lambda r: r.get("trajectory_id") == trajectory_id)

    event = {"key": f"batch:{ctx['batch_number']}:task:{task_id}:{mode}", "status": "complete",
             "batch": ctx["batch_number"], "task_id": task_id, "mode": mode, "evaluation": ctx["evaluation"],
             "prompt_delivered": ctx["prompt_delivered"], "reflection_id": reflection["reflection_id"],
             "accepted_reflection_count": reflection["accepted_reflection_count"],
             "raw_reflection_count": reflection["raw_reflection_count"],
             "reflection_count": reflection["accepted_reflection_count"],
             "case_ids": store["case_ids"], "finished_by": "scripts/finish_post_task.py"}
    with case_memory(ctx) as memory:
        event["consolidation_review"] = memory.review_recurring_failures(event["case_ids"])
        event["experience_candidate_record_id"] = memory.persist_experience_candidate(event["consolidation_review"])

    failed_items = [item for item in [*reflection.get("functional_reflections", []),
                                      reflection.get("implementation_reflection")]
                    if isinstance(item, dict) and item.get("outcome") != "success"]
    zip_path = str(ctx["destination"] / "000001.zip")
    adapter = type("ReplayedAdapter", (), {"last_memory": ctx["packet"]})()
    record_statistics(ctx["database"], ctx["llm"], ctx["task"], trajectory_id, zip_path, ctx["evaluation"],
                      [str(item.get("likely_cause_or_limitation", "")) for item in failed_items],
                      ctx["destination"], generation_ok=True,
                      guidance=guidance_run_info(ctx["llm"], adapter, zip_path, ctx["prompt_delivered"]),
                      cases=failed_items)
    event.update({"trajectory_id": trajectory_id, "candidate_refs": []})
    append_event(progress, event)
    print(json.dumps({k: event[k] for k in ("key", "trajectory_id", "experience_candidate_record_id",
                                            "prompt_delivered", "case_ids")}, indent=2))


if __name__ == "__main__":
    main()
