#!/usr/bin/env python3
"""Store re-run reflections (from rereflect_local.py) into a COPY of a Long Memory database, replacing the
cases the same trajectories stored before (archived, as in a re-run). For previewing the guidance later
tasks would get; never point it at a chain's own memory.db.

Usage: store_reflections_copy.py REFLECTIONS.jsonl DB_COPY --memory-url URL --memory-key-file FILE
       --embedding-url URL --embedding-key-file FILE [--config config/long_memory_cluster.json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src")]

from openai import OpenAI  # noqa: E402

from long_memory_integrations import AzureEmbedder, memory_llm_from_settings  # noqa: E402
from long_memory_runtime import JsonlRunLog  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reflections", type=Path)
    parser.add_argument("db_copy", type=Path)
    parser.add_argument("--memory-url", required=True)
    parser.add_argument("--memory-key-file", type=Path, required=True)
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--embedding-key-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "long_memory_cluster.json")
    args = parser.parse_args()
    if args.db_copy.name == "memory.db" or "azure" in (args.embedding_url + args.memory_url).lower():
        raise SystemExit("use a copy of memory.db (not the chain's own file) and a self-hosted embedder")
    settings = load_long_memory_settings(args.config)
    client = OpenAI(base_url=args.embedding_url, api_key=args.embedding_key_file.read_text().strip(), timeout=120)
    embedder = AzureEmbedder(client, settings.embedding["deployment"], dimensions=settings.embedding["dimensions"])
    llm = memory_llm_from_settings(OpenAI(base_url=args.memory_url, timeout=600,
                                          api_key=args.memory_key_file.read_text().strip()), settings.memory_llm)
    reflections = [json.loads(line) for line in args.reflections.read_text().splitlines() if line.strip()]
    with sqlite3.connect(args.db_copy) as db:
        for reflection in reflections:
            archived = db.execute("UPDATE reflection_cases SET status='archived' WHERE status='active' AND trajectory_id=?",
                                  (reflection["trajectory_id"],)).rowcount
            print(f"{reflection['task_id']}: archived {archived} earlier case(s)")
    with ReflectionCaseMemory(str(args.db_copy), "bolt", llm=llm, embedder=embedder, config=settings.memory,
                              log=JsonlRunLog(args.db_copy.with_suffix(".store-events.jsonl"))) as memory:
        for reflection in reflections:
            print(f"{reflection['task_id']}: stored {len(memory.store(reflection))} case(s)")


if __name__ == "__main__":
    main()
