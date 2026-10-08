#!/usr/bin/env python3
"""Stage 2: rewrite the stage-1 selection into implementation guidance and the final prompt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import bolt_memory_prompt  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from reflection_case_memory import CasePacket, ReflectionCaseMemory, RetrievedCase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True, help="Snapshot DB (only opened, not read)")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    stage1 = json.loads(args.stage1.read_text(encoding="utf-8"))
    settings, llm, embedder = make_memory_clients(args.memory_config.resolve())
    selected = tuple(RetrievedCase(c["case_id"], c["content"], c["similarity"]) for c in stage1["selected"])
    with ReflectionCaseMemory(str(args.database), "bolt", llm=llm, embedder=embedder,
                              config=settings.memory) as memory:
        adaptations, kept = memory.adapt_cases(stage1["task"], stage1["aspects"], selected)
        memory.statistics_task_id = stage1["task_id"]
        kept, ordering = memory.order_by_statistics(kept)
    common: tuple = ()
    common_raw: dict = {}
    if settings.memory.common_pool and stage1.get("common_candidates"):
        with ReflectionCaseMemory(str(args.database), "bolt", llm=llm, embedder=embedder,
                                  config=settings.memory) as memory:
            common, common_raw = memory.adapt_common_pool(
                [RetrievedCase(c["case_id"], c["content"], 0.0) for c in stage1["common_candidates"]])
    memory_statistics = ""
    if settings.memory.statistics_memory:
        from memory_statistics import PriorityParams, render_block, summarize
        memory_statistics = render_block(summarize(args.database.resolve(), "bolt", stage1["task_id"],
                                                   PriorityParams.from_config(settings.memory)))
    packet = CasePacket(kept, common=common, statistics=memory_statistics)
    prompt = bolt_memory_prompt(stage1["task"], packet, base_constraints=settings.memory.base_constraints_in_prompt)
    guidance = [{"case_id": c.case_id, "case_type": c.content.get("case_type", "functional"),
                 "matched_aspect": c.content.get("matched_aspect"),
                 "implementation_pattern": c.content["implementation_pattern"]} for c in kept]
    out = args.stage1.parent
    (out / "stage2.json").write_text(json.dumps(
        {"task_id": stage1["task_id"], "task": stage1["task"], "adaptations": adaptations, "guidance": guidance,
         "statistics": memory_statistics, "statistics_ordering": ordering,
         "common": list(common), "common_adaptation": common_raw},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "final_prompt.txt").write_text(prompt, encoding="utf-8")

    print("COMMON POOL:", json.dumps(common_raw, ensure_ascii=False, indent=1))
    print("STATISTICS ORDERING:", json.dumps(ordering, ensure_ascii=False))
    print("ADAPTATION DECISIONS")
    for a in adaptations:
        aspect = a.get("matched_aspect") or {}
        label = aspect.get("feature_object") or aspect.get("visual_requirement") or "-"
        print(f"  {str(a.get('case_id'))[:8]} -> {label[:28]:<28} applicable={a.get('applicable')} | {str(a.get('reason'))[:120]}")
    print("\nFINAL PROMPT\n" + "-" * 60 + "\n" + prompt + "\n" + "-" * 60)
    print(f"saved {out / 'stage2.json'} and {out / 'final_prompt.txt'}")


if __name__ == "__main__":
    main()
