"""Retrospective (block-level) reflection for the Long Memory arm.

Per-task reflection can only compare a task with what came before it. After a block of tasks the
whole record is available, so this pass looks at all of it at once: code-computed tables of outcomes
by feature category and build setup, the project facts of every task, and the failure cases already
written. It may add cross-task cases (append-only; earlier rows are never changed). Every statistic a
new case cites must match the table exactly, otherwise the case is dropped.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from long_memory import connect_database
from memory_statistics import _other_task, _has_table, detect_stack, guidance_effects, summarize, summarize_checks

RETROSPECTIVE_INSTRUCTIONS = """You review a block of finished website tasks together. For each task you get
its public requirement, whether generation produced a working project (and at which phase it
failed if not), build setup facts (dependencies, project structure), how each functional
check turned out (feature category, outcome, whether the evidence came from the tester's actions or
the code, whether the public requirement stated the expectation) and the failure lessons already
written for it. "guidance_effects" lists, for memory items that were in earlier prompts, pass counts per feature
category with and without that item (correlational). If an item is followed by a drop elsewhere, write a
companion requirement that keeps both; never advise ignoring an item. You also get tables computed from all tasks: for each feature category, how many
checks passed on each build setup, and a table "project builds and starts" with how many generations
produced a working project on each build setup. A generation that never built has no per-feature checks.
Look for lessons that only become visible across tasks: outcomes that differ between build setups for
the same kind of feature, and problems that repeat in several tasks. For a setup difference, explain
the mechanism using the setup facts (what that setup provides or lacks for this kind of feature); a
difference in counts without a mechanism is not a lesson. State the sample sizes plainly and do not
claim more than the counts support.
Write at most 3 cases, each an implementation-level lesson for any website (which kind of setup to
use or avoid and what the interactive features must contain), without any site's content or page
names. Cite every count you rely on in statistics = [{"category","setup","passed","checks"}], copied
exactly from the tables, and list the task ids in source_tasks. If the tables show no difference and
nothing repeats, return {"cases": []}. Return JSON only:
{"cases":[{"feature_object":str,"user_trigger":str,"expected_state_change":str,"observed_result":str,
"likely_cause_or_limitation":str,"preventative_action":str,"verification":str,"transfer_limits":str,
"statistics":[{"category":str,"setup":str,"passed":int,"checks":int}],"source_tasks":[str]}]}."""

_FIELDS = ("feature_object", "user_trigger", "expected_state_change", "observed_result",
           "likely_cause_or_limitation", "preventative_action", "verification", "transfer_limits")


def project_facts(archive: str | Path) -> dict:
    """Setup facts read from the generated project itself."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = [n for n in bundle.namelist() if "node_modules" not in n and not n.endswith("/")]
            package = next((n for n in names if n.count("/") <= 1 and n.endswith("package.json")), None)
            data = json.loads(bundle.read(package).decode("utf-8", "replace")) if package else {}
    except Exception:
        return {}
    extensions: dict[str, int] = {}
    for name in names:
        suffix = Path(name).suffix.lower()
        if suffix in (".astro", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".html"):
            extensions[suffix] = extensions.get(suffix, 0) + 1
    return {"dependencies": sorted({**data.get("dependencies", {}), **data.get("devDependencies", {})}),
            "scripts": sorted(data.get("scripts", {})), "source_files_by_type": extensions,
            "config_files": sorted(n for n in names if n.count("/") <= 1 and re.search(
                r"(astro|vite|next|nuxt|svelte|webpack)\.config", n))}


def collect_block(database: str | Path, agent_id: str, current_task_id: str) -> dict:
    with connect_database(database, read_only=True) as connection:
        trajectories = [dict(r) for r in connection.execute(
            "SELECT * FROM trajectories WHERE agent_id=? ORDER BY started_at", (agent_id,))
            if _other_task(r["task_id"], current_task_id)]
        facts = ([dict(r) for r in connection.execute("SELECT * FROM check_facts WHERE agent_id=?", (agent_id,))]
                 if _has_table(connection, "check_facts") else [])
        runs = ({r["trajectory_id"]: dict(r) for r in connection.execute(
            "SELECT * FROM run_facts WHERE agent_id=?", (agent_id,))} if _has_table(connection) else {})
        cases = [dict(r) for r in connection.execute(
            "SELECT trajectory_id, feature_object, outcome, observed_result, root_cause_or_hypothesis "
            "FROM reflection_cases WHERE agent_id=? AND channel='functional'", (agent_id,))]
    tasks = []
    for trajectory in trajectories:
        artifacts = json.loads(trajectory["artifact_refs"] or "[]")
        archive = artifacts[0]["path"] if artifacts else ""
        tid = trajectory["trajectory_id"]
        tasks.append({
            "task_id": trajectory["task_id"], "trajectory_id": tid,
            "requirement": trajectory["task_request"][:600],
            "setup": detect_stack(archive) if archive else "unknown",
            "generation": ("working project" if runs.get(tid, {}).get("generation_ok", 1)
                           else f"failed at {runs[tid].get('failure_phase') or 'validation'} after repair attempts"),
            "setup_facts": project_facts(archive) if archive else {},
            "checks": [{"category": f["category"], "outcome": f["outcome"], "evidence_source": f["evidence_source"],
                        "requirement_stated": f["requirement_stated"]}
                       for f in facts if f["trajectory_id"] == tid],
            "failure_lessons": [{"feature": c["feature_object"], "outcome": c["outcome"],
                                 "cause": c["root_cause_or_hypothesis"][:300]}
                                for c in cases if c["trajectory_id"] == tid and c["outcome"] != "success"]})
    tables = summarize_checks(database, agent_id, current_task_id)
    builds = {setup: {"checks": v["runs"], "passed": v["runs"] - v["generation_failed"]}
              for setup, v in summarize(database, agent_id, current_task_id)["stacks"].items()}
    if builds:
        tables["project builds and starts"] = {"checks": sum(v["checks"] for v in builds.values()),
                                               "stacks": builds, "nonpass": 0, "unstated": 0}
    return {"tasks": tasks, "tables": tables, "guidance_effects": guidance_effects(database, agent_id, current_task_id)}


def _statistics_match(cited: list, tables: dict) -> bool:
    for item in cited:
        if not isinstance(item, dict):
            return False
        cell = tables.get(str(item.get("category", "")).lower(), {}).get("stacks", {}).get(str(item.get("setup", "")))
        if not cell or cell["passed"] != item.get("passed") or cell["checks"] != item.get("checks"):
            return False
    return True


def retrospective(llm: Any, block: dict) -> dict:
    """Returns {"cases": [valid case items], "rejected": [...], "raw": model output}."""
    payload = {"instructions": RETROSPECTIVE_INSTRUCTIONS, "tasks": block["tasks"],
               "guidance_effects": block.get("guidance_effects", []),
               "tables": {cat: {"checks": v["checks"], "by_setup": v["stacks"]} for cat, v in block["tables"].items()}}
    raw = llm.generate("retrospective_reflection", payload)
    proposed = raw.get("cases", []) if isinstance(raw, dict) else []
    known_tasks = {t["task_id"] for t in block["tasks"]}
    cases, rejected = [], []
    for item in proposed if isinstance(proposed, list) else []:
        if not isinstance(item, dict) or not all(str(item.get(f, "")).strip() for f in _FIELDS):
            rejected.append({"item": item, "why": "missing fields"})
        elif not item.get("statistics") or not _statistics_match(item["statistics"], block["tables"]):
            rejected.append({"item": item, "why": "cited statistics do not match the tables"})
        elif not set(map(str, item.get("source_tasks", []))) <= known_tasks or not item.get("source_tasks"):
            rejected.append({"item": item, "why": "unknown or missing source tasks"})
        else:
            cases.append({**{f: str(item[f]).strip() for f in _FIELDS}, "outcome": "partial",
                          "feature_object": "[implementation] " + str(item["feature_object"]).replace("[implementation]", "").strip(),
                          "evidence_refs": [{"kind": "retrospective", "source_tasks": item["source_tasks"],
                                             "statistics": item["statistics"], "grounded": True}],
                          "provenance_status": "exact_or_normalised"})
    return {"cases": cases, "rejected": rejected, "raw": raw}
