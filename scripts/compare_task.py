#!/usr/bin/env python3
"""One-task comparison: No Memory, Long Memory (condensed), and the uncondensed Long Memory run when
one was archived before the condense rerun. Paper convention: accuracy = (Yes + 0.5*Partial)/checks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1] / "outputs" / "experiment"
NOMEM = EXP / "nomem_14_21_webgenlm_qwenvl_gpt4o_r2"
LONGMEM = EXP / "longmem_mac_q8_19_21_then_remaining_r1"


def _record(progress: Path, task_id: str) -> dict | None:
    if not progress.is_file():
        return None
    found = [json.loads(line) for line in progress.read_text().splitlines()
             if line.strip() and json.loads(line).get("task_id") == task_id]
    return found[-1] if found else None


def _uncondensed(task_id: str) -> tuple[dict | None, Path | None]:
    for backup in sorted(LONGMEM.glob("progress.jsonl.before-condense-rerun-*")):
        record = _record(backup, task_id)
        if record:
            return record, LONGMEM / "tasks" / f"{task_id}.pre-condense-backup" / "continual"
    return None, None


def _row(name: str, record: dict | None, task_dir: Path | None) -> str:
    if record is None:
        return f"| {name} | not run | | | | | |"
    checks = [e for e in record.get("evaluation", []) if e.get("check") != "appearance"]
    yes = sum(e.get("outcome") == "passed" for e in checks)
    partial = sum(e.get("outcome") == "partial" for e in checks)
    no = len(checks) - yes - partial
    appearance = next((e.get("score") for e in record.get("evaluation", []) if e.get("check") == "appearance"), None)
    if record.get("generation_failed") or not checks:
        return f"| {name} | start failed | | | {appearance} | | |"
    accuracy = (yes + 0.5 * partial) / len(checks)
    prompt = task_dir / "000001.prompt.txt" if task_dir else None
    generation = task_dir / "000001.generation.json" if task_dir else None
    prompt_chars = len(prompt.read_text()) if prompt and prompt.is_file() else ""
    attempts = (len(json.loads(generation.read_text()).get("attempts", []))
                if generation and generation.is_file() else "")
    return (f"| {name} | {yes}/{partial}/{no} | {accuracy:.2f} | {len(checks)} | {appearance} | "
            f"{attempts} | {prompt_chars} |")


def main() -> None:
    task_id = sys.argv[1]
    rows = [_row("No Memory", _record(NOMEM / "progress.jsonl", task_id), NOMEM / "tasks" / task_id / "disabled"),
            _row("Long Memory (condensed)", _record(LONGMEM / "progress.jsonl", task_id),
                 LONGMEM / "tasks" / task_id / "continual")]
    old, old_dir = _uncondensed(task_id)
    if old:
        rows.append(_row("Long Memory (uncondensed)", old, old_dir))
    print(f"TABLE {task_id}")
    print("| arm | Yes/Partial/No | accuracy | checks | appearance | build attempts | prompt chars |")
    print("|---|---|---|---|---|---|---|")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
