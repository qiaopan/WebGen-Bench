"""Long Memory arm only: turn a generation that never built into memory, and offer memory at repair time.

A generation that fails validation after all repair attempts used to abort the run and leave
no trace. Here it is recorded as a trajectory (``execution_error``), counted as all checks
failed, and reflected on: the build errors plus the source files they name become one
``[implementation]`` case that later tasks can retrieve through the fixed ``build`` aspect.
During repair retries the same case library (and the statistics table) supplies a hint.
"""
from __future__ import annotations

import json
import math
import re
import struct
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from memory_statistics import BUILD_FAILURE_FEATURE
from reflection_case_memory import IMPLEMENTATION_MARKER

FAILURE_REFLECTION_INSTRUCTIONS = """A generated website did not build or start, even after repair
attempts. You are given the public requirement, the validation errors of each attempt, the
project's technology stack and the source of the files named in the errors. Explain the failure
as a developer would for a teammate who will build a similar website next week. Name the concrete
mechanism visible in the errors or the code (for example which kind of file uses something its
framework cannot provide), not a guess. preventative_action is 1-2 sentences: a generalizable
implementation requirement that starts with "Implement" or "Use" and applies to any website built
the same way, without this site's content, page names or example values. If a line of code
explains the failure, code_evidence = {"file": <path>, "snippet": <that line copied verbatim>},
else null. Return JSON only: {"observed_result": str, "likely_cause_or_limitation": str,
"preventative_action": str, "verification": str, "transfer_limits": str,
"code_evidence": null|{"file": str, "snippet": str}}."""

_FIELDS = ("observed_result", "likely_cause_or_limitation", "preventative_action",
           "verification", "transfer_limits")
_SOURCE = re.compile(r"(?:src|app|pages)/[\w./\[\]@-]+\.(?:astro|jsx|tsx|js|ts|vue|svelte|mjs)")


def _tail(text: str, size: int) -> str:
    return text[-size:] if len(text) > size else text


def failed_generation_evidence(destination: Path, task_number: int = 1) -> dict:
    """Attempt reports plus the source files that the errors name, from our own failed archives."""
    prefix = f"{task_number:06d}"
    report_path = destination / f"{prefix}.generation.json"
    attempts = []
    if report_path.is_file():
        attempts = json.loads(report_path.read_text(encoding="utf-8")).get("attempts", [])
    archives = sorted(destination.glob(f"{prefix}.attempt-*.failed.zip"))
    files: dict[str, str] = {}
    if archives:
        with zipfile.ZipFile(archives[-1]) as bundle:
            names = [n for n in bundle.namelist() if not n.endswith("/")]
            named = []
            for attempt in reversed(attempts):
                named += _SOURCE.findall(str(attempt.get("error", "")))
            for wanted in dict.fromkeys(named):
                match = next((n for n in names if n.endswith(wanted) and "node_modules" not in n), None)
                if match and len(files) < 3:
                    files[match] = bundle.read(match).decode("utf-8", "replace")[:4000]
    return {"attempts": [{"attempt": a.get("attempt"), "phase": a.get("phase"),
                          "error": _tail(str(a.get("error", "")), 1500)} for a in attempts],
            "files": files, "archive": str(archives[-1]) if archives else "", "report": str(report_path)}


def failure_reflection(llm: Any, task: str, trajectory_id: str, stack: str, evidence: dict) -> dict | None:
    """Reflection dict shaped like post_task_reflection output; None if no usable lesson."""
    result = llm.generate("generation_failure_reflection", {
        "instructions": FAILURE_REFLECTION_INSTRUCTIONS, "public_requirement": task,
        "stack": stack, "attempts": evidence["attempts"], "code_files": evidence["files"]})
    if not isinstance(result, dict) or not all(str(result.get(f, "")).strip() for f in _FIELDS):
        return None
    code = result.get("code_evidence")
    if isinstance(code, dict):
        source = evidence["files"].get(str(code.get("file", "")), "")
        code = {**code, "grounded": bool(str(code.get("snippet", "")).strip() and code["snippet"] in source)}
    else:
        code = None
    case = {"feature_object": BUILD_FAILURE_FEATURE,
            "user_trigger": "Install, build and start the generated project",
            "expected_state_change": "The build succeeds and the first page renders without errors",
            "outcome": "failure", "evidence_refs": [], "provenance_status": "unresolved",
            "code_evidence": code, **{f: str(result[f]).strip() for f in _FIELDS}}
    return {"reflection_id": uuid.uuid4().hex, "trajectory_id": trajectory_id, "public_task_requirement": task,
            "task_summary": {}, "appearance_reflection": None, "functional_reflections": [],
            "implementation_reflection": case, "accepted_reflections": [case],
            "accepted_reflection_count": 1, "raw_reflection_count": 1, "kind": "generation_failure"}


def failed_evaluation(task: dict) -> list[dict]:
    """A generation that never ran counts as every functional check failed."""
    checks = [{"check": f"task000001_{index}", "outcome": "failed", "answer": "generation failed before evaluation",
               "failure_stage": "generation", "failure_type": "generation_failed",
               "failure_reason": "The generated project never built or started",
               "reached_target_action": False, "logic_failure_observed": False}
              for index in range(len(task.get("ui_instruct", [])))]
    return checks + [{"check": "appearance", "outcome": "scored", "score": None,
                      "failure_stage": "generation", "failure_type": "generation_failed"}]


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / norm if norm else 0.0


def repair_hint_factory(database: str, agent_id: str, embedder: Any, current_task_id: str,
                        *, top_k: int = 2, min_similarity: float = 0.35) -> Callable[[dict, str, int], str]:
    """Hook for repair retries: earlier build-failure lessons that resemble this error, plus the
    recorded outcome statistics for this stack. Facts and past lessons only."""
    from long_memory import connect_database
    from memory_statistics import _has_table, detect_stack, summarize

    def hint(report: dict, archive: str, attempt: int) -> str:
        error = f"{report.get('phase', '')}: {str(report.get('error', ''))[-1500:]}"
        try:
            query = tuple(float(x) for x in embedder.embed([error])[0])
        except Exception:
            return ""
        with connect_database(database, read_only=True) as connection:
            rows = [dict(r) for r in connection.execute(
                "SELECT case_id, preventative_action, observed_result, embedding FROM reflection_cases "
                "WHERE agent_id=? AND status='active' AND channel='functional' AND feature_object LIKE ?",
                (agent_id, IMPLEMENTATION_MARKER + "%"))]
        scored = []
        for row in rows:
            vector = struct.unpack(f"<{len(row['embedding']) // 4}f", row["embedding"])
            if len(vector) == len(query):
                scored.append((_cosine(query, vector), row))
        picked = [row for score, row in sorted(scored, key=lambda item: -item[0])[:top_k] if score >= min_similarity]
        lines = [f"- Earlier failure: {r['observed_result']} Lesson: {r['preventative_action']}" for r in picked]
        stack = detect_stack(archive) if archive else "unknown"
        facts = summarize(database, agent_id, current_task_id)["stacks"].get(stack)
        if facts and facts["runs"] >= 2:
            lines.append(f"- Recorded outcomes for stack {stack}: {facts['runs']} earlier generations, "
                         f"{facts['generation_failed']} did not produce a working project.")
        if not lines:
            return ""
        return (f"\n\nNOTES FROM EARLIER GENERATIONS (repair attempt {attempt}; past lessons and recorded "
                "counts, use only where they match the error above):\n" + "\n".join(lines) + "\n")

    return hint
