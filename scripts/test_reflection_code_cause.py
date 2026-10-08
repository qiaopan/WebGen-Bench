#!/usr/bin/env python3
"""Regression test: does post-task reflection trace failures to the generated code?

Runs the real reflection (reflection model + case review) on two trajectories whose root
cause was verified by hand (000015: contact form is an empty <form> on a static Astro
page; 000019: static mailto form and a search component that is never rendered) and
checks that a functional case cites real code and names an implementation cause.
Reads the DBs only; writes nothing.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import case_reflection_evidence, memory_llm_from_settings  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from post_task_reflection import _REQUIREMENT_CLAIM, create_reflection  # noqa: E402

CASES = [
    ("000015", ROOT / "outputs/experiment/library_14_18_strong/memory_snapshot.db",
     r"handler|static|client|hydrat|reload|refresh|script|onsubmit"),
    ("000019", ROOT / "outputs/experiment/stages_000019_r1_gen/memory.db",
     r"mailto|handler|static|client|render|hydrat|script|not used|unused|never"),
    ("000018", ROOT / "outputs/experiment/library_14_18_strong/memory_snapshot.db",
     r"sample|seed|resolv|first-time|first time"),
]


def main() -> int:
    settings, llm, _ = make_memory_clients(ROOT / "config/long_memory.json")
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    failures = []
    for task_id, db, pattern in CASES:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        trajectory = dict(con.execute("SELECT * FROM trajectories WHERE task_id=?", (task_id,)).fetchone())
        reflection = create_reflection(reflection_llm, trajectory, case_reflection_evidence(trajectory))
        print(f"\n===== {task_id}: {len(reflection['functional_reflections'])} functional case(s), "
              f"dropped by review: {reflection['dropped_by_critique']}")
        hit = False
        for item in reflection["functional_reflections"]:
            code = item.get("code_evidence") or {}
            print(f"- {item['feature_object'][:90]}\n    cause : {item['likely_cause_or_limitation'][:220]}"
                  f"\n    code  : grounded={code.get('grounded')} file={code.get('file')} "
                  f"snippet={str(code.get('snippet'))[:110]!r}\n    action: {item['preventative_action'][:240]}")
            text = item["likely_cause_or_limitation"] + " " + item["preventative_action"]
            req = item.get("requirement_evidence")
            print(f"    requirement_evidence: {None if req is None else (req['grounded'], req['quote'][:80])}")
            if _REQUIREMENT_CLAIM.search(text) and not (req and req.get("grounded")):
                failures.append(f"{task_id}: '{item['feature_object'][:50]}' claims the requirement asks for "
                                "something without a grounded quote")
            if code.get("grounded") and re.search(pattern, text, re.I):
                hit = True
        if not hit:
            failures.append(f"{task_id}: no grounded case naming an implementation cause")
    print("\nRESULT:", "PASS" if not failures else "FAIL")
    for failure in failures:
        print(" -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
