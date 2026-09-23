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
import sqlite3
import struct
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from long_memory import connect_database
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


CASE_ASPECT_INSTRUCTIONS = """Decompose a public website-generation requirement
into a small set of explicit, implementable retrieval aspects. Do not invent hidden
tests, business details, or implementation steps. Functional aspects must state a
feature object, a user trigger, and an expected visible state change. Appearance
aspects must state a concrete visual requirement. Return JSON only:
{"functional_aspects":[{"feature_object":str,"user_trigger":str,
"expected_state_change":str}],"appearance_aspects":[{"visual_requirement":str}]}.
Return at most three functional aspects and one appearance aspect. Empty lists are
valid when that channel is absent."""


CASE_FUNCTIONAL_RELEVANCE_INSTRUCTIONS = """Judge only functional historical cases.
Compare every candidate with the functional aspects by feature object, user trigger,
and expected state change. Different business domains are allowed when the same user
operation and visible state transition transfer. Do not select merely because both
tasks are websites, forms, or navigation. Return one decision for every candidate
in every supplied aspect; use reject when no specific match exists. Select at most
one candidate per aspect and at most the configured functional case limit overall.
Return JSON only with case_id, matched_aspect_index, verdict, matched_current_requirement,
reason, and 1-3 current-task implementation_checks."""

CASE_APPEARANCE_RELEVANCE_INSTRUCTIONS = """Judge only appearance historical cases.
Compare every candidate with the concrete appearance aspect. A different colour
palette alone is not a match; require a reusable visual constraint or failure mode.
Do not select merely because both tasks are websites. Return exactly one decision for
every candidate; use reject when no specific match exists. Select at most one
candidate. Return JSON only with case_id, matched_aspect_index, verdict,
matched_current_requirement, reason, and 1-3 current-task implementation_checks."""

CASE_IMPLEMENTATION_ADAPTATION_INSTRUCTIONS = """You are the second-stage memory
reviewer. The current task is binding. For each selected historical case, discard
irrelevant business content and retain only a transferable lesson. Rewrite it as a
short executable implementation pattern containing trigger, required UI/state
behaviour, and verification action. Do not invent requirements or copy old wording,
colours, or layout. Return JSON only:
{"patterns":[{"case_id":str,"applicable":bool,"reason":str,
"implementation_pattern":str}]}"""

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

    def render(self) -> str:
        if not self.cases:
            return ""
        return "Relevant Past Reflection Cases\n" + json.dumps(
            [item.content for item in self.cases], ensure_ascii=False, sort_keys=True
        )


class ReflectionCaseMemory:
    def __init__(self, database: str, agent_id: str, *, llm: Any, embedder: Any,
                 config: MemoryConfig, log: Callable[[dict], None] | None = None):
        self.connection = connect_database(database, read_only=False)
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

    def store(self, reflection: Mapping[str, Any]) -> list[str]:
        """Store complete structured cases; no Experience/Skill abstraction occurs."""
        task = str(reflection["public_task_requirement"])
        source: list[tuple[Mapping[str, Any], bool]] = []
        if isinstance(reflection.get("appearance_reflection"), dict):
            source.append((reflection["appearance_reflection"], True))
        source.extend((item, False) for item in reflection.get("functional_reflections", [])
                      if isinstance(item, dict))
        cases = [(self._content(task, item, appearance=appearance), item)
                 for item, appearance in source]
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
        if not sources:
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
        return {"case_type": row["channel"], "task_requirement": row["task_requirement"],
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
        return {"functional": functional[:self.config.max_task_aspects], "appearance": appearance[:1]}

    @staticmethod
    def _aspect_text(channel: str, aspect: Mapping[str, Any]) -> str:
        if channel == "appearance":
            return "appearance requirement: " + str(aspect["visual_requirement"])
        return ("functional feature: " + str(aspect["feature_object"]) + "; user trigger: "
                + str(aspect["user_trigger"]) + "; expected state: "
                + str(aspect["expected_state_change"]))

    def _discover_channel(self, channel: str, aspects: list[dict]) -> list[dict]:
        if not aspects:
            return []
        queries = self._embed([self._aspect_text(channel, aspect) for aspect in aspects])
        discovered: dict[str, tuple[RetrievedCase, float, int]] = {}
        for raw in self.connection.execute(
            "SELECT * FROM reflection_cases WHERE agent_id=? AND status='active' AND channel=? "
            "AND embedding_model=? AND embedding_dim=?",
            (self.agent_id, channel, self.embedder.model_id, len(queries[0])),
        ):
            row = dict(raw)
            content = self._case_content(row)
            text = _json(content)
            if hashlib.sha256(text.encode()).hexdigest() != row["embedding_text_hash"]:
                continue
            vector = _vector(struct.unpack(f"<{row['embedding_dim']}f", row["embedding"]))
            score, index = max((sum(left * right for left, right in zip(query, vector)), idx)
                               for idx, query in enumerate(queries))
            if score >= self.config.retrieval_min_similarity:
                discovered[row["case_id"]] = (RetrievedCase(row["case_id"], content, score), score, index)
        for raw in self.connection.execute(
            "SELECT * FROM experiences WHERE agent_id=? AND status='active' AND embedding_model=? AND embedding_dim=?",
            (self.agent_id, self.embedder.model_id, len(queries[0]))):
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
        return [{"case_id": item.case_id, "content": item.content, "similarity": score,
                 "matched_aspect_index": index}
                for item, score, index in ranked[:self.config.case_retrieval_candidates_per_channel]]

    def retrieve(self, task: str, *, top_k: int = 2) -> CasePacket:
        if not task.strip():
            raise ValueError("Case retrieval needs a task")
        aspects = self._aspects(task)
        functional_by_aspect = [self._discover_channel("functional", [aspect])
                                for aspect in aspects["functional"]]
        appearance_by_aspect = [self._discover_channel("appearance", [aspect])
                                for aspect in aspects["appearance"]]
        candidates = {"functional": functional_by_aspect, "appearance": appearance_by_aspect}
        selected: dict[str, RetrievedCase] = {}
        selected_by_channel: dict[str, list[str]] = {"functional": [], "appearance": []}
        decisions_by_channel: dict[str, list[dict]] = {}
        for channel, channel_candidates_by_aspect, channel_aspects, operation, instructions, max_selected in (
            ("functional", functional_by_aspect, aspects["functional"], "case_functional_relevance",
             CASE_FUNCTIONAL_RELEVANCE_INSTRUCTIONS, self.config.case_retrieval_max_functional),
            ("appearance", appearance_by_aspect, aspects["appearance"], "case_appearance_relevance",
             CASE_APPEARANCE_RELEVANCE_INSTRUCTIONS, self.config.case_retrieval_max_appearance),
        ):
            decisions_by_channel[channel] = []
            if not channel_aspects or not any(channel_candidates_by_aspect):
                continue
            result = self.llm.generate(operation, {"instructions": instructions,
                "task": task, "aspects": channel_aspects,
                "candidates_by_aspect": {str(i): value for i, value in enumerate(channel_candidates_by_aspect)}})
            # Canonical response is {"decisions": [...]}; tolerate legacy
            # bare-object/list responses so valid matches are not discarded.
            if isinstance(result, dict):
                raw_decisions = result.get("decisions")
                if raw_decisions is None and result.get("case_id"):
                    raw_decisions = [result]
                decisions = raw_decisions if isinstance(raw_decisions, list) else []
            elif isinstance(result, list):
                decisions = result
            else:
                decisions = []
            decisions_by_channel[channel] = decisions
            selected_aspects: set[int] = set()
            for decision in decisions:
                if not isinstance(decision, dict) or decision.get("verdict") not in ("hard_match", "soft_transfer"):
                    continue
                try:
                    aspect_index = int(decision.get("matched_aspect_index"))
                except (TypeError, ValueError):
                    continue
                if not 0 <= aspect_index < len(channel_candidates_by_aspect) or aspect_index in selected_aspects:
                    continue
                allowed = {item["case_id"]: item for item in channel_candidates_by_aspect[aspect_index]}
                item = allowed.get(decision.get("case_id"))
                if item is None:
                    continue
                selected[item["case_id"]] = RetrievedCase(item["case_id"], dict(item["content"]), item["similarity"])
                if item["case_id"] not in selected_by_channel[channel]:
                    selected_by_channel[channel].append(item["case_id"])
                selected_aspects.add(aspect_index)
                if len(selected_by_channel[channel]) >= max_selected:
                    break
        ordered = tuple(selected[case_id]
                        for channel in ("functional", "appearance")
                        for case_id in selected_by_channel[channel])
        adaptations: list[dict] = []
        if ordered:
            adapted = self.llm.generate("case_implementation_adaptation", {
                "instructions": CASE_IMPLEMENTATION_ADAPTATION_INSTRUCTIONS,
                "task": task, "aspects": aspects,
                "selected_cases": [{"case_id": item.case_id,
                                    "content": item.content,
                                    "similarity": item.similarity}
                                   for item in ordered]})
            raw = adapted.get("patterns", []) if isinstance(adapted, dict) else []
            kept: list[RetrievedCase] = []
            for pattern in raw if isinstance(raw, list) else []:
                if not isinstance(pattern, dict):
                    continue
                adaptations.append(pattern)
                if not pattern.get("applicable"):
                    continue
                source = next((item for item in ordered
                               if item.case_id == pattern.get("case_id")), None)
                text = str(pattern.get("implementation_pattern", "")).strip()
                if source is None or not text:
                    continue
                content = dict(source.content)
                content["implementation_pattern"] = text
                content["adaptation_reason"] = str(pattern.get("reason", ""))
                kept.append(RetrievedCase(source.case_id, content, source.similarity))
            ordered = tuple(kept)
        packet = CasePacket(ordered)
        self.log({"operation": "case_retrieval", "agent_id": self.agent_id, "task": task,
                  "aspects": aspects, "candidates_by_channel": candidates,
                  "decisions_by_channel": decisions_by_channel,
                  "implementation_adaptations": adaptations,
                  "selected": [item.case_id for item in ordered], "rendered_memory": packet.render(),
                  "packet_chars": len(packet.render())})
        return packet

    def run(self, task: str, adapter: Any, *, task_domain: str | None = None) -> Any:
        # ``task_domain`` is deliberately accepted for the same adapter contract
        # as LongMemory. Case-only retrieval has no domain hard filter.
        del task_domain
        return adapter.run(task, self.retrieve(task))
