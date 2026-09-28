#!/usr/bin/env python3
"""Compare the two reflection styles (structured vs questions) on the same trajectories.

Same reflection model, same evidence (including the site's code). Reads DBs only; writes one JSON.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import case_reflection_evidence, memory_llm_from_settings  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from post_task_reflection import create_reflection  # noqa: E402

SOURCES = [(ROOT / "outputs/experiment/library_14_18_v4/memory_snapshot.db", None),
           (ROOT / "outputs/experiment/stages_000019_r1_gen/memory.db", {"000019"})]
HEDGE = re.compile(r"\b(may|might|possibly|appears? to|seems?|could be|does not prove|not proven|hypothesis|unclear)\b", re.I)


def summarise(reflection: dict) -> dict:
    cases = reflection["functional_reflections"]
    impl = reflection.get("implementation_reflection")
    grounded = sum(1 for c in cases if (c.get("code_evidence") or {}).get("grounded"))
    hedged = sum(1 for c in cases if HEDGE.search(c["likely_cause_or_limitation"]))
    words = [len(c["preventative_action"].split()) for c in cases]
    return {"cases": len(cases), "code_grounded": grounded, "hedged_cause": hedged,
            "avg_action_words": round(sum(words) / len(words), 1) if words else 0,
            "appearance": bool(reflection["appearance_reflection"]), "implementation": bool(impl)}


def main() -> None:
    settings, llm, _ = make_memory_clients(ROOT / "config/long_memory.json")
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    rows, seen = [], set()
    for db, only in SOURCES:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        for row in con.execute("SELECT * FROM trajectories ORDER BY started_at"):
            t = dict(row)
            if (only is not None and t["task_id"] not in only) or t["task_id"] in seen:
                continue
            checks = json.loads(t["evaluation_results"])
            if not [c for c in checks if c["check"] != "appearance" and c["outcome"] != "passed"]:
                continue
            seen.add(t["task_id"])
            evidence = case_reflection_evidence(t)
            out = {"task": t["task_id"]}
            for style in ("structured", "questions"):
                r = create_reflection(reflection_llm, t, evidence, style=style)
                out[style] = {"summary": summarise(r),
                              "cases": [{"feature": c["feature_object"], "cause": c["likely_cause_or_limitation"],
                                         "action": c["preventative_action"],
                                         "code": (c.get("code_evidence") or {}).get("file")}
                                        for c in r["functional_reflections"]],
                              "implementation": (r.get("implementation_reflection") or {}).get("preventative_action"),
                              "appearance": (r.get("appearance_reflection") or {}).get("preventative_action")}
            rows.append(out)
            print("done", t["task_id"], flush=True)
    out_path = ROOT / "outputs/experiment/reflection_style_comparison.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out_path)


if __name__ == "__main__":
    main()
