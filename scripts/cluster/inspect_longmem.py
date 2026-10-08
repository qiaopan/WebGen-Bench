#!/usr/bin/env python3
"""Read-only audit of a Long Memory chain, task by task in execution order:
what reflection extracted and stored after each task, and what retrieval/condensing injected before it.

Usage: inspect_longmem.py LONGMEM_OUTPUT_DIR [--tasks N]   (first N completed tasks; default all)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def short(text, n=150) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n] + "…"


def decision_label(item: dict) -> str:
    for key in ("decision", "relevance", "label", "match", "verdict"):
        if item.get(key):
            return str(item[key])
    return "?"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--tasks", type=int, default=0)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.output / "progress.jsonl").read_text().splitlines()]
    done = [row for row in rows if row.get("mode") == "continual" and row.get("status") == "complete"]
    if args.tasks:
        done = done[:args.tasks]
    retrievals = [json.loads(line) for line in (args.output / "memory-events.jsonl").read_text().splitlines()
                  if json.loads(line).get("operation") == "case_retrieval"]
    db = sqlite3.connect(f"file:{args.output / 'memory.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    case_task = {r["case_id"]: r["task_id"] for r in db.execute(
        "SELECT c.case_id, t.task_id FROM reflection_cases c JOIN trajectories t USING (trajectory_id)")}

    for number, row in enumerate(done, 1):
        task_id = row["task_id"]
        checks = [c for c in row.get("evaluation", []) if c.get("check") != "appearance"]
        outcome = Counter(c.get("outcome") for c in checks)
        types = Counter(c.get("failure_type") for c in checks if c.get("outcome") != "passed")
        appearance = next((c.get("score") for c in row.get("evaluation", []) if c.get("check") == "appearance"), None)
        print(f"\n{'=' * 100}\n#{number} task {task_id}: passed {outcome['passed']} / partial {outcome['partial']} / "
              f"failed {outcome['failed']} of {len(checks)}; appearance {appearance}; "
              f"generation_failed={bool(row.get('generation_failed'))}; prompt_delivered={row.get('prompt_delivered')}")
        if types:
            print(f"   non-pass types: {dict(types)}")

        # ---- before the task: retrieval and injected guidance
        task_text = None
        trajectory = db.execute("SELECT * FROM trajectories WHERE trajectory_id=?",
                                (row.get("trajectory_id"),)).fetchone() if row.get("trajectory_id") else None
        if trajectory is not None:
            task_text = trajectory["task_request"]
        event = next((e for e in retrievals if task_text and str(e.get("task", "")).strip() == task_text.strip()), None)
        print("-- RETRIEVAL (before generation)")
        if event is None:
            print("   no case_retrieval event matched this task")
        else:
            aspects = event.get("aspects", {})
            print(f"   aspects: functional {len(aspects.get('functional', []))}, appearance {len(aspects.get('appearance', []))}")
            for channel, candidates in (event.get("candidates_by_channel") or {}).items():
                flat = [c for group in candidates for c in (group if isinstance(group, list) else [group])]
                if flat:
                    print(f"   {channel}: {len(flat)} candidate(s) from tasks "
                          f"{sorted({case_task.get(c.get('case_id'), '?') for c in flat})}")
            for channel, decisions in (event.get("decisions_by_channel") or {}).items():
                labels = Counter(decision_label(d) for d in decisions or [])
                if labels:
                    print(f"   {channel} decisions: {dict(labels)}")
            selected = event.get("selected") or []
            print(f"   selected: {len(selected)} case(s) from tasks {[case_task.get(c, '?') for c in selected]}")
            if task_id in [case_task.get(c) for c in selected]:
                print("   !! LEAK: a selected case comes from this same task")
            pool = event.get("common_pool") or {}
            print(f"   common pool: applied={pool.get('applied')}, candidates={len(pool.get('candidates') or [])}, "
                  f"patterns={len(pool.get('patterns') or [])}")
            condense = event.get("guidance_condense") or {}
            items = condense.get("items") or []
            print(f"   condensed: {len(items)} item(s), {sum(len(str(i)) for i in items)}/{condense.get('budget_chars')} chars, "
                  f"from {condense.get('candidates')} candidate(s); packet {event.get('packet_chars')} chars")
            for item in items:
                print(f"     - {short(item.get('text') if isinstance(item, dict) else item, 160)}")

        # ---- after the task: what reflection extracted and stored
        print("-- REFLECTION (after evaluation)")
        print(f"   raw={row.get('raw_reflection_count')} kept={row.get('reflection_count')} "
              f"experience_candidate={bool(row.get('experience_candidate_record_id'))}")
        if trajectory is None:
            print("   no trajectory row")
            continue
        cases = db.execute("SELECT * FROM reflection_cases WHERE trajectory_id=? ORDER BY created_at",
                           (trajectory["trajectory_id"],)).fetchall()
        status = Counter((c["channel"], c["status"]) for c in cases)
        print(f"   stored cases: {dict(status)}; embedded: {sum(1 for c in cases if c['embedding'] is not None)}/{len(cases)}")
        for case in cases:
            refs = json.loads(case["evidence_refs"] or "[]")
            grounded = sum(1 for r in refs if isinstance(r, dict) and r.get("grounded"))
            print(f"   [{case['channel'][:4]}|{case['status']}] {short(case['feature_object'], 60)}")
            print(f"       cause: {short(case['root_cause_or_hypothesis'], 170)}")
            print(f"       action: {short(case['preventative_action'], 170)}")
            print(f"       evidence refs {len(refs)} (grounded {grounded}); provenance {case['provenance_status']}")
        facts = db.execute("SELECT COUNT(*) FROM check_facts WHERE trajectory_id=?",
                           (trajectory["trajectory_id"],)).fetchone()[0] if _has(db, "check_facts") else "n/a"
        run_fact = db.execute("SELECT COUNT(*) FROM run_facts WHERE trajectory_id=?",
                              (trajectory["trajectory_id"],)).fetchone()[0] if _has(db, "run_facts") else "n/a"
        print(f"   statistics: run_facts {run_fact}, check_facts {facts}")


def _has(db, table: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


if __name__ == "__main__":
    main()
