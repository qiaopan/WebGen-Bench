"""Statistical memory for the Long Memory arm: facts about earlier runs, computed by code.

Each finished run appends one row to ``run_facts`` (technology stack, whether generation
produced a working project, check outcomes, cause labels). Aggregates are always
recomputed from those rows, restricted to tasks earlier than the current one, so the
statistics never contain information about the task being generated. The rendered block
states counts and sample sizes only; it contains no advice written by us.
"""
from __future__ import annotations

import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from dataclasses import dataclass

from long_memory import connect_database, ensure_optional_tables


@dataclass(frozen=True)
class PriorityParams:
    """Tunable numbers of the priority formula (see MemoryConfig for the meaning of each)."""
    window: int = 10
    half_life: float = 4.0
    severity_failed: float = 1.0
    severity_partial: float = 0.5
    alpha: float = 1.0

    @classmethod
    def from_config(cls, config: Any) -> "PriorityParams":
        return cls(window=config.priority_window, half_life=config.priority_half_life,
                   severity_failed=config.severity_failed, severity_partial=config.severity_partial,
                   alpha=config.priority_alpha)

# A generation that never built is a pipeline-defined category, not something a model labels.
BUILD_FAILURE_LABEL = "project did not build or start"
BUILD_FAILURE_FEATURE = "[implementation] Project builds and starts without errors"

_CAUSE_LABEL_INSTRUCTIONS = """Give each cause a broad category label of 2-4 words. Causes that would be
fixed by the same kind of implementation change must share one label, even when the features,
pages or wording differ. Reuse an existing label exactly whenever it fits; only invent a new label
when no existing label fits, and make it broad enough to cover related problems (no page names, no
example values, no brand words). Return JSON only: {"labels": [<one label per cause, same order>]}."""


def detect_stack(archive: str | Path) -> str:
    """Technology stack of a generated project, read from its own package.json."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            package = next((n for n in names if n.count("/") <= 1 and n.endswith("package.json")
                            and "node_modules" not in n), None)
            if package is None:
                return "static-html" if any(n.endswith("index.html") for n in names) else "unknown"
            data = json.loads(bundle.read(package).decode("utf-8", "replace"))
    except Exception:
        return "unknown"
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    for marker, label in (("astro", "astro"), ("next", "next"), ("nuxt", "nuxt"), ("@sveltejs/kit", "sveltekit"),
                          ("svelte", "svelte"), ("vue", "vue")):
        if marker in deps:
            return label
    if "react" in deps:
        return "react-vite" if "vite" in deps else "react-other"
    return "vite-vanilla" if "vite" in deps else "node-other"


def label_causes(llm: Any, causes: Sequence[str], existing_labels: Sequence[str]) -> list[str]:
    """One category label per cause text (same order), reusing the labels already in the table.
    Returns [] when the model's answer cannot be aligned with the input."""
    causes = [str(c).strip() or "unspecified problem" for c in causes]
    if not causes:
        return []
    result = llm.generate("cause_labelling", {
        "instructions": _CAUSE_LABEL_INSTRUCTIONS, "causes": causes,
        "existing_labels": list(existing_labels)})
    labels = result.get("labels") if isinstance(result, dict) else None
    if not isinstance(labels, list) or len(labels) != len(causes):
        return []
    return [re.sub(r"\s+", " ", str(label)).strip().lower() or "unspecified problem" for label in labels]


def setup_label(stack: str) -> str:
    """Pipeline-defined label for implementation-level problems: the detected build setup."""
    return f"setup: {stack}"


def add_setup_labels(database: str | Path, agent_id: str = "bolt") -> int:
    """Add the setup label to every run that has an implementation-level problem (a
    generation that never built, or an [implementation] case). Idempotent; returns rows changed."""
    changed = 0
    with connect_database(database, read_only=False) as connection:
        ensure_optional_tables(connection)
        for row in [dict(r) for r in connection.execute("SELECT * FROM run_facts WHERE agent_id=?", (agent_id,))]:
            has_case = connection.execute(
                "SELECT 1 FROM reflection_cases WHERE trajectory_id=? AND feature_object LIKE '[implementation]%' "
                "AND outcome IN ('partial','failure') LIMIT 1", (row["trajectory_id"],)).fetchone()
            if row["generation_ok"] and not has_case:
                continue
            causes = json.loads(row["causes"])
            label = setup_label(row["stack"])
            if label not in causes:
                connection.execute("UPDATE run_facts SET causes=? WHERE fact_id=?",
                                   (json.dumps(sorted({*causes, label}), ensure_ascii=False), row["fact_id"]))
                changed += 1
    return changed


def known_labels(connection: Any, agent_id: str) -> list[str]:
    if not _has_table(connection):
        return []
    labels: dict[str, int] = {}
    for row in connection.execute("SELECT causes FROM run_facts WHERE agent_id=?", (agent_id,)):
        for label in json.loads(row[0]):
            labels[label] = labels.get(label, 0) + 1
    return [label for label, _ in sorted(labels.items(), key=lambda item: -item[1])]


def _has_table(connection: Any, name: str = "run_facts") -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (name,)).fetchone() is not None


def record_run(database: str | Path, *, agent_id: str, task_id: str, trajectory_id: str,
               stack: str, generation_ok: bool, generation_attempts: int | None,
               failure_phase: str | None, outcomes: Mapping[str, int], causes: Sequence[str],
               cause_outcomes: Mapping[str, Mapping[str, int]] | None = None,
               prompt_delivered: bool | None = None, guidance_case_ids: Sequence[str] = (),
               guidance_total: int | None = None, guidance_followed: int | None = None,
               prompt_stats: Mapping[str, object] | None = None) -> str:
    fact_id = uuid.uuid4().hex
    with connect_database(database, read_only=False) as connection:
        ensure_optional_tables(connection)
        connection.execute(
            "INSERT OR REPLACE INTO run_facts (fact_id,agent_id,task_id,trajectory_id,stack,generation_ok,"
            "generation_attempts,failure_phase,checks_passed,checks_partial,checks_failed,causes,cause_outcomes,"
            "prompt_delivered,guidance_case_ids,guidance_total,guidance_followed,prompt_stats) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fact_id, agent_id, task_id, trajectory_id, stack, int(generation_ok), generation_attempts,
             failure_phase, int(outcomes.get("passed", 0)), int(outcomes.get("partial", 0)),
             int(outcomes.get("failed", 0)), json.dumps(sorted(set(causes)), ensure_ascii=False),
             json.dumps({k: dict(v) for k, v in (cause_outcomes or {}).items()}, ensure_ascii=False),
             None if prompt_delivered is None else int(prompt_delivered),
             json.dumps(list(guidance_case_ids)), guidance_total, guidance_followed,
             json.dumps(dict(prompt_stats or {}), ensure_ascii=False)))
    return fact_id


def prompt_stats(prompt: str, requirement: str, condense: Mapping[str, object] | None = None) -> dict:
    """Code-measured size of what the generator was sent: the requirement versus the injected memory.
    Everything after the requirement text is memory; bullet lines count as guidance items."""
    prompt, requirement = prompt.strip(), requirement.strip()
    memory = prompt[len(requirement):].strip() if prompt.startswith(requirement) else ""
    stats: dict[str, object] = {
        "prompt_chars": len(prompt), "requirement_chars": len(requirement), "memory_chars": len(memory),
        "memory_ratio": round(len(memory) / len(requirement), 3) if requirement else None,
        "memory_items": sum(line.lstrip().startswith("- ") for line in memory.splitlines()),
        "requirement_is_prefix": prompt.startswith(requirement)}
    if condense:
        stats["condense"] = {key: condense.get(key) for key in
                             ("applied", "candidates", "kept", "budget_chars", "used_chars")}
    return stats


def _other_task(task_id: str, current: str) -> bool:
    """Leave-one-task-out: everything except the task being run. Task numbers are not a timeline (the run
    order may be shuffled in ablations), so no ordering by number is assumed anywhere."""
    return task_id != current


def summarize(database: str | Path, agent_id: str, current_task_id: str,
              params: PriorityParams | None = None) -> dict:
    """Aggregate facts from all tasks except ``current_task_id`` (never the same task).

    Stack figures use all earlier runs. Cause figures use only the most recent ``window`` runs,
    with a decayed score (half-life in runs): a problem that stops appearing fades, so the
    ranking moves on to the problems that still occur (a curriculum driven by recent evidence).
    Each occurrence is weighted by its outcome (failed / partial checks, see PriorityParams)."""
    params = params or PriorityParams()
    with connect_database(database, read_only=True) as connection:
        if not _has_table(connection):
            return {"runs": 0, "stacks": {}, "causes": {}, "cause_scores": {}, "cause_totals": {}, "window_runs": 0}
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM run_facts WHERE agent_id=?", (agent_id,)) if _other_task(row["task_id"], current_task_id)]
    rows.sort(key=lambda r: r["recorded_at"])  # actual execution order (matters only if decay is on)
    stacks: dict[str, dict] = {}
    for row in rows:
        entry = stacks.setdefault(row["stack"], {"runs": 0, "generation_failed": 0, "passed": 0, "checks": 0})
        entry["runs"] += 1
        entry["generation_failed"] += 0 if row["generation_ok"] else 1
        entry["passed"] += row["checks_passed"]
        entry["checks"] += row["checks_passed"] + row["checks_partial"] + row["checks_failed"]
    recent = rows[-params.window:] if params.window > 0 else rows
    causes: dict[str, int] = {}
    scores: dict[str, float] = {}
    totals: dict[str, float] = {}  # severity summed over ALL history, no decay
    for row in rows:
        recorded_all = json.loads(row["cause_outcomes"] or "{}")
        for label in json.loads(row["causes"]):
            counts = recorded_all.get(label) or {"failed": 1 if row["generation_ok"] else max(1, row["checks_failed"])}
            totals[label] = totals.get(label, 0.0) + (counts.get("failed", 0) * params.severity_failed
                                                       + counts.get("partial", 0) * params.severity_partial)
    for age, row in enumerate(reversed(recent)):
        decay = 0.5 ** (age / params.half_life) if params.half_life > 0 else 1.0
        recorded = json.loads(row["cause_outcomes"] or "{}")
        for label in json.loads(row["causes"]):
            causes[label] = causes.get(label, 0) + 1
            counts = recorded.get(label)
            if counts is None:  # rows written before outcomes were kept: one failed check per run
                counts = {"failed": 1 if row["generation_ok"] else max(1, row["checks_failed"])}
            severity = (counts.get("failed", 0) * params.severity_failed
                        + counts.get("partial", 0) * params.severity_partial)
            scores[label] = scores.get(label, 0.0) + decay * severity
    scores = {label: value ** params.alpha for label, value in scores.items()}
    return {"runs": len(rows), "stacks": stacks, "causes": causes, "cause_scores": scores,
            "window_runs": len(recent), "cause_totals": totals, "categories": summarize_checks(database, agent_id, current_task_id)}


def render_block(summary: Mapping[str, Any], *, min_runs: int = 3, min_count: int = 2) -> str:
    """Compact fact block. Priority grows with evidence: entries are ranked by share weighted
    by sample size, and the number of entries shown grows with the number of earlier runs."""
    runs = int(summary.get("runs", 0))
    if runs < min_runs:
        return ""
    weight = runs / (runs + 5.0)
    entries: list[tuple[float, str]] = []
    for stack, item in summary["stacks"].items():
        if item["runs"] < min_count:
            continue
        failed_share = item["generation_failed"] / item["runs"]
        pass_rate = item["passed"] / item["checks"] if item["checks"] else 0.0
        text = (f"Stack {stack}: {item['runs']} earlier generations, "
                f"{item['generation_failed']} did not produce a working project ({failed_share:.0%}); "
                f"functional checks passed {item['passed']}/{item['checks']} ({pass_rate:.0%}).")
        # A generation that never built loses every check, so it weighs double.
        entries.append(((2 * failed_share + (1 - pass_rate) * 0.5) * item["runs"] / (item["runs"] + 5.0), text))
    recent = int(summary.get("window_runs", runs)) or runs
    for label, count in summary["causes"].items():
        if count < min_count:
            continue
        score = summary.get("cause_scores", {}).get(label, count)
        entries.append((score / recent * weight * 1.5,
                        f"Recorded problem \"{label}\": present in {count} of the last {recent} generations "
                        f"({count / recent:.0%})."))
    for category, item in summary.get("categories", {}).items():
        stacks = {name: v for name, v in item["stacks"].items() if v["checks"] >= 1}
        if len(stacks) >= 2 and item["checks"] >= 2 * min_count:
            rates = [v["passed"] / v["checks"] for v in stacks.values()]
            detail = ", ".join(f"{name} {v['passed']}/{v['checks']}" for name, v in sorted(stacks.items()))
            entries.append(((max(rates) - min(rates)) * item["checks"] / (item["checks"] + 5.0) * 1.2,
                            f"Checks on \"{category}\" passed by stack: {detail}."))
        if item["unstated"] >= 1:
            entries.append((item["unstated"] / item["nonpass"] * item["nonpass"] / (item["nonpass"] + 5.0),
                            f"Checks on \"{category}\": {item['unstated']} of {item['nonpass']} non-passing results "
                            f"concerned expectations the public requirement did not state."))
    if not entries:
        return ""
    limit = min(6, 2 + runs // 3)
    lines = [text for _, text in sorted(entries, key=lambda item: -item[0])[:limit]]
    return "\n".join(f"- {line}" for line in lines)


def _fixed_labels(database: str | Path, agent_id: str, cases: Sequence[Any]) -> dict[str, list[str]]:
    """Labels that code defines: implementation-level cases are labelled by the build setup of the
    run they came from (or, for cross-task cases, the setups whose counts they cite); a generation
    that never built also carries the build-failure category. No model is involved."""
    fixed: dict[str, list[str]] = {}
    with connect_database(database, read_only=True) as connection:
        has_runs = _has_table(connection)
        for case in cases:
            feature = str(case.content.get("feature_object", ""))
            if not feature.startswith("[implementation]"):
                continue
            row = connection.execute("SELECT trajectory_id, evidence_refs FROM reflection_cases WHERE case_id=?",
                                     (case.case_id,)).fetchone()
            labels: list[str] = []
            refs = json.loads(row["evidence_refs"] or "[]") if row else []
            cited = [item["setup"] for ref in refs if isinstance(ref, dict) and ref.get("kind") == "retrospective"
                     for item in ref.get("statistics", []) if isinstance(item, dict) and item.get("setup")]
            if cited:
                labels = [setup_label(s) for s in dict.fromkeys(cited)]
            elif row and has_runs:
                run = connection.execute("SELECT stack FROM run_facts WHERE trajectory_id=?",
                                         (row["trajectory_id"],)).fetchone()
                if run:
                    labels = [setup_label(run["stack"])]
            if feature == BUILD_FAILURE_FEATURE:
                labels.append(BUILD_FAILURE_LABEL)
            if labels:
                fixed[case.case_id] = labels
    return fixed


def order_by_cause_frequency(llm: Any, database: str | Path, agent_id: str, task_id: str,
                             cases: Sequence[Any], params: PriorityParams | None = None) -> tuple[list[Any], dict]:
    """Put guidance whose underlying problem occurs most often (recent, decayed) first.
    The problem category of each case is labelled with the same labels as the statistics table."""
    cases = list(cases)
    info: dict = {"applied": False}
    if len(cases) < 2:
        return cases, info
    summary = summarize(database, agent_id, task_id, params)
    scores = summary["cause_scores"]
    if not scores:
        return cases, info
    fixed = _fixed_labels(database, agent_id, cases)
    open_cases = [c for c in cases if c.case_id not in fixed]
    with connect_database(database, read_only=True) as connection:
        marks = ",".join("?" for _ in open_cases)
        causes = {row[0]: row[1] for row in connection.execute(
            f"SELECT case_id, root_cause_or_hypothesis FROM reflection_cases WHERE case_id IN ({marks})",
            tuple(c.case_id for c in open_cases))} if open_cases else {}
        existing = known_labels(connection, agent_id)
    open_labels = label_causes(llm, [causes.get(c.case_id, "") for c in open_cases], existing) if open_cases else []
    if len(open_labels) != len(open_cases):
        return cases, info
    by_id = {case_id: [label] for case_id, label in zip((c.case_id for c in open_cases), open_labels)} | fixed
    labels = [by_id[c.case_id] for c in cases]
    priority = [max((scores.get(label, 0.0) for label in group), default=0.0) for group in labels]
    order = sorted(range(len(cases)), key=lambda i: -priority[i])
    totals = summary.get("cause_totals", {})
    info = {"applied": True, "labels": {cases[i].case_id: labels[i] for i in range(len(cases))},
            "case_totals": {cases[i].case_id: round(max((totals.get(l, 0.0) for l in labels[i]), default=0.0), 3)
                            for i in range(len(cases))},
            "scores": {label: round(scores.get(label, 0.0), 3) for group in labels for label in group}}
    return [cases[i] for i in order], info


# ---- per-check facts: what kind of feature, on which stack, with what outcome -------------

_CHECK_LABEL_INSTRUCTIONS = """Label the functional checks of one website task. For each check give a
broad feature category of 1-3 words (the kind of feature, not this site's wording). Reuse an
existing category exactly whenever it fits; only add a new one when none fits. For each check that
did not pass, also say which of the listed problem cases explains it (its index), or null when
none does. Return JSON only: {"categories": [<one per check, same order>],
"case_for_check": [<case index or null, one per check, same order>]}."""


def known_categories(connection: Any, agent_id: str) -> list[str]:
    if not _has_table(connection, "check_facts"):
        return []
    counts: dict[str, int] = {}
    for row in connection.execute("SELECT category FROM check_facts WHERE agent_id=?", (agent_id,)):
        counts[row[0]] = counts.get(row[0], 0) + 1
    return [label for label, _ in sorted(counts.items(), key=lambda item: -item[1])]


def build_check_rows(llm: Any, existing_categories: Sequence[str], checks: Sequence[Mapping[str, Any]],
                     cases: Sequence[Mapping[str, Any]]) -> list[dict]:
    """checks: [{"index", "task", "outcome"}]; cases: reflection functional items (may be empty).
    Returns rows without stack/ids. evidence_source and requirement_stated come from the case that
    explains the check (grounded code evidence -> 'code'; grounded requirement quote -> stated)."""
    if not checks:
        return []
    result = llm.generate("check_labelling", {
        "instructions": _CHECK_LABEL_INSTRUCTIONS, "existing_categories": list(existing_categories),
        "checks": [{"index": c["index"], "task": c["task"], "outcome": c["outcome"]} for c in checks],
        "cases": [{"index": i, "feature": str(c.get("feature_object", "")),
                   "cause": str(c.get("likely_cause_or_limitation", ""))[:300]} for i, c in enumerate(cases)]})
    categories = result.get("categories") if isinstance(result, dict) else None
    links = result.get("case_for_check") if isinstance(result, dict) else None
    if not isinstance(categories, list) or len(categories) != len(checks):
        return []
    if not isinstance(links, list) or len(links) != len(checks):
        links = [None] * len(checks)
    rows = []
    for check, category, link in zip(checks, categories, links):
        case = cases[link] if isinstance(link, int) and 0 <= link < len(cases) else None
        source = stated = None
        if check["outcome"] != "passed" and case is not None:
            code = case.get("code_evidence")
            source = "code" if isinstance(code, dict) and code.get("grounded") else "operation"
            evidence = case.get("requirement_evidence")
            stated = int(isinstance(evidence, dict) and evidence.get("grounded") is True)
        rows.append({"check_index": int(check["index"]),
                     "category": re.sub(r"\s+", " ", str(category)).strip().lower() or "other",
                     "outcome": check["outcome"], "evidence_source": source, "requirement_stated": stated})
    return rows


def record_checks(database: str | Path, *, agent_id: str, task_id: str, trajectory_id: str,
                  stack: str, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    with connect_database(database, read_only=False) as connection:
        ensure_optional_tables(connection)
        for row in rows:
            connection.execute(
                "INSERT OR REPLACE INTO check_facts (fact_id,agent_id,task_id,trajectory_id,check_index,category,"
                "outcome,stack,evidence_source,requirement_stated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, agent_id, task_id, trajectory_id, row["check_index"], row["category"],
                 row["outcome"], stack, row["evidence_source"], row["requirement_stated"]))


def summarize_checks(database: str | Path, agent_id: str, current_task_id: str) -> dict:
    """Per feature category: pass counts by stack, and how many non-passing checks concerned
    expectations the public requirement did not state. Earlier tasks only."""
    with connect_database(database, read_only=True) as connection:
        if not _has_table(connection, "check_facts"):
            return {}
        rows = [dict(r) for r in connection.execute("SELECT * FROM check_facts WHERE agent_id=?", (agent_id,))
                if _other_task(r["task_id"], current_task_id)]
    categories: dict[str, dict] = {}
    for row in rows:
        entry = categories.setdefault(row["category"], {"checks": 0, "stacks": {}, "nonpass": 0, "unstated": 0})
        entry["checks"] += 1
        stack = entry["stacks"].setdefault(row["stack"], {"checks": 0, "passed": 0})
        stack["checks"] += 1
        stack["passed"] += row["outcome"] == "passed"
        if row["outcome"] != "passed":
            entry["nonpass"] += 1
            entry["unstated"] += row["requirement_stated"] == 0
    return categories


def guidance_effects(database: str | Path, agent_id: str, current_task_id: str) -> list[dict]:
    """Internal statistic (not shown to the generator): for each memory item that was in the prompt of some
    earlier run, the pass counts per feature category in runs WITH that item versus runs WITHOUT it.
    Correlational; runs whose prompt was not delivered count as 'without'."""
    with connect_database(database, read_only=True) as connection:
        if not (_has_table(connection) and _has_table(connection, "check_facts")):
            return []
        runs = {r["trajectory_id"]: dict(r) for r in connection.execute(
            "SELECT * FROM run_facts WHERE agent_id=?", (agent_id,)) if _other_task(r["task_id"], current_task_id)}
        checks = [dict(r) for r in connection.execute("SELECT * FROM check_facts WHERE agent_id=?", (agent_id,))
                  if r["trajectory_id"] in runs]
    guided = {tid: set(json.loads(run["guidance_case_ids"] or "[]")) if run["prompt_delivered"] else set()
              for tid, run in runs.items()}
    result = []
    for case_id in sorted({c for ids in guided.values() for c in ids}):
        cells: dict[str, dict[str, list[int]]] = {}
        for check in checks:
            side = "with" if case_id in guided[check["trajectory_id"]] else "without"
            cell = cells.setdefault(check["category"], {"with": [0, 0], "without": [0, 0]})
            cell[side][1] += 1
            cell[side][0] += check["outcome"] == "passed"
        rows = [{"category": cat, "with": v["with"], "without": v["without"]} for cat, v in cells.items()
                if v["with"][1] and v["without"][1]]
        if rows:
            result.append({"case_id": case_id, "by_category": rows})
    return result
