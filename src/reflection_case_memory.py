"""Concrete reflection-case memory used for the Case-only ablation.

Cases retain a task's requirement context and observed user flow.  They are not
Experience/Skill replacements in the main system: this small component exists so
the experiment can test whether direct cross-task cases help more than an extra
abstraction layer on short website-generation tasks.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import struct
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from long_memory import connect_database, ensure_optional_tables
from long_memory_runtime import MemoryConfig


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _vector(values: Sequence[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector or not all(math.isfinite(value) for value in vector):
        raise ValueError("Embedding must contain finite numbers")
    length = math.hypot(*vector)
    if not math.isfinite(length) or length == 0:
        raise ValueError("Embedding must have finite nonzero norm")
    return tuple(value / length for value in vector)


# Implementation-approach cases share the "functional" channel (the schema only allows
# functional/appearance) and are told apart by this prefix on feature_object.
IMPLEMENTATION_MARKER = "[implementation]"

CASE_ASPECT_INSTRUCTIONS = """Decompose a public website-generation requirement
into a small set of explicit, implementable retrieval aspects. Do not invent hidden
tests, business details, or implementation steps. Functional aspects must state a
feature object, a user trigger, an expected visible state change, and a
pattern_query: one short sentence that names the generic interaction pattern with
no business nouns (for example "submitting a form shows a visible confirmation",
"looking up a record by its ID shows its current status", "selecting an item shows
its details"). Appearance aspects must state a concrete visual requirement. Return
JSON only:
{"functional_aspects":[{"feature_object":str,"user_trigger":str,
"expected_state_change":str,"pattern_query":str}],
"appearance_aspects":[{"visual_requirement":str}],"interactive":bool}.
interactive is true when any functional aspect needs the page to react to user input
in the browser (form submission, search, lookup by an ID, filtering, toggling).
Enumerate every explicit functional object and every concrete visual requirement in
the public requirement; do not merge or omit aspects to satisfy a count limit. Empty
lists are valid only when that channel is absent."""

CASE_FUNCTIONAL_RELEVANCE_INSTRUCTIONS = """Judge historical functional cases against ONE
current functional aspect. The aspect carries a domain-free pattern_query naming the
interaction pattern; compare each candidate with that pattern and with the aspect's
user_trigger and expected_state_change. feature_object, page names and business
nouns are only labels and may differ: a newsletter form that shows a thank-you
message, a contact form and a booking form that shows a confirmation are all
"submit a form and see a visible result", so they match; a product-detail view and
a service-detail view likewise. A historical failure lesson transfers whenever the
same kind of interaction is involved (form submission and its feedback, lookup by
an ID, list ordering, detail view, navigation), even if the business content or the
exact field differs. Choose reject only when the interaction pattern is clearly
different (for example static text vs a form). When unsure between soft_transfer
and reject for the same kind of interaction, choose soft_transfer: a later stage
still removes details that do not apply. Judge EVERY candidate. Verdict is one of
hard_match (same trigger and state change), soft_transfer (same kind of
interaction or the same failure mode), reject. Return JSON only, in exactly this
shape:
{"decisions":[{"case_id":str,"verdict":str,"matched_current_requirement":str,
"reason":str,"implementation_checks":[str]}]}
with exactly one entry per candidate and 1-3 current-task implementation_checks
for selected candidates."""

CASE_APPEARANCE_RELEVANCE_INSTRUCTIONS = """Judge historical appearance cases against ONE
current appearance aspect. Compare the design principle behind each case's
preventative_action with the aspect. A different colour palette alone is not a match
for a colour aspect. But a case whose principle applies to the aspect matches even
when the specific features or content it mentions differ: for example a case saying
"the first screen must show the required lead form" matches an aspect asking that
the first screen presents this task's required features, because the principle
(key required features visible on the first screen) is the same. Do not select
merely because both tasks are websites, and do not select generic style advice with
no specific requirement. Judge EVERY candidate. Verdict is one of hard_match,
soft_transfer, reject. Return JSON only, in exactly this shape:
{"decisions":[{"case_id":str,"verdict":str,"matched_current_requirement":str,
"reason":str,"implementation_checks":[str]}]}
with exactly one entry per candidate and 1-3 current-task implementation_checks
for selected candidates."""

CASE_BUILD_RELEVANCE_INSTRUCTIONS = """Judge historical implementation cases against ONE
current implementation aspect (how the site must be built so that its interactive
features work in the browser). An implementation case is about the way a site is built:
the kind of setup interactive features need and what every interactive feature must
contain. It matches when that lesson applies to the current interactive features, even
if the concrete features differ (a case about forms with no client-side handler
applies to any form). Reject cases about unrelated matters such as content, layout or
colours. A case about a build or start-up failure matches whenever the current site could be
built with the same kind of setup: the setup is the generator's own choice, so the current task
not naming it is not a reason to reject. Judge EVERY candidate. Verdict is one of hard_match, soft_transfer, reject.
Return JSON only, in exactly this shape:
{"decisions":[{"case_id":str,"verdict":str,"matched_current_requirement":str,
"reason":str,"implementation_checks":[str]}]}
with exactly one entry per candidate and 1-3 current-task implementation_checks
for selected candidates."""

COMMON_POOL_ADAPTATION_INSTRUCTIONS = """You maintain a short list of implementation pitfalls that apply to ANY
website, whatever its features. You get historical implementation cases (how earlier websites were
built and what went wrong), ordered by priority, most important first. Merge and rewrite them into at
most max_patterns declarative requirements for a one-shot code generator that cannot run or observe
the site. Each starts with "Implement", "Use" or "Ensure" (or "If" when conditional, see below). When the cases name a concrete choice (which
kind of setup to use or avoid, what an interactive component must contain, what a build needs), keep
that choice and its names. Include no website's content, page names or example values. Prefer the
higher-priority cases; drop a case only if another one already covers it or it is not an
implementation-level lesson.
Generalise: a case may mix a site-wide lesson with details of one feature (for example "every
required section needs its own navigation entry, and the contact form must show its fields above the
fold"). Keep only the part that holds for any website (the navigation entry for every section) and drop
the feature-specific part (the contact form): feature lessons reach later tasks by feature match, not
through this list. Several cases that state the same site-wide lesson become one requirement.
Conditions: a lesson that holds for every website that has interactive features is written without a
condition. A lesson that only matters when the website has a certain kind of feature or takes a certain
approach (for example when data created by one feature must be found again by another) is written as
"If the website <condition the builder can judge from what it is building>, <requirement>", so that a
builder whose website does not meet the condition can skip it. Never state a condition in terms of a
label the builder cannot know in advance. A condition is for how the site is built (setup, data
flow, rendering), never a way to keep how one feature should behave ("If the website has a news
section, it must render articles" is a feature lesson: drop it). Return JSON only:
{"patterns":[{"implementation_pattern":str,"source_case_ids":[str]}]}."""

IMPLEMENTATION_LESSON_GROUP_INSTRUCTIONS = """Group implementation lessons that state the SAME underlying requirement for a
website's build (for example "validate forms inline, never with a blocking browser alert" is one lesson
even if two tasks worded it differently and mention different forms). Different requirements stay in
different groups; a lesson that matches no other stays alone. Every case_id appears in exactly one
group. Return JSON only: {"groups":[{"case_ids":[str],"lesson":str}]}."""

CASE_APPEARANCE_SAME_LESSON_INSTRUCTIONS = """Decide whether a NEW appearance case states the
SAME design lesson as one of the EXISTING appearance cases. Two cases state the same
lesson when their preventative_action requires the same underlying design principle
(for example "the first screen must show the task's key required features"), even if
the concrete features, page names or business content they mention differ. They are
different lessons when the principle differs (for example first-screen content vs
colour matching vs typography). Return JSON only:
{"same_as": <case_id of the matching existing case, or null>, "reason": str}."""

CASE_IMPLEMENTATION_ADAPTATION_INSTRUCTIONS = """You are the second-stage memory
reviewer. The current task and its aspects are binding. For each selected historical
case, separate its CONCRETE details (specific fields, controls, data formats,
business content, colours, layout) from its TRANSFERABLE lesson (the behaviour or
quality condition that would also make the current aspect work).
1. Drop every concrete detail that the current requirement does not contain (for
example a phone-number input when the task only needs a tap-to-call link, a
date-of-birth field or SSN digits the task never mentions).
2. Keep the transferable lesson and restate it for the matched current aspect, using
only the current task's own features and wording. The case's preventative action names
the element the earlier site lacked (for example a navigation entry for every section, a
submit handler, a timer that advances a carousel); that missing element is the core of the
lesson and must still be named in your pattern. Do not replace it with a weaker visibility
or quality condition (for example "a section becomes visible when scrolled to" in place of
"every section has its own navigation entry"). Keep the case's qualifiers: do not turn a limited statement into an
absolute one (for example "show the form on the first screen, not only behind navigation" must not
become "no navigation is needed"), and never add a requirement that removes or contradicts something
the current requirement asks for or that other guidance needs, such as navigation. Typical transferable lessons:
show a visible confirmation or result after a submit; make a lookup find the data
that was just created or stored; do not reject valid input and show accepted
formats and visible errors; show details for the selected item and a way to leave
them; keep the flow short for an automated tester.
3. matched_aspect is the single current aspect this case is being adapted for. Write
the pattern for that aspect only; do not merge in other aspects and do not re-map it
to another one. Set applicable=false only when no transferable lesson relates to it.
An implementation case (feature_object starts with "[implementation]") concerns how the
site is built: keep its pattern at that level (which kind of setup to use and what every
interactive feature must contain), not a single page's content. When the case names a
concrete setup to use or avoid, keep those names in the pattern.
Write implementation_pattern as one short declarative implementation requirement
for a one-shot code generator that cannot run, test, or observe the site. Use the
form "Implement / Provide / Include <component, state, rendered content, control>
so that <condition>": say what the code must contain and what the rendered page
must show. Name the concrete element or state that must exist and when it appears, in one
sentence about one behaviour, rather than describing qualities such as clear or persistent. Do NOT narrate a user session ("when a user does X, then ..."), and do
not use tester or runtime verbs (run, test, verify, check that, fix, click, select,
open, observe, navigate); feature names such as "service status check" are fine.
It must not mention any field, control or feature that the current requirement
lacks, and must not copy old wording, colours, or layout. Historical trigger and
verification text is evidence only; convert it into what must be built. When the case
shows the flow was slow or incomplete for an automated tester (many fields,
hard-to-fill inputs such as date pickers, strict formats, extra steps), also keep
only the fields and steps the current requirement needs, avoid extra required
inputs, and keep the target result reachable in as few interactions as possible.
Return JSON only:
{"patterns":[{"case_id":str,"applicable":bool,"reason":str,
"implementation_pattern":str}]}
with one entry per selected case; implementation_pattern may be empty when
applicable=false."""

CASE_CONSOLIDATION_INSTRUCTIONS = """Review one newly completed website task against
older partial or failed reflection cases. Find only a concrete recurring interaction
or visual failure mode. Business domains may differ, but the user trigger and
expected visible state must transfer. Do not infer a pattern from merely both being
websites or forms. Return JSON only:
{"decision":"none|experience|skill","source_case_ids":[str],
"missed_retrieval_reason":str,"experience":null|{"condition":str,"lesson":str,
"recommended_action":str,"verification":str},"skill":null|{"goal":str,
"conditions":str,"workflow":[str],"completion_checks":[str]}}.
Use decision=none unless at least one older case and the new case share a specific
failure mode. Candidate output is advisory only; it must not alter the current task."""


# Target length of one condensed guidance item after its "Part:" prefix (characters).
ITEM_MAX_CHARS = 90


@dataclass(frozen=True)
class RetrievedCase:
    case_id: str
    content: dict
    similarity: float


@dataclass(frozen=True)
class CasePacket:
    cases: tuple[RetrievedCase, ...] = ()
    # BoltAgentAdapter accepts both abstract memory packets and case packets.
    experiences: tuple = ()
    skills: tuple = ()
    # Task-independent implementation pitfalls (already rewritten, one requirement per entry).
    common: tuple[str, ...] = ()
    common_case_ids: tuple[str, ...] = ()  # source cases of the common lines (for run records)
    # Statistical memory: recorded facts about earlier runs (see memory_statistics.py).
    statistics: str = ""

    guidance_header = (
        "\n\nIMPLEMENTATION GUIDANCE FROM PAST TASKS:\n"
        "The requirement above has priority: build everything it lists. These notes only flag "
        "parts earlier websites got wrong; they are not the full list.\n"
    )
    common_header = (
        "\n\nCOMMON IMPLEMENTATION PITFALLS FROM EARLIER WEBSITES:\n"
        "These come from problems that earlier websites ran into. A line that starts with \"If\" applies "
        "only when its condition is true of the website you are building; otherwise ignore that line. "
        "Follow the other lines as part of this website.\n"
    )
    statistics_header = (
        "\n\nRECORDED OUTCOMES OF EARLIER GENERATIONS (counts from earlier tasks, not requirements):\n"
        "These are facts about how earlier websites turned out; they show correlation, not proof. "
        "Weigh them when choosing how to implement this website.\n"
    )

    def _sections(self) -> list[tuple[str, str]]:
        lines = []
        for item in self.cases:
            pattern = str(item.content.get("implementation_pattern", "")).strip()
            if pattern:
                # No source tag ([functional]/[common]): it means nothing to the generator; provenance
                # stays in the run log.
                lines.append(f"- {pattern}")
        sections = [(self.guidance_header, "\n".join(lines)),
                    (self.common_header, "\n".join(f"- {text}" for text in self.common if text.strip())),
                    (self.statistics_header, self.statistics)]
        return [(header, text) for header, text in sections if text]

    @property
    def injection_header(self) -> str:
        sections = self._sections()
        return sections[0][0] if sections else self.guidance_header

    # Repeated at the end: models use the start and the end of a prompt best (Liu et al., Lost in the Middle).
    guidance_footer = "\n\nReminder: build every page and feature the requirement lists, not only these."

    def render(self) -> str:
        sections = self._sections()
        if not sections:
            return ""
        return (sections[0][1] + "".join(header + text for header, text in sections[1:])
                + self.guidance_footer)


class ReflectionCaseMemory:
    def __init__(self, database: str, agent_id: str, *, llm: Any, embedder: Any,
                 config: MemoryConfig, log: Callable[[dict], None] | None = None):
        self.database = database
        self.statistics_task_id: str | None = None  # current task id; enables statistics and the time cutoff
        self.excluded_by_cutoff: set[str] = set()
        self.connection = connect_database(database, read_only=False)
        ensure_optional_tables(self.connection)
        self.agent_id, self.llm, self.embedder, self.config = agent_id, llm, embedder, config
        self.log = log or (lambda _: None)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ReflectionCaseMemory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = [_vector(value) for value in self.embedder.embed(texts)]
        if len(vectors) != len(texts) or len({len(value) for value in vectors}) != 1:
            raise ValueError("Embedder returned inconsistent case vectors")
        return vectors

    @staticmethod
    def _content(task_requirement: str, item: Mapping[str, Any], *, appearance: bool) -> dict:
        if appearance:
            return {
                "case_type": "appearance", "task_requirement": task_requirement,
                "feature_object": "visible website appearance", "user_trigger": "View the rendered page",
                "expected_state_change": "The rendered page visibly satisfies the requested design.",
                "observed_result": item["observed_result"],
                "root_cause_or_hypothesis": item["likely_cause_or_limitation"],
                "preventative_action": item["preventative_action"], "verification": item["verification"],
                "transfer_limits": item["transfer_limits"], "outcome": "observation",
            }
        return {
            "case_type": "functional", "task_requirement": task_requirement,
            "feature_object": item["feature_object"], "user_trigger": item["user_trigger"],
            "expected_state_change": item["expected_state_change"],
            "observed_result": item["observed_result"],
            "root_cause_or_hypothesis": item["likely_cause_or_limitation"],
            "preventative_action": item["preventative_action"], "verification": item["verification"],
            "transfer_limits": item["transfer_limits"], "outcome": item["outcome"],
        }

    def _drop_duplicate_appearance(self, cases: list, reflection: Mapping[str, Any]) -> list:
        """Appearance advice repeats across tasks. A new appearance case that states the same
        design lesson as an existing one is not stored; it is logged as support for that case."""
        kept = []
        for content, item in cases:
            if content["case_type"] != "appearance":
                kept.append((content, item))
                continue
            existing = [dict(row) for row in self.connection.execute(
                "SELECT case_id, preventative_action FROM reflection_cases "
                "WHERE agent_id=? AND status='active' AND channel='appearance'", (self.agent_id,))]
            same_as = None
            if existing:
                result = self.llm.generate("case_appearance_same_lesson", {
                    "instructions": CASE_APPEARANCE_SAME_LESSON_INSTRUCTIONS,
                    "new_case": {"observed_result": content["observed_result"],
                                 "preventative_action": content["preventative_action"]},
                    "existing_cases": [{"case_id": row["case_id"],
                                        "preventative_action": row["preventative_action"]} for row in existing]})
                candidate = result.get("same_as") if isinstance(result, dict) else None
                if candidate in {row["case_id"] for row in existing}:
                    same_as = candidate
            if same_as is None:
                kept.append((content, item))
            else:
                support_id = uuid.uuid4().hex
                with self.connection:
                    self.connection.execute(
                        "INSERT INTO case_supports "
                        "(support_id,agent_id,supported_case_id,supporting_trajectory_id,channel,"
                        "observed_result,preventative_action,evidence_refs) VALUES (?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(agent_id,supported_case_id,supporting_trajectory_id,preventative_action) "
                        "DO NOTHING",
                        (support_id, self.agent_id, same_as, reflection["trajectory_id"], "appearance",
                         content["observed_result"], content["preventative_action"],
                         _json(item.get("evidence_refs", []))),
                    )
                self.log({"operation": "case_supported", "agent_id": self.agent_id,
                          "trajectory_id": reflection["trajectory_id"], "supports_case_id": same_as,
                          "support_id": support_id, "new_preventative_action": content["preventative_action"]})
        return kept

    def store(self, reflection: Mapping[str, Any]) -> list[str]:
        """Store complete structured cases; no Experience/Skill abstraction occurs."""
        task = str(reflection["public_task_requirement"])
        source: list[tuple[Mapping[str, Any], bool]] = []
        if isinstance(reflection.get("appearance_reflections"), list):
            source.extend((item, True) for item in reflection["appearance_reflections"] if isinstance(item, dict))
        elif isinstance(reflection.get("appearance_reflection"), dict):
            source.append((reflection["appearance_reflection"], True))
        # Passed functional checks are not memory: only partial/failure cases are stored.
        source.extend((item, False) for item in reflection.get("functional_reflections", [])
                      if isinstance(item, dict) and item.get("outcome") != "success")
        if isinstance(reflection.get("implementation_reflection"), dict):
            source.append((reflection["implementation_reflection"], False))
        cases = [(self._content(task, item, appearance=appearance), item)
                 for item, appearance in source]
        cases = self._drop_duplicate_appearance(cases, reflection)
        if not cases:
            return []
        texts = [_json(content) for content, _ in cases]
        vectors = self._embed(texts)
        created: list[str] = []
        with self.connection:
            for (content, source_item), text, vector in zip(cases, texts, vectors):
                case_id = uuid.uuid4().hex
                row = {
                    "case_id": case_id, "trajectory_id": reflection["trajectory_id"],
                    "agent_id": self.agent_id,
                    "channel": "appearance" if content["case_type"] == "appearance" else "functional",
                    "outcome": content["outcome"], "task_requirement": task,
                    "feature_object": content["feature_object"], "user_trigger": content["user_trigger"],
                    "expected_state_change": content["expected_state_change"],
                    "observed_result": content["observed_result"],
                    "root_cause_or_hypothesis": content["root_cause_or_hypothesis"],
                    "preventative_action": content["preventative_action"],
                    "verification": content["verification"], "transfer_limits": content["transfer_limits"],
                    "evidence_refs": _json(source_item.get("evidence_refs", [])),
                    "provenance_status": source_item.get("provenance_status", "unresolved"),
                    # Uncertain causes stay on record for audit but are never retrieved.
                    "status": "archived" if source_item.get("cause_confidence") == "uncertain" else "active",
                    "embedding": struct.pack(f"<{len(vector)}f", *vector),
                    "embedding_model": self.embedder.model_id, "embedding_dim": len(vector),
                    "embedding_text_hash": hashlib.sha256(text.encode()).hexdigest(),
                }
                self.connection.execute(
                    f"INSERT INTO reflection_cases ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                    tuple(row.values()),
                )
                created.append(case_id)
        self.log({"operation": "case_store", "agent_id": self.agent_id,
                  "trajectory_id": reflection["trajectory_id"], "case_ids": created})
        return created

    def review_recurring_failures(self, case_ids: Sequence[str]) -> dict:
        """Second reflection: propose, but do not activate, a reusable lesson."""
        if not case_ids:
            return {"decision": "none", "reason": "no newly stored cases"}
        marks = ",".join("?" for _ in case_ids)
        current = [self._case_content(dict(row)) for row in self.connection.execute(
            f"SELECT * FROM reflection_cases WHERE case_id IN ({marks})", tuple(case_ids))]
        historical = [self._case_content(dict(row)) | {"case_id": row["case_id"]}
                      for row in self.connection.execute(
            "SELECT * FROM reflection_cases WHERE agent_id=? AND outcome IN ('partial','failure') "
            f"AND case_id NOT IN ({marks}) ORDER BY created_at DESC LIMIT 12",
            (self.agent_id, *case_ids))]
        if not historical:
            result = {"decision": "none", "reason": "no earlier partial/failure cases"}
        else:
            result = self.llm.generate("case_consolidation", {
                "instructions": CASE_CONSOLIDATION_INSTRUCTIONS,
                "new_cases": current, "historical_failure_cases": historical,
            })
            if not isinstance(result, dict):
                result = {"decision": "none", "reason": "invalid review response"}
        self.log({"operation": "case_consolidation_review", "new_case_ids": list(case_ids),
                  "historical_case_count": len(historical), "review": result})
        return result

    def persist_experience_candidate(self, review: Mapping[str, Any]) -> str | None:
        """Persist an approved-shape review as a *candidate*, never auto-active."""
        proposal = review.get("experience") if isinstance(review, Mapping) else None
        source_case_ids = review.get("source_case_ids", []) if isinstance(review, Mapping) else []
        if review.get("decision") != "experience" or not isinstance(proposal, Mapping):
            return None
        required = ("condition", "lesson", "recommended_action", "verification")
        if not all(isinstance(proposal.get(key), str) and proposal[key].strip() for key in required):
            return None
        source_case_ids = [value for value in source_case_ids if isinstance(value, str) and value]
        if not source_case_ids:
            return None
        marks = ",".join("?" for _ in source_case_ids)
        sources = list(self.connection.execute(
            f"SELECT case_id, trajectory_id, evidence_refs FROM reflection_cases WHERE case_id IN ({marks})",
            tuple(source_case_ids)))
        # memory_sources requires at least one evidence reference per link; cases without any (for example
        # implementation or build-failure cases) cannot support a candidate, and skipping is harmless.
        sources = [row for row in sources if json.loads(row["evidence_refs"] or "[]")]
        # Several cases from one run can cite identical evidence; memory_sources keeps one link per pair.
        sources = list({(row["trajectory_id"], row["evidence_refs"]): row for row in sources}.values())
        if not sources:
            self.log({"operation": "experience_candidate_skipped", "reason": "no source case has evidence references",
                      "source_case_ids": source_case_ids})
            return None
        record_id, experience_id = uuid.uuid4().hex, "case-review-" + uuid.uuid4().hex[:12]
        content = {"condition": proposal["condition"].strip(), "lesson": proposal["lesson"].strip(),
                   "recommended_action": proposal["recommended_action"].strip(),
                   "verification": proposal["verification"].strip()}
        text, vector = _json(content), self._embed([_json(content)])[0]
        row = {"record_id": record_id, "experience_id": experience_id, "agent_id": self.agent_id,
               "version_no": 1, "title": "Cross-task failure prevention",
               **content, "avoid_action": "Do not rely on an unverified implementation or transient feedback.",
               "limitations": "Candidate generated from reflection cases; requires validation before activation.",
               "status": "candidate", "embedding": struct.pack(f"<{len(vector)}f", *vector),
               "embedding_model": self.embedder.model_id, "embedding_dim": len(vector),
               "embedding_text_hash": hashlib.sha256(text.encode()).hexdigest(),
               "restored_from_record_id": None}
        with self.connection:
            self.connection.execute(f"INSERT INTO experiences ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
            for source in sources:
                self.connection.execute(
                    "INSERT INTO memory_sources (source_id,experience_record_id,trajectory_id,evidence_refs,relation,note) VALUES (?,?,?,?,?,?)",
                    (uuid.uuid4().hex, record_id, source["trajectory_id"], source["evidence_refs"], "supports",
                     "Cross-task reflection candidate derived from this failure case."))
        self.log({"operation": "experience_candidate_persisted", "record_id": record_id,
                  "source_case_ids": source_case_ids})
        return record_id

    def activate_experience(self, record_id: str) -> None:
        """Explicit validation gate for a reviewed candidate."""
        with self.connection:
            self.connection.execute("UPDATE experiences SET status='active' WHERE record_id=? AND status='candidate'", (record_id,))

    @staticmethod
    def _case_content(row: Mapping[str, Any]) -> dict:
        return {"case_type": ("implementation" if str(row["feature_object"]).startswith(IMPLEMENTATION_MARKER)
                              else row["channel"]),
                "task_requirement": row["task_requirement"],
                "feature_object": row["feature_object"], "user_trigger": row["user_trigger"],
                "expected_state_change": row["expected_state_change"], "observed_result": row["observed_result"],
                "root_cause_or_hypothesis": row["root_cause_or_hypothesis"],
                "preventative_action": row["preventative_action"], "verification": row["verification"],
                "transfer_limits": row["transfer_limits"], "outcome": row["outcome"]}

    def _aspects(self, task: str) -> dict[str, list[dict]]:
        result = self.llm.generate("case_task_aspects", {
            "instructions": CASE_ASPECT_INSTRUCTIONS, "task": task,
        })
        raw = result if isinstance(result, dict) else {}
        functional = [item for item in raw.get("functional_aspects", [])
                      if isinstance(item, dict) and all(str(item.get(key, "")).strip()
                                                        for key in ("feature_object", "user_trigger", "expected_state_change"))]
        appearance = [item for item in raw.get("appearance_aspects", [])
                      if isinstance(item, dict) and str(item.get("visual_requirement", "")).strip()]
        # No code-written "first screen presents every feature" aspect any more: it was a hand-written
        # design assumption that pulled guidance such as "all sections on the landing page, no navigation"
        # (000017, 000018) against requirements and checks that expect navigation.
        build = []
        if functional and raw.get("interactive") is True and not self.config.common_pool:
            build.append({"implementation_requirement": "the site is built so that its interactive "
                          "features work in the browser as client-side behaviour: " +
                          ", ".join(str(item["feature_object"]) for item in functional)})
        return {"functional": functional, "appearance": appearance, "build": build}

    @staticmethod
    def _aspect_text(channel: str, aspect: Mapping[str, Any]) -> str:
        if channel == "appearance":
            return "appearance requirement: " + str(aspect["visual_requirement"])
        if channel == "build":
            return "implementation approach: " + str(aspect["implementation_requirement"])
        text = ("functional feature: " + str(aspect["feature_object"]) + "; user trigger: "
                + str(aspect["user_trigger"]) + "; expected state: "
                + str(aspect["expected_state_change"]))
        pattern = str(aspect.get("pattern_query", "")).strip()
        return text + ("; interaction pattern: " + pattern if pattern else "")

    def _allowed_case_ids(self) -> set[str] | None:
        """Cases from every task except the current one (leave-one-task-out); None = not configured.
        Keeps a re-run of a task from reading its own earlier reflections. Task numbers are not treated as a
        timeline, so cases from higher-numbered tasks stay available."""
        if not (self.config.exclude_same_task and self.statistics_task_id):
            return None
        from memory_statistics import _other_task
        allowed = set()
        for row in self.connection.execute(
                "SELECT c.case_id, t.task_id FROM reflection_cases c JOIN trajectories t "
                "ON t.trajectory_id = c.trajectory_id WHERE c.agent_id=?", (self.agent_id,)):
            if _other_task(row["task_id"], self.statistics_task_id):
                allowed.add(row["case_id"])
            else:
                self.excluded_by_cutoff.add(row["case_id"])
        return allowed

    def _discover_channel(self, channel: str, aspects: list[dict]) -> list[dict]:
        if not aspects:
            return []
        allowed = self._allowed_case_ids()
        queries = self._embed([self._aspect_text(channel, aspect) for aspect in aspects])
        discovered: dict[str, tuple[RetrievedCase, float, int]] = {}
        db_channel = "functional" if channel == "build" else channel
        marker = {"build": " AND feature_object LIKE ?"}.get(channel, "")
        marker_args = (IMPLEMENTATION_MARKER + "%",) if marker else ()
        for raw in self.connection.execute(
            "SELECT * FROM reflection_cases WHERE agent_id=? AND status='active' AND channel=? "
            "AND embedding_model=? AND embedding_dim=?" + marker,
            (self.agent_id, db_channel, self.embedder.model_id, len(queries[0])) + marker_args,
        ):
            row = dict(raw)
            if allowed is not None and row["case_id"] not in allowed:
                continue
            if self._skip_in_functional(row, channel):
                continue
            content = self._case_content(row)
            text = _json(content)
            if hashlib.sha256(text.encode()).hexdigest() != row["embedding_text_hash"]:
                continue
            vector = _vector(struct.unpack(f"<{row['embedding_dim']}f", row["embedding"]))
            score, index = max((sum(left * right for left, right in zip(query, vector)), idx)
                               for idx, query in enumerate(queries))
            if score >= self.config.retrieval_min_similarity:
                discovered[row["case_id"]] = (RetrievedCase(row["case_id"], content, score), score, index)
        # Lightweight lexical backstop: if embeddings produce no candidates,
        # recover cases sharing concrete feature words with the current aspect.
        # The LLM relevance gate still makes the final selection; this only
        # prevents an empty vector result from short-circuiting retrieval.
        if not discovered:
            for raw in self.connection.execute(
                "SELECT * FROM reflection_cases WHERE agent_id=? AND status='active' AND channel=?" + marker,
                (self.agent_id, db_channel) + marker_args,
            ):
                row = dict(raw)
                if allowed is not None and row["case_id"] not in allowed:
                    continue
                if self._skip_in_functional(row, channel):
                    continue
                content = self._case_content(row)
                case_text = _json(content).lower()
                best_overlap = 0.0
                best_index = 0
                for index, aspect in enumerate(aspects):
                    aspect_text = self._aspect_text(channel, aspect).lower()
                    left = set(re.findall(r"[a-z0-9]{3,}", aspect_text))
                    right = set(re.findall(r"[a-z0-9]{3,}", case_text))
                    overlap = len(left & right) / max(1, len(left))
                    if overlap > best_overlap:
                        best_overlap, best_index = overlap, index
                if best_overlap > 0:
                    discovered[row["case_id"]] = (RetrievedCase(row["case_id"], content, best_overlap), best_overlap, best_index)
        for raw in ([] if channel == "build" else self.connection.execute(
            "SELECT * FROM experiences WHERE agent_id=? AND status='active' AND embedding_model=? AND embedding_dim=?",
            (self.agent_id, self.embedder.model_id, len(queries[0])))):
            row = dict(raw)
            text = _json({"condition": row["condition"], "lesson": row["lesson"],
                          "recommended_action": row["recommended_action"], "verification": row["verification"]})
            if hashlib.sha256(text.encode()).hexdigest() != row["embedding_text_hash"]:
                continue
            vector = _vector(struct.unpack(f"<{row['embedding_dim']}f", row["embedding"]))
            score, index = max((sum(left * right for left, right in zip(query, vector)), idx)
                               for idx, query in enumerate(queries))
            if score >= self.config.retrieval_min_similarity:
                content = {"case_type": channel, "task_requirement": "cross-task reusable experience",
                           "feature_object": row["condition"], "user_trigger": row["condition"],
                           "expected_state_change": row["lesson"], "observed_result": row["lesson"],
                           "root_cause_or_hypothesis": "recurring cross-task failure",
                           "preventative_action": row["recommended_action"],
                           "verification": row["verification"], "transfer_limits": row["limitations"],
                           "outcome": "experience"}
                key = "experience:" + row["record_id"]
                discovered[key] = (RetrievedCase(key, content, score), score, index)
        ranked = sorted(discovered.values(), key=lambda item: (-item[1], item[0].case_id))
        # Two pools: failure/partial/observation cases first; success cases only fill
        # remaining slots.
        limit = self.config.case_retrieval_candidates_per_channel
        failure_pool = [entry for entry in ranked if entry[0].content.get("outcome") != "success"]
        success_pool = [entry for entry in ranked if entry[0].content.get("outcome") == "success"]
        chosen = failure_pool[:limit]
        chosen += success_pool[:limit - len(chosen)]
        return [{"case_id": item.case_id, "content": item.content, "similarity": score,
                 "matched_aspect_index": index}
                for item, score, index in chosen]

    @staticmethod
    def _parse_decisions(result: Any) -> list:
        if isinstance(result, dict):
            raw = result.get("decisions")
            if raw is None and result.get("case_id"):
                raw = [result]
            return raw if isinstance(raw, list) else []
        return result if isinstance(result, list) else []

    def _judge_aspect(self, channel: str, operation: str, instructions: str, task: str,
                      aspect: Mapping[str, Any], aspect_index: int, candidates: list[dict]) -> list[dict]:
        """One relevance call per aspect; every candidate must be judged (one retry)."""
        ids = [item["case_id"] for item in candidates]
        request = {"instructions": instructions, "task": task, "aspect": dict(aspect),
                   "candidates": candidates}
        decisions = self._parse_decisions(self.llm.generate(operation, request))
        missing = [i for i in ids if not any(isinstance(d, dict) and d.get("case_id") == i for d in decisions)]
        if missing:
            self.log({"operation": "incomplete_decisions", "agent_id": self.agent_id, "channel": channel,
                      "aspect": aspect_index, "missing": missing, "attempt": 1})
            retry = self._parse_decisions(self.llm.generate(operation, {
                **request, "retry_notice": "Your previous answer omitted decisions for case_ids " +
                json.dumps(missing) + ". Return one decision for every candidate."}))
            still = [i for i in ids if not any(isinstance(d, dict) and d.get("case_id") == i for d in retry)]
            if still:
                self.log({"operation": "incomplete_decisions", "agent_id": self.agent_id, "channel": channel,
                          "aspect": aspect_index, "missing": still, "attempt": 2})
            if len(still) <= len(missing):
                decisions = retry
        return [{**d, "matched_aspect_index": aspect_index} for d in decisions
                if isinstance(d, dict) and d.get("case_id") in ids]

    def select_cases(self, task: str, aspects: dict[str, list[dict]]
                     ) -> tuple[dict, dict[str, list[dict]], tuple[RetrievedCase, ...]]:
        """Stage 1: candidate discovery and relevance judgement."""
        functional_by_aspect = [self._discover_channel("functional", [aspect])
                                for aspect in aspects["functional"]]
        appearance_by_aspect = [self._discover_channel("appearance", [aspect])
                                for aspect in aspects["appearance"]]
        build_by_aspect = [self._discover_channel("build", [aspect]) for aspect in aspects.get("build", [])]
        candidates = {"functional": functional_by_aspect, "appearance": appearance_by_aspect,
                      "build": build_by_aspect}
        selected: dict[str, RetrievedCase] = {}
        matched_aspects: dict[str, list[dict]] = {}
        selected_by_channel: dict[str, list[str]] = {"functional": [], "appearance": [], "build": []}
        decisions_by_channel: dict[str, list[dict]] = {}
        for channel, channel_candidates_by_aspect, channel_aspects, operation, instructions, max_selected in (
            ("functional", functional_by_aspect, aspects["functional"], "case_functional_relevance",
             CASE_FUNCTIONAL_RELEVANCE_INSTRUCTIONS, len(aspects["functional"])),
            ("appearance", appearance_by_aspect, aspects["appearance"], "case_appearance_relevance",
             CASE_APPEARANCE_RELEVANCE_INSTRUCTIONS, len(aspects["appearance"])),
            ("build", build_by_aspect, aspects.get("build", []), "case_build_relevance",
             CASE_BUILD_RELEVANCE_INSTRUCTIONS, len(aspects.get("build", []))),
        ):
            decisions_by_channel[channel] = []
            if not channel_aspects or not any(channel_candidates_by_aspect):
                continue
            if self.config.case_retrieval_skip_relevance_gate:
                decisions = []
                for aspect_index, aspect_candidates in enumerate(channel_candidates_by_aspect):
                    if len(selected_by_channel[channel]) >= max_selected:
                        break
                    item = next((c for c in aspect_candidates
                                 if c["case_id"] not in selected_by_channel[channel]), None)
                    if item is None:
                        continue
                    selected[item["case_id"]] = RetrievedCase(item["case_id"], dict(item["content"]), item["similarity"])
                    selected_by_channel[channel].append(item["case_id"])
                    decisions.append({"case_id": item["case_id"], "matched_aspect_index": aspect_index,
                                      "verdict": "gate_skipped"})
                decisions_by_channel[channel] = decisions
                continue
            decisions_by_channel[channel] = []
            for aspect_index, aspect in enumerate(channel_aspects):
                aspect_candidates = channel_candidates_by_aspect[aspect_index]
                if not aspect_candidates:
                    continue
                decisions = self._judge_aspect(channel, operation, instructions, task, aspect,
                                               aspect_index, aspect_candidates)
                decisions_by_channel[channel].extend(decisions)
                allowed = {item["case_id"]: item for item in aspect_candidates}
                for verdict in ("hard_match", "soft_transfer"):
                    # Prefer a case not already chosen for another aspect: aspects with the same query
                    # otherwise all take the same top case and push other relevant lessons out.
                    matching = [d for d in decisions if d.get("verdict") == verdict
                                and d.get("case_id") in allowed]
                    winner = next((d for d in matching if d["case_id"] not in selected_by_channel[channel]),
                                  matching[0] if matching else None)
                    if winner is not None:
                        item = allowed[winner["case_id"]]
                        selected[item["case_id"]] = RetrievedCase(item["case_id"], dict(item["content"]),
                                                                  item["similarity"])
                        matched_aspects.setdefault(item["case_id"], []).append(dict(aspect))
                        if item["case_id"] not in selected_by_channel[channel]:
                            selected_by_channel[channel].append(item["case_id"])
                        break
        ordered = tuple(RetrievedCase(case_id, {**selected[case_id].content,
                                                "matched_aspects": matched_aspects.get(case_id, [])},
                                      selected[case_id].similarity)
                        for channel in ("build", "functional", "appearance")
                        for case_id in selected_by_channel[channel])
        return candidates, decisions_by_channel, ordered

    def adapt_cases(self, task: str, aspects: dict[str, list[dict]],
                    ordered: tuple[RetrievedCase, ...]) -> tuple[list[dict], tuple[RetrievedCase, ...]]:
        """Stage 2: rewrite selected cases into current-task implementation patterns."""
        adaptations: list[dict] = []
        kept: list[RetrievedCase] = []
        for source in ordered:
            base = {key: value for key, value in source.content.items() if key != "matched_aspects"}
            # One adaptation per (case, aspect): a case retrieved for two aspects yields two
            # separate patterns instead of one merged pattern.
            for matched in source.content.get("matched_aspects") or [None]:
                adapted = self.llm.generate("case_implementation_adaptation", {
                    "instructions": CASE_IMPLEMENTATION_ADAPTATION_INSTRUCTIONS,
                    "task": task, "aspects": aspects,
                    "selected_cases": [{"case_id": source.case_id, "content": base,
                                        "matched_aspect": matched, "similarity": source.similarity}]})
                raw = adapted.get("patterns", []) if isinstance(adapted, dict) else []
                pattern = next((p for p in raw if isinstance(p, dict) and p.get("case_id") == source.case_id), None) \
                    if isinstance(raw, list) else None
                if pattern is None:
                    self.log({"operation": "incomplete_adaptation", "agent_id": self.agent_id,
                              "case_id": source.case_id, "matched_aspect": matched})
                    continue
                adaptations.append({**pattern, "matched_aspect": matched})
                text = str(pattern.get("implementation_pattern", "")).strip()
                if not pattern.get("applicable") or not text:
                    continue
                kept.append(RetrievedCase(source.case_id, {
                    **base, "implementation_pattern": text, "matched_aspect": matched,
                    "adaptation_reason": str(pattern.get("reason", ""))}, source.similarity))
        ordered = tuple(kept)
        return adaptations, ordered

    def retrieve(self, task: str, *, top_k: int = 2,
                 preclassified: dict[str, list[dict]] | None = None) -> CasePacket:
        if not task.strip():
            raise ValueError("Case retrieval needs a task")
        aspects = preclassified if preclassified is not None else self._aspects(task)
        candidates, decisions_by_channel, ordered = self.select_cases(task, aspects)
        adaptations, ordered = self.adapt_cases(task, aspects, ordered)
        ordered, ordering = self.order_by_statistics(ordered)
        common: tuple[str, ...] = ()
        common_info: dict = {}
        if self.config.common_pool:
            candidates_common, common_info = self.common_pool_candidates()
            common, adapted = self.adapt_common_pool(candidates_common)
            common_info = {**common_info, "candidates": [c.case_id for c in candidates_common], **adapted}
        common_sources = tuple(dict.fromkeys(cid for item in common_info.get("patterns", [])
                                             for cid in item.get("source_case_ids", [])))
        packet = CasePacket(ordered, common=common, common_case_ids=common_sources,
                            statistics=self.statistics_block())
        condensed_info: dict = {"applied": False}
        if self.config.guidance_condense:
            packet, condensed_info = self.condense_packet(task, packet)
        self.log({"operation": "case_retrieval", "agent_id": self.agent_id, "task": task,
                  "guidance_condense": condensed_info,
                  "aspects": aspects, "candidates_by_channel": candidates,
                  "decisions_by_channel": decisions_by_channel,
                  "implementation_adaptations": adaptations, "statistics_ordering": ordering, "common_pool": common_info,
                  "selected": [item.case_id for item in ordered], "rendered_memory": packet.render(),
                  "packet_chars": len(packet.render())})
        return packet

    def condense_packet(self, task: str, packet: CasePacket) -> tuple[CasePacket, dict]:
        """Merge every memory line into at most guidance_max_items short requirements, within a
        character budget proportional to the requirement. Lines are rewritten, not invented: each kept
        item names the candidate lines it came from, and items citing nothing are dropped."""
        candidates = []
        for item in packet.cases:
            text = str(item.content.get("implementation_pattern", "")).strip()
            if text:
                candidates.append({"id": f"g{len(candidates)}", "text": text, "case_ids": [item.case_id],
                                   "kind": item.content.get("case_type", "functional")})
        common_ids = list(packet.common_case_ids)
        for text in packet.common:
            if text.strip():
                candidates.append({"id": f"g{len(candidates)}", "text": text.strip(), "case_ids": common_ids,
                                   "kind": "common pitfall"})
        if not candidates:
            return packet, {"applied": False, "reason": "no memory lines"}
        budget = int(len(task) * self.config.guidance_max_ratio)
        limit = self.config.guidance_max_items
        instructions = (
                f"You prepare implementation guidance for a small code-generation model that loses "
                f"instructions when given many. Rewrite the candidate lines into AT MOST {limit} items, "
                f"each ONE sentence, and at most {budget} characters in total. These are notes on parts of the "
                "requirement, not a list of what to build: start every item with the part of the requirement "
                "it refines (for example \"For the booking form: ...\", or \"On every page: ...\" for a "
                "common pitfall) and say how to implement that part so it does not go wrong; never write an "
                "item that only names a feature to build. Use at most 2 items for common pitfalls and the "
                "rest for the requirement's own features. Cover, do not drop: every candidate must be cited "
                "in some item's \"from\", unless it duplicates another candidate or does not apply to this "
                "requirement's features or stack - list those in \"dropped\" with \"why\": \"duplicate\" or \"not_applicable\" (space is never a reason: merge instead). When there are "
                "more candidates than items allowed, merge related candidates into one item (cite them all) "
                "and shorten wording to fit the character limit; never leave out a note on one of the "
                "requirement's features to save space, because the code model tends to build only the parts the "
                "notes mention. Candidates of kind \"common pitfall\" come from problems "
                "that recurred across earlier websites and apply to every website: keep the first two. "
                f"Brevity: each item is one short imperative sentence of at most {ITEM_MAX_CHARS} characters "
                "after its prefix (for example \"Voting: after Vote, show a confirmation at once.\"); write "
                "only what to build and how, never verification or rationale clauses (verify..., ensuring..., "
                "so that users..., without relying on...), no filler adverbs (visibly, sufficiently, "
                "immediately after a successful...), and do not restate values the requirement already gives "
                "(colours, names) beyond a word or two. "
                "Put the item most likely to prevent a failure first. Do not add new advice that no candidate supports; recorded statistics may "
                "only be used to decide what matters most, never quoted. Return JSON "
                '{"items":[{"text":str,"from":[candidate ids]}],"dropped":[{"id":str,"why":"duplicate|not_applicable","reason":str}]}.')
        request = {"instructions": instructions, "requirement": task,
                   "candidates": [{k: c[k] for k in ("id", "text", "kind")} for c in candidates],
                   "recorded_statistics": packet.statistics}
        result = self.llm.generate("guidance_condense", request)
        # Coverage check (code): a feature candidate that no item cites and that the model did not drop as a
        # duplicate or not-applicable was cut for space -- the failure seen in 018 and 026, where the generator
        # then built only the noted parts. Ask once more, naming what is missing and the size limits.
        def _gaps(answer: dict) -> tuple[list[str], int]:
            items = answer.get("items", []) if isinstance(answer, dict) else []
            cited = {s for i in items if isinstance(i, dict) for s in (i.get("from") or [])}
            # Only a duplicate or not-applicable candidate may be dropped; "no room" is not accepted.
            dropped = {str(d.get("id")) for d in (answer.get("dropped") or [])
                       if isinstance(d, dict) and d.get("why") in ("duplicate", "not_applicable")} \
                if isinstance(answer, dict) else set()
            missing = [c["id"] for c in candidates
                       if c["kind"] != "common pitfall" and c["id"] not in cited and c["id"] not in dropped]
            size = sum(len(str(i.get("text", ""))) for i in items[:limit] if isinstance(i, dict))
            return missing, size
        missing, size = _gaps(result)
        retried = None
        if missing or size > budget:
            retried = {"missing": missing, "chars": size}
            result = self.llm.generate("guidance_condense", {
                **request, "previous_answer": result,
                "problem": (f"Your previous answer left out candidates {missing} without listing them as dropped, "
                            f"and/or used {size} of {budget} characters. Rewrite so every non-duplicate, "
                            f"applicable candidate is cited, within {limit} items and {budget} characters, by "
                            "merging related candidates and shortening wording.")})
            retried["after"] = dict(zip(("missing", "chars"), _gaps(result)))
        long_items = [i for i in (result.get("items", []) if isinstance(result, dict) else [])
                      if isinstance(i, dict) and len(str(i.get("text", ""))) > ITEM_MAX_CHARS + 30]
        if long_items:
            shortened = self.llm.generate("guidance_shorten", {
                "instructions": (f"Shorten each item to one imperative sentence of at most {ITEM_MAX_CHARS} "
                                 "characters after its prefix (keep the prefix such as \"Voting:\" or \"Every "
                                 "page:\"). Keep the concrete thing to build; delete verification or rationale "
                                 "clauses, filler adverbs and values the requirement already states. Return JSON "
                                 '{"items":[{"index":int,"text":str}]}.'),
                "requirement": task, "items": [{"index": n, "text": i.get("text")} for n, i in enumerate(long_items)]})
            for entry in (shortened.get("items", []) if isinstance(shortened, dict) else []):
                n = entry.get("index") if isinstance(entry, dict) else None
                if isinstance(n, int) and 0 <= n < len(long_items) and str(entry.get("text", "")).strip():
                    long_items[n]["text"] = str(entry["text"]).strip()
        by_id = {c["id"]: c for c in candidates}
        kept, used = [], 0
        for item in (result.get("items", []) if isinstance(result, dict) else [])[:limit]:
            text = str(item.get("text", "")).strip() if isinstance(item, dict) else ""
            sources = [by_id[s] for s in item.get("from", []) if s in by_id] if text else []
            if not sources:
                continue
            used += len(text)
            case_ids = list(dict.fromkeys(cid for s in sources for cid in s["case_ids"]))
            kept.append(RetrievedCase(case_ids[0] if case_ids else "", {
                "implementation_pattern": text, "case_type": sources[0]["kind"].split()[0],
                "source_case_ids": case_ids, "_from": [s["id"] for s in sources]}, 0.0))
        # Recurring cross-site lessons must survive condensing: the first two common lines are kept (at most
        # 2 common items, the rest for the requirement's features). A missing one is added.
        common_candidates = [c for c in candidates if c["kind"] == "common pitfall"]
        for wanted in common_candidates[:2]:
            if not kept or sum(k.content.get("case_type") == "common" for k in kept) >= 2:
                break
            if any(k.content.get("case_type") == "common" and wanted["id"] in k.content.get("_from", []) for k in kept):
                continue
            # Never cut a feature note to make room (the generator then skips that feature); the
            # item count may exceed the limit by the common lines that had to be restored.
            kept.append(RetrievedCase(wanted["case_ids"][0] if wanted["case_ids"] else "", {
                "implementation_pattern": wanted["text"], "case_type": "common",
                "source_case_ids": list(wanted["case_ids"]), "_from": [wanted["id"]]}, 0.0))
            used += len(wanted["text"])
        if not kept:
            return packet, {"applied": False, "reason": "condensing returned no usable item",
                            "raw": result}
        condensed = CasePacket(tuple(kept), common=(), common_case_ids=(), statistics="")
        cited = {s for k in kept for s in k.content.get("_from", [])}
        return condensed, {"applied": True, "budget_chars": budget, "used_chars": used,
                           "candidates": len(candidates), "kept": len(kept), "retried": retried,
                           "uncovered": [c["id"] for c in candidates if c["id"] not in cited],
                           "dropped": (result.get("dropped") if isinstance(result, dict) else None),
                           "items": [c.content["implementation_pattern"] for c in kept]}

    def implementation_breadth(self) -> dict:
        """How widely each implementation lesson occurred: the number of DISTINCT tasks whose cases state it.

        Code counts the tasks; a model only groups cases that state the same lesson. The task being run is
        excluded (leave-one-task-out), so a lesson that so far appeared in one task is narrow."""
        cached = getattr(self, "_breadth_cache", None)
        if cached is not None and cached[0] == self.statistics_task_id:
            return cached[1]
        rows = [dict(row) for row in self.connection.execute(
            "SELECT r.case_id, r.preventative_action, t.task_id FROM reflection_cases r "
            "JOIN trajectories t USING(trajectory_id) WHERE r.agent_id=? AND r.status='active' "
            "AND r.channel='functional' AND r.feature_object LIKE ?", (self.agent_id, IMPLEMENTATION_MARKER + "%"))]
        allowed = self._allowed_case_ids()
        if allowed is not None:
            rows = [row for row in rows if row["case_id"] in allowed]
        groups: list[list[str]] = []
        lessons: dict[str, str] = {}
        if len(rows) > 1:
            try:
                result = self.llm.generate("implementation_lesson_groups", {
                    "instructions": IMPLEMENTATION_LESSON_GROUP_INSTRUCTIONS,
                    "cases": [{"case_id": r["case_id"], "lesson": r["preventative_action"][:400]} for r in rows]})
            except ValueError:
                result = {}
            known, seen = {r["case_id"] for r in rows}, set()
            for item in (result.get("groups") or []) if isinstance(result, dict) else []:
                ids = [c for c in (item.get("case_ids") or []) if c in known and c not in seen] \
                    if isinstance(item, dict) else []
                if ids:
                    seen.update(ids)
                    groups.append(ids)
                    lessons[ids[0]] = str(item.get("lesson", ""))[:200]
            groups += [[r["case_id"]] for r in rows if r["case_id"] not in seen]
        else:
            groups = [[r["case_id"]] for r in rows]
        task_of = {r["case_id"]: r["task_id"] for r in rows}
        summary = [{"case_ids": ids, "tasks": sorted({task_of[c] for c in ids}), "lesson": lessons.get(ids[0], "")}
                   for ids in groups]
        broad = {c for entry in summary if len(entry["tasks"]) >= self.config.common_pool_min_tasks
                 for c in entry["case_ids"]}
        value = {"broad_ids": broad, "groups": summary, "min_tasks": self.config.common_pool_min_tasks}
        self._breadth_cache = (self.statistics_task_id, value)
        return value

    def _skip_in_functional(self, row: Mapping[str, Any], channel: str) -> bool:
        """Implementation cases reach the functional (feature-matched) route only when they are NOT broad
        enough for the common pool; broad ones are served by the pool."""
        if channel != "functional" or not str(row["feature_object"]).startswith(IMPLEMENTATION_MARKER):
            return False
        if not self.config.common_pool:
            return True  # old behaviour: the build aspect serves them
        return row["case_id"] in self.implementation_breadth()["broad_ids"]

    def common_pool_candidates(self, requirement: str | None = None) -> tuple[list[RetrievedCase], dict]:
        """Stage 1 of the common pool: implementation lessons that occurred in several different tasks
        (breadth >= common_pool_min_tasks), most important first, plus reserved slots for the highest
        all-time severity whatever their breadth (a rare but severe problem, such as a build failure).
        Narrower lessons are not lost: they are retrieved by feature match like functional cases."""
        rows = [dict(row) for row in self.connection.execute(
            "SELECT * FROM reflection_cases WHERE agent_id=? AND status='active' AND channel='functional' "
            "AND feature_object LIKE ? ORDER BY created_at DESC", (self.agent_id, IMPLEMENTATION_MARKER + "%"))]
        allowed = self._allowed_case_ids()
        if allowed is not None:
            rows = [row for row in rows if row["case_id"] in allowed]
        cases = tuple(RetrievedCase(row["case_id"], self._case_content(row), 0.0) for row in rows)
        breadth = self.implementation_breadth()
        ordered, info = self.order_by_statistics(cases)
        info = {**info, "breadth": breadth["groups"], "min_tasks": breadth["min_tasks"]}
        limit = self.config.common_pool_candidates
        # Reserved slots also serve the cold start: before statistics can rank anything, they are filled
        # with the newest implementation lessons (rows are newest first), so a lesson seen in only one
        # task is still offered instead of leaving the pool empty.
        reserve = reserved_slots = min(self.config.common_pool_reserve, limit)
        ordered = list(ordered)
        broad = [c for c in ordered if c.case_id in breadth["broad_ids"]]
        picked = broad[:limit - reserve]
        totals = info.get("case_totals", {})
        rest = sorted((c for c in ordered if c not in picked), key=lambda c: -totals.get(c.case_id, 0.0))
        # One reserved slot per lesson: several cases of the same lesson (one task can store it once per
        # failed check) must not fill every slot and push other lessons out.
        group_of = {cid: index for index, entry in enumerate(breadth["groups"]) for cid in entry["case_ids"]}
        taken = {group_of.get(c.case_id, c.case_id) for c in picked}
        for case in rest:
            if reserve <= 0:
                break
            key = group_of.get(case.case_id, case.case_id)
            if key not in taken:
                picked.append(case)
                taken.add(key)
                reserve -= 1
        picked += [c for c in broad if c not in picked][:limit - len(picked)]
        info["narrow_left_to_feature_match"] = [c.case_id for c in ordered if c not in picked
                                                and c.case_id not in breadth["broad_ids"]]
        return picked, {**info, "available": len(cases), "reserved_slots": reserved_slots}

    def adapt_common_pool(self, candidates: Sequence[RetrievedCase]) -> tuple[tuple[str, ...], dict]:
        """Stage 2 of the common pool: merge/rewrite the candidates into a few general requirements."""
        if not candidates:
            return (), {"patterns": []}
        size = self.config.common_pool_size
        result = self.llm.generate("common_pool_adaptation", {
            "instructions": COMMON_POOL_ADAPTATION_INSTRUCTIONS, "max_patterns": size,
            "cases": [{"case_id": c.case_id, "priority_rank": index + 1,
                       "content": {k: v for k, v in c.content.items() if k != "matched_aspects"}}
                      for index, c in enumerate(candidates)]})
        raw = result.get("patterns", []) if isinstance(result, dict) else []
        known = {c.case_id for c in candidates}
        patterns = []
        for item in raw if isinstance(raw, list) else []:
            text = str(item.get("implementation_pattern", "")).strip() if isinstance(item, dict) else ""
            sources = [s for s in item.get("source_case_ids", []) if s in known] if text else []
            if text and sources:
                patterns.append((text, sources))
        return tuple(text for text, _ in patterns[:size]), {"patterns": [
            {"implementation_pattern": t, "source_case_ids": s} for t, s in patterns[:size]]}

    def order_by_statistics(self, cases: Any) -> tuple[tuple, dict]:
        """Long Memory only: most frequent recent problems first (see memory_statistics.py)."""
        if not (self.config.statistics_memory and self.statistics_task_id):
            return tuple(cases), {"applied": False}
        from memory_statistics import PriorityParams, order_by_cause_frequency
        ordered, info = order_by_cause_frequency(self.llm, self.database, self.agent_id,
                                                 self.statistics_task_id, cases,
                                                 PriorityParams.from_config(self.config))
        return tuple(ordered), info

    def statistics_block(self) -> str:
        if not (self.config.statistics_memory and self.statistics_task_id):
            return ""
        from memory_statistics import PriorityParams, render_block, summarize
        return render_block(summarize(self.database, self.agent_id, self.statistics_task_id,
                                      PriorityParams.from_config(self.config)))

    def run(self, task: str, adapter: Any, *, task_domain: str | None = None) -> Any:
        # ``task_domain`` is deliberately accepted for the same adapter contract
        # as LongMemory. Case-only retrieval has no domain hard filter.
        del task_domain
        aspects = self._aspects(task)
        packet = self.retrieve(task, preclassified=aspects)
        return adapter.run(task, packet)
