#!/usr/bin/env python3
"""Block-level retrospective reflection over all tasks except --before-task, into a DB copy."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import memory_llm_from_settings  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402
from retrospective_reflection import collect_block, retrospective  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True, help="DB copy; retrospective cases are appended")
    parser.add_argument("--before-task", required=True, help="review every task except this one")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    settings, _, embedder = make_memory_clients(args.memory_config.resolve())
    load_dotenv(ROOT / ".env")
    client = OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"], timeout=180, max_retries=2,
                    base_url=(os.environ.get("WEBGEN_MEMORY_BASE_URL")
                              or os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1"))
    llm = memory_llm_from_settings(client, settings.reflection_llm)
    block = collect_block(args.database.resolve(), "bolt", args.before_task)
    result = retrospective(llm, block)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "retrospective.json").write_text(json.dumps(
        {"block_tasks": [t["task_id"] for t in block["tasks"]], "tables": block["tables"], **result},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stored: list[str] = []
    if result["cases"]:
        latest = block["tasks"][-1]
        reflection = {"reflection_id": uuid.uuid4().hex, "trajectory_id": latest["trajectory_id"],
                      "public_task_requirement": f"Cross-task retrospective over tasks {block['tasks'][0]['task_id']}-{latest['task_id']}",
                      "appearance_reflection": None, "functional_reflections": [],
                      "implementation_reflection": result["cases"][0]}
        with ReflectionCaseMemory(str(args.database.resolve()), "bolt", llm=llm, embedder=embedder,
                                  config=settings.memory) as memory:
            for case in result["cases"]:
                stored += memory.store({**reflection, "implementation_reflection": case})
    print("tasks reviewed:", [t["task_id"] for t in block["tasks"]])
    for cat, v in block["tables"].items():
        print(f"  {cat}: " + ", ".join(f"{s} {c['passed']}/{c['checks']}" for s, c in v["stacks"].items()))
    for case in result["cases"]:
        print("\nCASE", case["feature_object"], "\n  cause:", case["likely_cause_or_limitation"],
              "\n  action:", case["preventative_action"], "\n  cited:", case["evidence_refs"][0]["statistics"])
    for bad in result["rejected"]:
        print("REJECTED:", bad["why"], "|", str(bad["item"])[:200])
    print("stored case ids:", [c[:8] for c in stored])


if __name__ == "__main__":
    main()
