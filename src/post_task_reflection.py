"""Post-task case reflection for continual long-memory construction.

Reflection is created only *after* a website receives its locked evaluation.  It is
an archive for later tasks, never feedback to regenerate the same website.  Raw
model output is retained even when a locator cannot be resolved exactly: losing a
useful case because an LLM expressed a locator differently is worse than recording
it with an explicit provenance warning.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


REFLECTION_INSTRUCTIONS = """Produce one detailed post-task case reflection for a
continual website-generation memory system. The website has already received its
final locked evaluation and MUST NOT be repaired or regenerated. Use only the
supplied public requirement, GUI trajectory, final evaluation evidence and
screenshot-based appearance feedback. Never repeat hidden expected answers.

This is not a generic project summary. Preserve the task case: requirement scope,
feature object, user trigger, expected state change, observed result, and a
confirmed root cause or clearly labelled hypothesis. Cover meaningful success as
well as partial/failing behaviour. A success is useful only when it explains a
non-trivial operation or visible design decision that another task can reuse.

Return two independent channels:
1) task_summary: concise requirement coverage, verified strengths, main functional
risks, and visible observations.
2) appearance_reflection: score/feedback -> visible strength or weakness -> future
design action -> future visual validation. Do not infer functional behaviour from a
screenshot.
3) functional_reflections: one related user-flow cluster each, not scattered UI
atoms. For every cluster give feature_object, user_trigger, expected_state_change,
observed_result, outcome (success|partial|failure), likely_cause_or_limitation,
preventative_action, verification, and transfer_limits. Infrastructure, provider,
port and timeout failures are not website lessons.

Return JSON only:
{"task_summary":{"requirement_coverage":str,"verified_strengths":[str],
"primary_functional_risks":[str],"primary_visual_observations":[str]},
"appearance_reflection":null|{"observed_result":str,"likely_cause_or_limitation":str,
"preventative_action":str,"verification":str,"transfer_limits":str,
"evidence_refs":[supplied refs]},
"functional_reflections":[{"feature_object":str,"user_trigger":str,
"expected_state_change":str,"observed_result":str,
"outcome":"success|partial|failure","likely_cause_or_limitation":str,
"preventative_action":str,"verification":str,"transfer_limits":str,
"evidence_refs":[supplied refs]}]}.
Use at most three functional clusters. Evidence refs should use supplied refs, but
do not omit a useful concrete observation merely because its locator is uncertain."""


_FUNCTIONAL_FIELDS = (
    "feature_object", "user_trigger", "expected_state_change", "observed_result",
    "outcome", "likely_cause_or_limitation", "preventative_action", "verification",
    "transfer_limits",
)
_APPEARANCE_FIELDS = (
    "observed_result", "likely_cause_or_limitation", "preventative_action",
    "verification", "transfer_limits",
)


def _clean_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _task_summary(value: object) -> dict:
    value = value if isinstance(value, dict) else {}
    coverage = value.get("requirement_coverage", "")
    return {
        "requirement_coverage": coverage.strip() if isinstance(coverage, str) else "",
        "verified_strengths": _clean_strings(value.get("verified_strengths")),
        "primary_functional_risks": _clean_strings(value.get("primary_functional_risks")),
        "primary_visual_observations": _clean_strings(value.get("primary_visual_observations")),
    }


def _resolve_refs(refs: object, evidence: list[dict]) -> tuple[list[dict], str]:
    """Resolve exact or conventional locator variants without silently dropping case.

    A raw reflection remains archived even when this returns ``unresolved``.  Only
    ``exact_or_normalised`` items become strict extraction evidence.
    """
    if not isinstance(refs, list):
        return [], "unresolved"
    available = [item.get("ref") for item in evidence if isinstance(item.get("ref"), dict)]
    exact = {_json(ref): ref for ref in available}
    # Evaluator records expose their GUI transcript via ``content.evidence``.
    # A reflection model sometimes copies that path rather than the compact ref
    # object. It is still an unambiguous reference to supplied evidence.
    evidence_paths = {
        item["content"].get("evidence"): item["ref"]
        for item in evidence
        if isinstance(item.get("ref"), dict) and isinstance(item.get("content"), dict)
        and isinstance(item["content"].get("evidence"), str)
    }
    resolved: list[dict] = []
    seen: set[str] = set()
    for supplied in refs:
        if isinstance(supplied, str):
            match = evidence_paths.get(supplied)
            candidate = None
        elif isinstance(supplied, dict):
            candidate = supplied.get("ref") if isinstance(supplied.get("ref"), dict) else supplied
            match = exact.get(_json(candidate))
        else:
            continue
        if match is None:
            for ref in available:
                # Models commonly use check/message/result indices without the
                # wrapper kind/role.  Accept only an unambiguous conventional match.
                keys = ("check", "message_index", "result_index", "step_id")
                if isinstance(candidate, dict) and any(
                    key in candidate and candidate.get(key) == ref.get(key) for key in keys
                ):
                    match = ref
                    break
        if match is not None and _json(match) not in seen:
            resolved.append(match)
            seen.add(_json(match))
    return resolved, "exact_or_normalised" if resolved else "unresolved"


def _complete(item: object, fields: tuple[str, ...]) -> bool:
    return isinstance(item, dict) and all(
        isinstance(item.get(field), str) and item[field].strip() for field in fields
    )


def _normalise_functional(item: object, evidence: list[dict]) -> dict | None:
    if not _complete(item, _FUNCTIONAL_FIELDS):
        return None
    assert isinstance(item, dict)
    if item["outcome"].strip().lower() not in ("success", "partial", "failure"):
        return None
    refs, provenance_status = _resolve_refs(item.get("evidence_refs"), evidence)
    return {
        **{key: item[key].strip() for key in _FUNCTIONAL_FIELDS},
        "outcome": item["outcome"].strip().lower(),
        "evidence_refs": refs,
        "provenance_status": provenance_status,
        "accepted_for_memory": bool(refs),
    }


def _normalise_appearance(item: object, evidence: list[dict]) -> dict | None:
    if not _complete(item, _APPEARANCE_FIELDS):
        return None
    assert isinstance(item, dict)
    refs, provenance_status = _resolve_refs(item.get("evidence_refs"), evidence)
    return {
        "channel": "appearance",
        **{key: item[key].strip() for key in _APPEARANCE_FIELDS},
        "evidence_refs": refs,
        "provenance_status": provenance_status,
        "accepted_for_memory": bool(refs),
    }


def create_reflection(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict]) -> dict:
    """Create a source-aware case archive without writing to the database."""
    result = llm.generate("post_task_reflection", {
        "instructions": REFLECTION_INSTRUCTIONS,
        "public_task_requirement": str(trajectory["task_request"]),
        "trajectory_id": str(trajectory["trajectory_id"]),
        "evaluation_results": trajectory.get("evaluation_results", ""),
        "evidence": evidence,
    })
    if not isinstance(result, dict):
        raise ValueError("Post-task reflection must return a JSON object")
    functional = []
    raw_functional = result.get("functional_reflections", [])
    if isinstance(raw_functional, list):
        for item in raw_functional[:3]:
            normalised = _normalise_functional(item, evidence)
            if normalised is not None:
                functional.append(normalised)
    appearance = _normalise_appearance(result.get("appearance_reflection"), evidence)
    reflections = ([appearance] if appearance is not None else []) + functional
    accepted = [item for item in reflections if item["accepted_for_memory"]]
    return {
        "reflection_id": uuid.uuid4().hex,
        "trajectory_id": str(trajectory["trajectory_id"]),
        "public_task_requirement": str(trajectory["task_request"]),
        "task_summary": _task_summary(result.get("task_summary")),
        "appearance_reflection": appearance,
        "functional_reflections": functional,
        "accepted_reflections": accepted,
        # ``reflections`` is retained for old readers; it is now the complete
        # archived set, not only strict-provenance records.
        "reflections": reflections,
        "accepted_reflection_count": len(accepted),
        "raw_reflection_count": len(reflections),
        "raw_model_output": result,
    }


def append_reflection(path: Path, reflection: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(_json(dict(reflection)) + "\n")


def reflective_evidence_loader(base_loader: Callable[[dict], list[dict]],
                               artifact_path: Path) -> Callable[[dict], list[dict]]:
    """Attach the complete case archive as secondary, provenance-linked evidence."""
    def load(trajectory: dict) -> list[dict]:
        evidence = list(base_loader(trajectory))
        if not artifact_path.is_file():
            return evidence
        selected = None
        for line in artifact_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = json.loads(line)
                if event.get("trajectory_id") == trajectory["trajectory_id"]:
                    selected = event
        if selected:
            evidence.append({
                "ref": {"kind": "post_task_case", "reflection_id": selected["reflection_id"]},
                "content": selected,
            })
        return evidence
    return load
