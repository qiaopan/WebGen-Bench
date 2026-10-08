#!/usr/bin/env python3
"""Flag infrastructure failures that the shared parsers would record as ordinary model results
(both have happened on the cluster), so they can be re-run later:

- the functional evaluator never answered (e.g. 401), which the parser scores as "failed";
- build repairs that never got a reply (Bolt's context step failing), scored as a build failure;
- a screenshot whose appearance grade could not be read (Qwen-VL answer format);
- no progress record (the runner crashed on this task).

The queue keeps running (a stopped Slurm job loses its GPU). Only problems that would write wrong
lessons into Long Memory are blocking, and only for the continual arm. Every finding is appended to
OUTPUT_DIR/health-warnings.jsonl.

Usage: check_task_health.py OUTPUT_DIR TASK_ID MODE
Exit: 2 only for a blocking problem in Long Memory (it would poison the memory chain); 0 otherwise,
including warnings, which are printed as HEALTH_WARN and logged.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def chat_messages(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("messages", []) if isinstance(data, dict) else data


def main() -> int:
    output, task_id, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    task_dir = output / "tasks" / task_id / mode
    warnings: list[str] = []
    poisoning: list[str] = []  # wrong outcomes that reflection would turn into lessons
    record = None
    progress = output / "progress.jsonl"
    for line in (progress.read_text(encoding="utf-8").splitlines() if progress.is_file() else []):
        row = json.loads(line)
        if row.get("task_id") == task_id and row.get("mode") == mode:
            record = row
    if record is None:
        warnings.append("no progress record (runner crashed on this task)")
    else:
        checks = record.get("evaluation") or []
        generation_failed = bool(record.get("generation_failed")) or any(
            c.get("failure_type") == "generation_failed" for c in checks)
        if generation_failed:
            chat = task_dir / "000001.failed-chat.json"
            if chat.is_file():
                roles = [m.get("role") for m in chat_messages(chat)]
                # After the first assistant answer, every repair request should get an assistant reply.
                tail = roles[roles.index("assistant"):] if "assistant" in roles else roles
                if any(a == "user" and b == "user" for a, b in zip(tail, tail[1:])):
                    poisoning.append("build repair requests got no reply (consecutive user messages in the chat)")
        else:
            functional = [c for c in checks if c.get("check") != "appearance"]
            unreached = [c for c in functional if c.get("failure_type") == "start_failed"]
            if unreached:  # a model outcome under the official protocol, but worth seeing in the log
                print(f"NOTE {task_id} {mode}: {len(unreached)}/{len(functional)} checks never reached the site")
            services = task_dir / "extracted" / "services.json"
            if (functional and len(unreached) == len(functional) and services.is_file()
                    and not json.loads(services.read_text(encoding="utf-8") or "{}")):
                # The validator saw the dev server start, yet the evaluator found no port in PM2's log:
                # on 2026-10-05 this was the evaluators reading ~/.pm2 while the job used its own PM2_HOME.
                poisoning.append("no port detected for a site the validator saw start (check PM2 logs)")
            results = sorted((task_dir / "extracted" / "results").glob("*/interact_messages.json"))
            if not results and len(unreached) < len(functional):
                poisoning.append("no functional evaluator transcripts")
            for path in results:
                if not any(m.get("role") == "assistant" for m in json.loads(path.read_text(encoding="utf-8"))):
                    poisoning.append(f"functional evaluator never answered: {path.parent.name}")
            # No screenshot means the page body had no height (blank page, e.g. a Vite error overlay):
            # the official grader skips it and counts 0, a model outcome. A screenshot whose grade
            # cannot be read is ours to fix (answer format).
            appearance = [c for c in checks if c.get("check") == "appearance"]
            shots = list((task_dir / "extracted" / "000001" / "shots").glob("*.png"))
            if shots and (not appearance or appearance[0].get("score") is None):
                warnings.append("appearance grade missing or unreadable although a screenshot exists")
            elif not shots and len(unreached) < len(functional):
                print(f"NOTE {task_id} {mode}: no screenshot (blank page); appearance counts 0 as in the official grader")
    findings = [("block", p) for p in poisoning] + [("warn", w) for w in warnings]
    if findings:
        with (output / "health-warnings.jsonl").open("a", encoding="utf-8") as stream:
            for level, text in findings:
                stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "task_id": task_id,
                                         "mode": mode, "level": level, "problem": text}) + "\n")
    for level, text in findings:
        print(f"HEALTH_{'BLOCK' if level == 'block' and mode == 'continual' else 'WARN'} {task_id} {mode}: {text}")
    if not findings:
        print(f"HEALTH_OK {task_id} {mode}")
    # Nonzero only when the queue must stop; warnings are in the log and health-warnings.jsonl.
    return 2 if poisoning and mode == "continual" else 0


if __name__ == "__main__":
    raise SystemExit(main())
