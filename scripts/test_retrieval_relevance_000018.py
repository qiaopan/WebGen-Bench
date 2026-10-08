#!/usr/bin/env python3
"""Relevance-gate check for 000018 against hand-labelled expectations.

Replays the candidates logged for 000018 (no embedding, no generation, no DB writes)
through the real relevance-gate prompts with the Memory LLM (a few small calls) and
compares the selection with the human judgement.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from long_memory_integrations import AzureMemoryLLM  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402

DEFAULT_EVENTS = ROOT / "outputs/experiment/continual_14_to_16_fresh/memory-events.jsonl"
DEFAULT_DB = ROOT / "outputs/experiment/continual_14_to_16_fresh/memory.db"

# Human labels for 000018 (case_id prefix). must: has to be selected. forbidden: must not be selected.
EXPECTED = {
    "functional": {
        0: {"must": "830c090a"},   # booking form submit -> confirmation
        1: {"must": "44c0433f"},   # service inquiry -> details (cross-domain soft transfer)
        2: {"forbidden": ["830c090a", "9af12dd9", "ad8ef753", "44c0433f"]},  # tel/mailto: no real match
    },
    "appearance": {0: {"forbidden": ["ad791710", "4ae4ee83", "92094591"]}},
}


class PassthroughAdaptationLLM:
    """Real LLM for relevance judgements; adaptation is bypassed so selection is observable."""

    def __init__(self, llm: AzureMemoryLLM):
        self.llm = llm
        self.calls: list[str] = []

    def generate(self, operation: str, payload):
        self.calls.append(operation)
        if operation == "case_implementation_adaptation":
            return {"patterns": [{"case_id": c["case_id"], "applicable": True, "reason": "test passthrough",
                                  "implementation_pattern": "test"} for c in payload["selected_cases"]]}
        return self.llm.generate(operation, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB,
                        help="Copied to a temp file; never modified")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()

    events = [json.loads(line) for line in args.events.read_text(encoding="utf-8").splitlines() if line.strip()]
    event = next(e for e in events if e.get("operation") == "case_retrieval" and "house cleaning" in e.get("task", ""))
    aspects, candidates, task = event["aspects"], event["candidates_by_channel"], event["task"]

    load_dotenv(ROOT / ".env")
    settings = load_long_memory_settings(args.memory_config)
    client = OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                    base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1",
                    timeout=120, max_retries=2)
    llm = PassthroughAdaptationLLM(AzureMemoryLLM(client, settings.memory_llm["deployment"],
                                                  max_tokens=settings.memory_llm["max_completion_tokens"]))
    logs: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "memory.db"
        shutil.copy(args.database, db)
        with ReflectionCaseMemory(str(db), "bolt", llm=llm, embedder=None, config=settings.memory,
                                  log=logs.append) as memory:
            replay = {ch: iter(candidates[ch]) for ch in ("functional", "appearance")}
            memory._discover_channel = lambda channel, _aspects: next(replay[channel])  # type: ignore[method-assign]
            packet = memory.retrieve(task, preclassified=aspects)

    retrieval = next(e for e in logs if e.get("operation") == "case_retrieval")
    failures: list[str] = []
    print(f"{'channel':<11}{'aspect':<7}{'case':<10}{'verdict':<14}reason")
    for channel in ("functional", "appearance"):
        for decision in retrieval["decisions_by_channel"][channel]:
            print(f"{channel:<11}{decision.get('matched_aspect_index')!s:<7}{str(decision.get('case_id'))[:8]:<10}"
                  f"{decision.get('verdict')!s:<14}{str(decision.get('reason'))[:90]}")

    selected = {item.case_id for item in packet.cases}
    print("\nselected:", sorted(case[:8] for case in selected))
    for channel, per_aspect in EXPECTED.items():
        for index, rule in per_aspect.items():
            picked = {d["case_id"][:8] for d in retrieval["decisions_by_channel"][channel]
                      if d.get("matched_aspect_index") == index
                      and d.get("verdict") in ("hard_match", "soft_transfer") and d["case_id"] in selected}
            if "must" in rule and rule["must"] not in picked:
                failures.append(f"{channel}[{index}] should select {rule['must']}, got {sorted(picked)}")
            for bad in rule.get("forbidden", []):
                if bad in picked:
                    failures.append(f"{channel}[{index}] should NOT select {bad}")
    for channel, groups in candidates.items():
        for index, group in enumerate(groups):
            covered = {d.get("case_id") for d in retrieval["decisions_by_channel"][channel]
                       if d.get("matched_aspect_index") == index}
            for item in group:
                if item["case_id"] not in covered:
                    failures.append(f"{channel}[{index}] no decision for {item['case_id'][:8]}")
    incomplete = [e for e in logs if e.get("operation") == "incomplete_decisions"]
    print("incomplete_decisions events:", len(incomplete))
    if failures:
        print("\nFull decisions for functional aspect 0 and 1:")
        for decision in retrieval["decisions_by_channel"]["functional"]:
            if decision.get("matched_aspect_index") in (0, 1):
                print(json.dumps(decision, ensure_ascii=False, indent=1))
    print("\nRESULT:", "PASS" if not failures else "FAIL")
    for failure in failures:
        print(" -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
