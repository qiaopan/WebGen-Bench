#!/usr/bin/env python3
"""Does code evidence change the reflection? Same prompt and model, with vs without code files."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import case_reflection_evidence, memory_llm_from_settings  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402
from post_task_reflection import create_reflection  # noqa: E402

SOURCES = [ROOT / "outputs/experiment/library_14_18_strong/memory_snapshot.db",
           ROOT / "outputs/experiment/stages_000019_r1_gen/memory.db"]


def main() -> None:
    settings, llm, _ = make_memory_clients(ROOT / "config/long_memory.json")
    reflection_llm = memory_llm_from_settings(llm.client, settings.reflection_llm)
    rows = []
    for db in SOURCES:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        for row in con.execute("SELECT * FROM trajectories ORDER BY started_at"):
            trajectory = dict(row)
            if trajectory["task_id"] == "000019" and "stages_000019" not in str(db):
                continue
            if trajectory["task_id"] in {r["task"] for r in rows}:
                continue
            checks = json.loads(trajectory["evaluation_results"])
            if not [c for c in checks if c["check"] != "appearance" and c["outcome"] != "passed"]:
                continue
            evidence = case_reflection_evidence(trajectory)
            without = [e for e in evidence if e["ref"].get("kind") not in ("code_manifest", "code_file")]
            a = create_reflection(reflection_llm, trajectory, without)
            b = create_reflection(reflection_llm, trajectory, evidence)
            rows.append({"task": trajectory["task_id"],
                         "without": [{k: x[k] for k in ("feature_object", "likely_cause_or_limitation", "preventative_action")}
                                     for x in a["functional_reflections"]],
                         "with": [{"feature_object": x["feature_object"],
                                   "likely_cause_or_limitation": x["likely_cause_or_limitation"],
                                   "preventative_action": x["preventative_action"],
                                   "code": x.get("code_evidence")} for x in b["functional_reflections"]]})
            print("done", trajectory["task_id"], flush=True)
    out = ROOT / "outputs/experiment/code_evidence_comparison.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
