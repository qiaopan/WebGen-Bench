#!/usr/bin/env python3
"""Diagnostic: appearance-only reflection (one case per reviewer deduction, grounded in code).

Reads one trajectory from a memory DB, calls the reflection model once, prints the cases.
Writes nothing (no DB, no files). Usage:
  python scripts/test_appearance_reflection.py [--db PATH] [--task 000021]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import case_reflection_evidence, memory_llm_from_settings  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from post_task_reflection import create_appearance_reflections  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "outputs/experiment/stages_000021_r1_gen/memory.db"))
    parser.add_argument("--task", default="000021")
    args = parser.parse_args()
    settings, llm, _ = make_memory_clients(ROOT / "config/long_memory.json")
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    trajectory = dict(con.execute("SELECT * FROM trajectories WHERE task_id=? ORDER BY rowid DESC",
                                  (args.task,)).fetchone())
    dropped: list = []
    cases = create_appearance_reflections(reflection_llm, trajectory, case_reflection_evidence(trajectory), dropped)
    print(f"{args.task}: {len(cases)} case(s)")
    for number, case in enumerate(cases, 1):
        code = case.get("code_evidence") or {}
        print(f"\n[{number}] channel={case.get('channel')}"
              f"\n    deduction (quote grounded={case['deduction_grounded']}): {case['deduction']}"
              f"\n    grouped because: {case.get('group_reason')}"
              f"\n    observed: {case['observed_result']}"
              f"\n    cause   : {case['likely_cause_or_limitation']}"
              f"\n    action  : {case['preventative_action']}"
              f"\n    verify  : {case['verification']}"
              f"\n    limits  : {case['transfer_limits']}"
              f"\n    code    : grounded={code.get('grounded')} file={code.get('file')} "
              f"snippet={str(code.get('snippet'))[:100]!r}")
    for case in dropped:
        print(f"\nDROPPED (no verified code citation): {case['deduction'][:120]}\n    action was: {case['preventative_action'][:200]}"
              f"\n    cited: {case.get('code_evidence')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
