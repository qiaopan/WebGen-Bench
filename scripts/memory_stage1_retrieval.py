#!/usr/bin/env python3
"""Stage 1: aspects -> candidate recall -> relevance judgement. Memory LLM + embeddings only."""
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
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import AzureEmbedder, AzureMemoryLLM  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402
from run_continual_memory import load_manifest  # noqa: E402


def make_memory_clients(config_path: Path):
    load_dotenv(ROOT / ".env")
    settings = load_long_memory_settings(config_path)
    base_url = (os.environ.get("WEBGEN_MEMORY_BASE_URL")
                or os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1")
    client = OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"], base_url=base_url, timeout=120, max_retries=2)
    llm = AzureMemoryLLM(client, settings.memory_llm["deployment"],
                         max_tokens=settings.memory_llm["max_completion_tokens"])
    embedder = AzureEmbedder(client, settings.embedding["deployment"], dimensions=settings.embedding["dimensions"])
    return settings, llm, embedder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--database", type=Path, required=True, help="Snapshot DB (see make_memory_snapshot.py)")
    parser.add_argument("--out", type=Path, required=True, help="Directory for stage1.json")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "data/experiment_splits/continual_domain_blocks/manifest.json")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    task = next(t for _, t in load_manifest(args.manifest.resolve(), None) if str(t["id"]) == args.task_id)
    settings, llm, embedder = make_memory_clients(args.memory_config.resolve())
    events: list[dict] = []
    with ReflectionCaseMemory(str(args.database), "bolt", llm=llm, embedder=embedder,
                              config=settings.memory, log=events.append) as memory:
        memory.statistics_task_id = args.task_id  # before any retrieval: enables same-task exclusion
        aspects = memory._aspects(task["instruction"])
        candidates, decisions, selected = memory.select_cases(task["instruction"], aspects)
        common, common_info = (memory.common_pool_candidates(task["instruction"]) if settings.memory.common_pool else ([], {}))
    args.out.mkdir(parents=True, exist_ok=True)
    result = {"task_id": args.task_id, "task": task["instruction"], "aspects": aspects,
              "candidates_by_channel": candidates, "decisions_by_channel": decisions,
              "selected": [{"case_id": c.case_id, "content": c.content, "similarity": c.similarity} for c in selected],
              "common_candidates": [{"case_id": c.case_id, "content": c.content} for c in common],
              "common_info": common_info,
              "excluded_same_task": len(memory.excluded_by_cutoff),
              "incomplete_decisions": [e for e in events if e.get("operation") == "incomplete_decisions"]}
    (args.out / "stage1.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("ASPECTS")
    for channel, items in aspects.items():
        for i, item in enumerate(items):
            print(f"  {channel}[{i}] {item.get('feature_object') or item.get('visual_requirement') or item.get('implementation_requirement')} | "
                  f"{item.get('user_trigger', '')} -> {item.get('expected_state_change', '')}")
    print("\nJUDGEMENTS (channel aspect case verdict | candidate feature | reason)")
    cases = {c["case_id"]: c["content"] for groups in candidates.values() for g in groups for c in g}
    for channel, items in decisions.items():
        for d in items:
            print(f"  {channel[:4]} {d['matched_aspect_index']} {d['case_id'][:8]} {d.get('verdict'):<13} | "
                  f"{cases.get(d['case_id'], {}).get('feature_object', '')[:32]:<32} | {str(d.get('reason'))[:110]}")
    print(f"\nCases excluded because they belong to this task: {len(memory.excluded_by_cutoff)}")
    print("\nCOMMON POOL CANDIDATES (priority order):", common_info)
    for c in common:
        print(f"  {c.case_id[:8]} | {c.content.get('feature_object', '')[:70]} | cause: {str(c.content.get('root_cause_or_hypothesis', ''))[:110]}")
    print("\nSELECTED:", [c.case_id[:8] for c in selected], " incomplete_decisions:", len(result["incomplete_decisions"]))
    print(f"saved {args.out / 'stage1.json'}")


if __name__ == "__main__":
    main()
