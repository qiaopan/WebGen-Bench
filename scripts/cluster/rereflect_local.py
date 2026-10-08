#!/usr/bin/env python3
"""Re-run the post-task reflection for finished Long Memory tasks with the CURRENT local reflection code,
against a pulled copy of a cluster run, and print the lessons. Nothing is written to any database; the
reflections go to --out (JSONL) for comparison with the stored ones.

For trying reflection-prompt or evidence changes before they reach the cluster. The memory model is
reached through an SSH tunnel to a running cluster job (it must be the job's own service, never another
user's), e.g. `ssh -O forward -L 28440:127.0.0.1:28440 csml3` for the Long Memory job (port offset 20).

Usage: rereflect_local.py OUTPUT_DIR TASK_ID [TASK_ID ...] --base-url http://127.0.0.1:28440/v1
       --key-file FILE [--out FILE] [--config config/long_memory_cluster.json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "src" / "automatic_bolt_diy")]

from openai import OpenAI  # noqa: E402

from long_memory_integrations import (case_reflection_evidence, earlier_trajectories,  # noqa: E402
                                      memory_llm_from_settings, setup_history)
from long_memory_settings import load_long_memory_settings  # noqa: E402
from post_task_reflection import create_reflection, prompt_version  # noqa: E402

CLUSTER_ROOT = "/data/qma258/webgen/"


def localise(row: dict) -> dict:
    """Point the cluster paths stored in a trajectory at the pulled copy on this machine."""
    return {key: value.replace(CLUSTER_ROOT, str(ROOT) + "/") if isinstance(value, str) else value
            for key, value in row.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("task_ids", nargs="+")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "long_memory_cluster.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--model", help="override the reflection model (prompt tuning only; never for stored memory)")
    args = parser.parse_args()
    if "azure" in args.base_url.lower():
        raise SystemExit("WebGen cluster runs must not call Azure")
    settings = load_long_memory_settings(args.config)
    client = OpenAI(base_url=args.base_url, api_key=args.key_file.read_text().strip(), timeout=600)
    llm = memory_llm_from_settings(client, {**settings.reflection_llm, **({"deployment": args.model} if args.model else {})})
    db = sqlite3.connect(f"file:{args.output / 'memory.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out = args.out or args.output / f"rereflect-{prompt_version()}.jsonl"
    for task_id in args.task_ids:
        row = db.execute("SELECT * FROM trajectories WHERE task_id=? ORDER BY rowid DESC LIMIT 1",
                         (task_id,)).fetchone()
        if row is None:
            print(f"{task_id}: no trajectory"); continue
        source = localise(dict(row))
        history = setup_history([localise(t) for t in earlier_trajectories(db, source)])
        reflection = create_reflection(llm, source, case_reflection_evidence(source),
                                       review=settings.memory.post_task_case_review,
                                       style=settings.memory.reflection_style,
                                       appearance_mode=settings.memory.appearance_reflection,
                                       setup_history=history)
        with out.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"task_id": task_id, **reflection}, ensure_ascii=False, default=str) + "\n")
        print(f"== {task_id} (prompt {reflection.get('prompt_version')}, context trims {llm.context_trims})")
        for item in [*reflection.get("functional_reflections", []), reflection.get("implementation_reflection")]:
            if not isinstance(item, dict):
                continue
            print(f"- [{item.get('cause_confidence', '-')}/{item.get('scope', '-')}] {item.get('feature_object', '')[:70]}")
            print(f"    cause:  {item.get('likely_cause_or_limitation', '')[:240]}")
            print(f"    action: {item.get('preventative_action', '')[:300]}")
        llm.context_trims.clear()
    print(f"written to {out}")


if __name__ == "__main__":
    main()
