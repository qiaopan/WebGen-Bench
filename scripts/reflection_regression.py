#!/usr/bin/env python3
"""Reflection-prompt regression: re-run post-task reflection on fixed, human-checked tasks and score it.

Each prompt change can fix a new task and quietly break an old one. This re-reflects every task in
the gold file with the CURRENT prompt (Azure reflection model only; the generator is not used, the
memory DB is only read) and scores each failed/partial check against the human-checked attribution.
The gold labels only score prompt versions; they are never written into Long Memory.

Per check: a case must exist when the gold cause is established; its cause_confidence must match
(unless gold says "any"); an established case must name the cause (one of cause_any) and must not
state a forbidden conclusion. Established causes written with hedged wording are flagged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import finish_post_task as fpt  # noqa: E402
import run_continual_memory as rcm  # noqa: E402
from long_memory import connect_database  # noqa: E402
from long_memory_integrations import memory_llm_from_settings  # noqa: E402
from post_task_reflection import prompt_version  # noqa: E402

HEDGE = re.compile(r"\b(appears?|seems?|likely|may|might|probably|possibly)\b", re.IGNORECASE)


def reflect(output: Path, task_id: str) -> dict:
    ctx = fpt.load_context(output, task_id)
    settings = ctx["settings"]
    reflection_llm = memory_llm_from_settings(ctx["llm"].client, settings.reflection_llm)
    with connect_database(ctx["database"], read_only=True) as connection:
        source = dict(connection.execute("SELECT * FROM trajectories WHERE trajectory_id=?",
                                         (ctx["trajectory_id"],)).fetchone())
        history = rcm.setup_history(rcm.earlier_trajectories(connection, source))
    return rcm.create_reflection(reflection_llm, source, rcm.case_reflection_evidence(source),
                                 review=settings.memory.post_task_case_review,
                                 style=settings.memory.reflection_style,
                                 appearance_mode=settings.memory.appearance_reflection,
                                 setup_history=history)


def _text(case: dict) -> str:
    code = case.get("code_evidence") or {}
    investigation = case.get("investigation") or {}
    return " ".join(str(x) for x in (case.get("likely_cause_or_limitation"), case.get("observed_result"),
                                     investigation.get("conclusion") if isinstance(investigation, dict) else "",
                                     case.get("preventative_action"), code.get("snippet") if isinstance(code, dict) else code))


def score(gold: dict, reflection: dict) -> list[dict]:
    cases = {}
    for case in reflection.get("functional_reflections", []):
        cases.setdefault(case.get("check_index"), []).append(case)
    rows = []
    for check, expect in gold.items():
        if check.startswith("_"):
            continue
        index = int(check.rsplit("_", 1)[1])
        found = cases.get(index, [])
        case = found[0] if found else None
        confidence = case.get("cause_confidence") if case else "none"
        want = expect.get("confidence", "any")
        problems = []
        if want == "established" and confidence != "established":
            problems.append(f"expected established, got {confidence}")
        if want == "uncertain" and confidence == "established":
            problems.append("guessed cause stated as established")
        if case and confidence == "established":
            text = _text(case).lower()
            if expect.get("cause_any") and not any(k.lower() in text for k in expect["cause_any"]):
                problems.append("cause not named")
            wrong = [k for k in expect.get("forbid", []) if k.lower() in text]
            if wrong:
                problems.append(f"forbidden conclusion: {wrong}")
            if HEDGE.search(str(case.get("likely_cause_or_limitation", ""))):
                problems.append("hedged wording but established")
        rows.append({"check": check, "expect": want, "got": confidence, "ok": not problems,
                     "problems": problems, "cause": str(case.get("likely_cause_or_limitation", ""))[:200] if case else ""})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1")
    parser.add_argument("--gold", type=Path, default=ROOT / "config/reflection_regression/gold_v1.json")
    parser.add_argument("--tasks", nargs="*", help="subset of gold task ids")
    parser.add_argument("--results", type=Path, default=ROOT / "outputs/experiment/reflection_regression")
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text())
    version = prompt_version()
    run_dir = args.results / f"{version}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True)
    summary = {"prompt_version": version, "gold": str(args.gold), "tasks": {}}
    for task_id in args.tasks or [k for k in gold if not k.startswith("_")]:
        reflection = reflect(args.output.resolve(), task_id)
        (run_dir / f"{task_id}.reflection.json").write_text(json.dumps(reflection, ensure_ascii=False, indent=2))
        rows = score(gold[task_id], reflection)
        summary["tasks"][task_id] = rows
        print(f"## {task_id}  {sum(r['ok'] for r in rows)}/{len(rows)} ok")
        for skip in reflection.get("functional_skipped", []):
            print(f"  (no case for check {skip.get('check_index')}: {skip.get('reason')})")
        for row in rows:
            print(f"  {'OK ' if row['ok'] else 'BAD'} {row['check']} expect={row['expect']} got={row['got']} "
                  f"{'; '.join(row['problems'])}\n      {row['cause']}")
    total = [r for rows in summary["tasks"].values() for r in rows]
    summary["ok"], summary["checks"] = sum(r["ok"] for r in total), len(total)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nprompt {version}: {summary['ok']}/{summary['checks']} checks ok -> {run_dir}")


if __name__ == "__main__":
    main()
