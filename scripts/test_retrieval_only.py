#!/usr/bin/env python3
"""Retrieval-only smoke test; no website generation and no database writes."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from long_memory import connect_database  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402
from long_memory_integrations import AzureEmbedder, AzureMemoryLLM  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--task", help="Public task requirement text")
    p.add_argument("--task-file", type=Path, help="File containing the public task requirement")
    p.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = p.parse_args()
    if not args.task and not args.task_file:
        p.error("one of --task or --task-file is required")
    task = args.task_file.read_text(encoding="utf-8").strip() if args.task_file else args.task
    load_dotenv(ROOT / ".env")
    settings = load_long_memory_settings(args.memory_config)
    client = OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                    base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1",
                    timeout=120, max_retries=2)
    llm = AzureMemoryLLM(client, settings.memory_llm["deployment"],
                         max_tokens=settings.memory_llm["max_completion_tokens"])
    embedder = AzureEmbedder(client, settings.embedding["deployment"],
                             dimensions=settings.embedding["dimensions"])
    with ReflectionCaseMemory(str(args.database), "bolt", llm=llm,
                              embedder=embedder, config=settings.memory) as memory:
        packet = memory.retrieve(task)
        print(json.dumps({"selected_case_ids": [item.case_id for item in packet.cases],
                          "rendered_memory": packet.render()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
