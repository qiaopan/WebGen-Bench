#!/usr/bin/env python3
"""Classify candidate evaluation tasks before any website generation.

This deliberately performs only the small structured ``aspects`` MemoryLLM call.
It does not create a database, embed text, retrieve memory, call Bolt, or run an
evaluator.  Use its CSV/JSON report to check the simple/medium/complex split and
choose a balanced pilot before spending generator tokens.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from long_memory_integrations import AzureMemoryLLM  # noqa: E402
from long_memory_runtime import OPERATIONS  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def parse_ids(value: str | None) -> set[str] | None:
    if not value:
        return None
    result = {item.strip() for item in value.split(",") if item.strip()}
    if not result:
        raise ValueError("--task-ids must contain at least one ID")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path,
                        default=ROOT / "data/experiment_splits/groups/group_02_dev_evaluate.jsonl")
    parser.add_argument("--task-ids", help="Optional comma-separated record IDs")
    parser.add_argument("--memory-config", type=Path,
                        default=ROOT / "config/long_memory.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "outputs/experiment/complexity_preflight")
    parser.add_argument("--max-completion-tokens", type=int, default=350,
                        help="Small budget for classification only (default: 350)")
    args = parser.parse_args()
    if args.max_completion_tokens < 100:
        parser.error("--max-completion-tokens must be at least 100")

    selected_ids = parse_ids(args.task_ids)
    records = load_jsonl(args.tasks.resolve())
    if selected_ids is not None:
        records = [record for record in records if str(record.get("id")) in selected_ids]
        missing = selected_ids - {str(record.get("id")) for record in records}
        if missing:
            parser.error("Unknown task IDs: " + ", ".join(sorted(missing)))
    if not records:
        parser.error("No tasks selected")

    load_dotenv(ROOT / ".env")
    settings = load_long_memory_settings(args.memory_config.resolve())
    base_url = os.environ["WEBGEN_GENERATOR_BASE_URL"]
    api_key = os.environ.get("AZURE_OPENAI_API_KEY") or os.environ["DASHSCOPE_API_KEY"]
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120, max_retries=2)
    llm = AzureMemoryLLM(
        client, settings.memory_llm["deployment"], max_tokens=args.max_completion_tokens,
        rate_limit_retries=settings.memory_llm.get("rate_limit_retries"),
        rate_limit_base_seconds=settings.memory_llm.get("rate_limit_base_seconds"),
        rate_limit_max_wait_seconds=settings.memory_llm.get("rate_limit_max_wait_seconds"),
        rate_limit_long_retry_seconds=settings.memory_llm.get("rate_limit_long_retry_seconds"),
        rate_limit_long_retries=settings.memory_llm.get("rate_limit_long_retries"),
    )
    strategies = {
        "simple": settings.memory.simple_retrieval_strategy,
        "medium": settings.memory.medium_retrieval_strategy,
        "complex": settings.memory.complex_retrieval_strategy,
    }

    rows: list[dict] = []
    for position, record in enumerate(records, start=1):
        result = llm.generate("aspects", {
            "instructions": OPERATIONS["aspects"],
            "task": record["instruction"],
            "max_aspects": settings.memory.max_task_aspects,
        })
        aspects = result.get("aspects")
        complexity = result.get("complexity")
        reason = result.get("complexity_reason")
        if (complexity not in strategies or not isinstance(reason, str)
                or not isinstance(aspects, list)
                or any(not isinstance(item, str) or not item.strip() for item in aspects)):
            raise ValueError(f"Invalid classifier result for {record['id']}: {result}")
        rows.append({
            "position": position,
            "task_id": str(record["id"]),
            "application_type": record.get("application_type", ""),
            "primary_category": record.get("Category", {}).get("primary_category", ""),
            "complexity": complexity,
            "retrieval_strategy": strategies[complexity],
            "complexity_reason": reason.strip(),
            "aspects": aspects[:settings.memory.max_task_aspects],
        })
        print(f"[preflight] {position}/{len(records)} {record['id']}: "
              f"{complexity} -> {strategies[complexity]}", flush=True)

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "complexity-preflight.json").write_text(
        json.dumps({"source_tasks": str(args.tasks.resolve()), "rows": rows}, ensure_ascii=False,
                   indent=2) + "\n", encoding="utf-8")
    with (output / "complexity-preflight.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("position", "task_id", "application_type",
                                "primary_category", "complexity", "retrieval_strategy",
                                "complexity_reason", "aspects"))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "aspects": " | ".join(row["aspects"])})
    counts = Counter(row["complexity"] for row in rows)
    print("[preflight] complete: " + ", ".join(
        f"{label}={counts[label]}" for label in ("simple", "medium", "complex")))
    print(f"[preflight] report: {output / 'complexity-preflight.csv'}")


if __name__ == "__main__":
    main()
