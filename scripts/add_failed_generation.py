#!/usr/bin/env python3
"""Record an already-finished failed generation (validation never passed) as Long Memory, on a DB copy.

Same steps the continual runner performs when generation fails: failed trajectory (execution_error),
all checks counted failed, reflection on the build errors and the source they name, statistics rows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from generation_failure_memory import failed_evaluation, failed_generation_evidence, failure_reflection  # noqa: E402
from long_memory_integrations import memory_llm_from_settings  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from memory_statistics import detect_stack  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402
from run_continual_memory import insert_failed_trajectory, load_manifest, record_statistics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--generation-dir", type=Path, required=True, help="dir holding 000001.attempt-*.failed.zip")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "data/experiment_splits/continual_domain_blocks/manifest.json")
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    batch, task = next((b, t) for b, t in load_manifest(args.manifest.resolve(), None) if str(t["id"]) == args.task_id)
    settings, llm, embedder = make_memory_clients(args.memory_config.resolve())
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    destination = args.generation_dir.resolve()
    evidence = failed_generation_evidence(destination)
    evaluation = failed_evaluation(task)
    trajectory_id = insert_failed_trajectory(args.database.resolve(), task, destination, "webgen-generator-gpt41-mini",
                                             batch, evidence, evaluation)
    stack = detect_stack(evidence["archive"]) if evidence["archive"] else "unknown"
    lesson = failure_reflection(reflection_llm, task["instruction"], trajectory_id, stack, evidence)
    case_ids: list[str] = []
    if lesson:
        with ReflectionCaseMemory(str(args.database.resolve()), "bolt", llm=llm, embedder=embedder,
                                  config=settings.memory) as memory:
            case_ids = memory.store(lesson)
    record_statistics(args.database.resolve(), llm, task, trajectory_id, evidence["archive"], evaluation,
                      [lesson["implementation_reflection"]["likely_cause_or_limitation"]] if lesson else [],
                      destination, generation_ok=False)
    print(json.dumps({"stack": stack, "attempt_phases": [a["phase"] for a in evidence["attempts"]],
                      "files_read": list(evidence["files"]), "case_ids": [c[:8] for c in case_ids],
                      "lesson": lesson["implementation_reflection"] if lesson else None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
