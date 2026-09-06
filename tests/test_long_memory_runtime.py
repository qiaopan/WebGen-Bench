from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from long_memory import connect_database, initialize_database
from long_memory_runtime import (ExtractionOutputError, JsonlRunLog, LongMemory,
                                 MemoryConfig, MemoryPacket, MemoryRef)
from long_memory_integrations import AzureMemoryLLM, bolt_memory_prompt
from long_memory_settings import load_long_memory_settings


def proposal(title="Filter insight", kind="experience", relation="supports"):
    content = ({"title": title, "condition": "Filtering a list", "lesson": title,
                "verification": "Inspect the rendered list"} if kind == "experience" else
               {"name": title, "goal": "A working list", "conditions": "Filtering a list",
                "workflow": ["Apply filters before pagination"],
                "completion_checks": ["Visible results match the filter"]})
    return {"kind": kind, "content": content, "evidence_refs": [{"step_id": "1"}],
            "relation": relation, "note": "Observed in the recorded trace"}


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def generate(self, operation, payload):
        self.calls.append((operation, payload))
        response = self.responses.get(operation, {
            "extract": {"memories": [proposal()]},
            "validate": {"valid": True, "reason": "Grounded in the supplied evidence"},
            "judge": {"action": "KEEP", "reason": "Distinct knowledge"},
            "consolidate": {"action": "KEEP", "reason": "Distinct knowledge"},
            "aspects": {"aspects": ["Filtering", "Pagination"]},
            "relevance": lambda payload: {"applicable": [item["ref"] for item in payload["candidates"]],
                                           "reasons": {item["ref"]["record_id"]: "Applicable"
                                                       for item in payload["candidates"]}},
        }[operation])
        if isinstance(response, Exception):
            raise response
        return response(payload) if callable(response) else response


class FakeEmbedder:
    model_id = "offline-test@1"

    def embed(self, texts):
        return [[0.0, 1.0] if "unrelated" in text else
                [0.8, 0.6] if "weaker" in text else [1.0, 0.0] for text in texts]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "memory.db"
        initialize_database(self.path)
        self.llm = FakeLLM()
        self.events = []
        self.memory = self.open()
        self.addCleanup(self.memory.close)

    def open(self, mode="learn", agent="bolt", config=None, **overrides):
        return LongMemory(self.path, agent, memory_mode=mode, llm=self.llm,
                          embedder=FakeEmbedder(), config=config, log=self.events.append,
                          evidence_loader=lambda row: [{"ref": {"step_id": "1"},
                              "content": "Observed list results and the recorded outcome"}], **overrides)

    def trajectory(self, id="t1", agent="bolt", outcome="failure", status="completed"):
        with connect_database(self.path, read_only=False) as connection:
            connection.execute(
                "INSERT INTO trajectories (trajectory_id,task_id,agent_id,attempt_no,split_group,"
                "task_request,run_config,trace_path,run_status,finished_at,evaluation_results) "
                "VALUES (?,?,?,1,'g1','Filter a list','{}','trace.json',?,?,?)",
                (id, id, agent, status, None if status == "running" else "2026-09-06T00:00:00Z",
                 json.dumps([{"outcome": outcome}])),
            )
        connection.close()

    def make(self, id="t1", title="Filter insight", kind="experience", relation="supports", active=True):
        self.llm.responses["extract"] = {"memories": [proposal(title, kind, relation)]}
        ref = self.memory.extract(id)[0]
        if active:
            self.memory.validate(ref)
        return ref

    def link(self, target, parent):
        with self.memory._transaction():
            self.memory._source(target, parent=parent, evidence_refs=[{"memory": parent.record_id}],
                                relation="supports", note="Reviewed supporting knowledge")

    def test_zero_memories_and_no_implicit_consolidation(self):
        self.trajectory()
        self.llm.responses["extract"] = {"memories": []}
        self.assertEqual(self.memory.extract_and_validate("t1"), [])
        self.assertEqual([call[0] for call in self.llm.calls], ["extract"])
        self.assertEqual(self.memory.connection.execute("SELECT count(*) FROM experiences").fetchone()[0], 0)

    def test_bolt_adapter_preserves_memory_content_and_empty_packet(self):
        self.assertEqual(bolt_memory_prompt("task", MemoryPacket()), "task")
        self.trajectory()
        ref = self.make()
        packet = self.memory.retrieve("Filter")
        prompt = bolt_memory_prompt("Build it", packet)
        self.assertIn("Build it", prompt)
        self.assertIn("Relevant Experiences", prompt)
        self.assertIn(self.memory._row(ref)["lesson"], prompt)

    def test_admission_duplicate_judgement_receives_only_same_type_neighbors(self):
        self.trajectory()
        self.make(kind="skill")
        candidate = self.make(kind="experience", active=False)
        self.llm.responses["judge"] = lambda payload: (
            {"action": "KEEP", "reason": "Cross-type knowledge is distinct"}
            if payload["neighbors"] == [] else
            {"action": "REJECT", "reason": "Unexpected cross-type neighbor"}
        )
        self.assertEqual(self.memory.validate(candidate), "active")

    def test_candidates_and_rejections_are_never_retrieved(self):
        self.trajectory()
        ref = self.make(active=False)
        self.assertEqual(self.memory._row(ref)["status"], "candidate")
        self.assertEqual(self.memory.retrieve("Filter a list"), MemoryPacket())
        self.llm.responses["validate"] = {"valid": False, "reason": "Unsupported assertion"}
        self.assertEqual(self.memory.validate(ref), "rejected")
        self.assertEqual(self.memory.retrieve("Filter a list"), MemoryPacket())
        with self.assertRaises(sqlite3.IntegrityError), self.memory.connection:
            self.memory.connection.execute("UPDATE experiences SET status='active'")

    def test_provider_error_leaves_candidate_retryable(self):
        self.trajectory()
        ref = self.make(active=False)
        self.llm.responses["validate"] = RuntimeError("Provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.memory.validate(ref)
        self.assertEqual(self.memory._row(ref)["status"], "candidate")
        self.assertIn("error", self.events[-1])
        del self.llm.responses["validate"]
        self.assertEqual(self.memory.validate(ref), "active")

    def test_success_and_failure_both_support_experience_and_single_trace_skill(self):
        self.trajectory(outcome="failure")
        experience = self.make()
        skill = self.make(kind="skill")
        self.trajectory("t2", outcome="success")
        self.make("t2")
        packet = self.memory.retrieve("Filter a list")
        self.assertEqual(len(packet.experiences), 2)
        self.assertEqual(packet.skills[0].ref, skill)
        self.assertEqual(self.memory.provenance(experience, supports_only=True)["trajectories"][0]
                         ["evaluation_results"], '[{"outcome": "failure"}]')
        self.assertEqual(self.memory._row(skill)["experience_refs"], "[]")

    def test_support_adds_evidence_without_duplicate_active_memory(self):
        self.trajectory()
        first = self.make()
        self.trajectory("t2")
        second = self.make("t2", active=False)
        self.llm.responses["judge"] = {"action": "SUPPORT", "target": vars(first),
                                       "reason": "Independent confirmation"}
        self.assertEqual(self.memory.validate(second), "rejected")
        self.assertEqual(self.memory.validate(second), "rejected")
        packet = self.memory.retrieve("Filter")
        self.assertEqual(len(packet.experiences), 1)
        self.assertEqual(packet.experiences[0].supporting_trajectories, 2)
        self.assertEqual(self.memory._row(first)["version_no"], 1)

    def test_invalid_support_target_is_retried_then_rejected(self):
        self.trajectory()
        candidate = self.make(active=False)
        self.llm.responses["judge"] = {
            "action": "SUPPORT", "target": vars(candidate), "reason": "Invalid self target"
        }
        self.assertEqual(self.memory.validate(candidate), "rejected")
        self.assertEqual(self.memory._row(candidate)["status"], "rejected")
        judge_calls = [call for call in self.llm.calls if call[0] == "judge"]
        self.assertEqual(len(judge_calls), 3)

    def test_similarity_does_not_merge_and_consolidate_action_is_deferred(self):
        self.trajectory()
        self.make()
        self.llm.responses["judge"] = {"action": "CONSOLIDATE", "reason": "Potential pattern"}
        self.make(title="Different knowledge")
        self.assertEqual(len(self.memory.retrieve("Filter").experiences), 2)
        self.assertNotIn("consolidate", [operation for operation, _ in self.llm.calls])

    def test_consolidation_counts_independent_trajectories_not_memories(self):
        self.trajectory()
        for i in range(4):
            self.make(title=f"Lesson {i}")
        self.assertEqual(self.memory.consolidate(), [])
        self.assertNotIn("consolidate", [operation for operation, _ in self.llm.calls])

    def test_consolidation_preserves_originals_and_recursive_provenance(self):
        originals = []
        for i in range(3):
            self.trajectory(f"t{i}")
            originals.append(self.make(f"t{i}", title=f"Lesson {i}"))
        count = 0

        def consolidate(payload):
            nonlocal count
            count += 1
            if count > 1:
                return {"action": "KEEP", "reason": "Already represented"}
            return {"action": "CONSOLIDATE", "reason": "General procedure supported by these traces",
                    "source_memories": [vars(ref) for ref in originals],
                    "memory": proposal("General filtering procedure", "skill")}

        self.llm.responses["consolidate"] = consolidate
        derived = self.memory.consolidate()[0]
        self.assertEqual(derived.kind, "skill")
        self.assertTrue(all(self.memory._row(ref)["status"] == "active" for ref in originals))
        graph = self.memory.provenance(derived)
        self.assertEqual({row["trajectory_id"] for row in graph["trajectories"]}, {"t0", "t1", "t2"})
        self.assertEqual({row["source_experience_record_id"] for row in graph["edges"]
                          if row["trajectory_id"] is None}, {ref.record_id for ref in originals})
        self.assertEqual(self.memory.retrieve("Filter").skills[0].supporting_trajectories, 3)

    def test_consolidation_does_not_resend_full_trajectory_evidence(self):
        for i in range(3):
            self.trajectory(f"t{i}")
            self.make(f"t{i}", title=f"Lesson {i}")

        def consolidate(payload):
            for memory in payload["memories"]:
                provenance = memory["provenance"]
                self.assertLessEqual(len(provenance["direct_sources"]), 12)
                self.assertLessEqual(len(provenance["representative_trajectories"]), 5)
                for trajectory in provenance["representative_trajectories"]:
                    self.assertNotIn("evidence", trajectory)
                    self.assertEqual(
                        set(trajectory),
                        {"trajectory_id", "task_id", "run_status", "outcome_summary"},
                    )
            return {"action": "KEEP", "reason": "Distinct knowledge"}

        self.llm.responses["consolidate"] = consolidate
        self.memory.consolidate()

    def test_consolidation_accepts_flat_memory_content(self):
        originals = []
        for i in range(3):
            self.trajectory(f"t{i}")
            originals.append(self.make(f"t{i}", title=f"Lesson {i}"))
        flat = proposal("General filtering procedure", "skill")
        flat = {"kind": flat["kind"], **flat["content"]}
        self.llm.responses["consolidate"] = {
            "action": "CONSOLIDATE", "reason": "Supported procedure",
            "source_memories": [vars(ref) for ref in originals], "memory": flat,
        }
        derived = self.memory.consolidate()[0]
        self.assertEqual(derived.kind, "skill")

    def test_consolidation_resumes_derived_candidate_before_new_checks(self):
        originals = []
        for i in range(3):
            self.trajectory(f"t{i}")
            originals.append(self.make(f"t{i}", title=f"Lesson {i}"))
        derived, row = self.memory._prepare(proposal("Pending generalisation", "skill"))
        with self.memory._transaction():
            self.memory._insert(derived.table, row)
            for parent in originals:
                self.memory._source(derived, parent=parent, evidence_refs=[vars(parent)],
                                    relation="supports", note="Pending consolidation")
        self.llm.responses["judge"] = {"action": "KEEP", "reason": "Valid generalisation"}
        self.llm.responses["consolidate"] = {"action": "KEEP", "reason": "Already covered"}
        self.assertIn(derived, self.memory.consolidate())
        self.assertEqual(self.memory._row(derived)["status"], "active")
        operations = [operation for operation, _ in self.llm.calls]
        self.assertLess(operations.index("validate"), operations.index("consolidate"))

    def test_semantic_selection_cannot_bypass_evidence_minimum(self):
        refs = []
        for i in range(3):
            self.trajectory(f"t{i}")
            refs.append(self.make(f"t{i}"))
        self.llm.responses["consolidate"] = {
            "action": "CONSOLIDATE", "reason": "Only one source actually supports this",
            "source_memories": [vars(refs[0])], "memory": proposal("Generalisation"),
        }
        with self.assertRaisesRegex(ValueError, "minimum"):
            self.memory.consolidate()
        self.assertEqual(self.memory.connection.execute("SELECT count(*) FROM experiences").fetchone()[0], 3)

    def test_generalisation_supporting_its_source_adds_leaves_without_a_cycle(self):
        originals = []
        for i in range(3):
            self.trajectory(f"t{i}")
            originals.append(self.make(f"t{i}"))
        derived, row = self.memory._prepare(proposal("Generalisation"))
        with self.memory._transaction():
            self.memory._insert(derived.table, row)
            for parent in originals:
                self.memory._source(derived, parent=parent, evidence_refs=[vars(parent)],
                                    relation="supports", note="Reviewed generalisation")
        self.llm.responses["judge"] = {"action": "SUPPORT", "target": vars(originals[0]),
                                       "reason": "The existing claim already covers this"}
        self.assertEqual(self.memory.validate(derived), "rejected")
        self.assertEqual(len(self.memory.provenance(originals[0], supports_only=True)["trajectories"]), 3)
        self.assertEqual(len(self.memory.provenance(derived)["trajectories"]), 3)

    def test_candidate_activation_requires_provenance_and_skill_requires_done(self):
        ref, row = self.memory._prepare(proposal())
        with self.memory._transaction():
            self.memory._insert(ref.table, row)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "provenance"), self.memory._transaction():
            self.memory._status(ref, "active")
        invalid = proposal(kind="skill")
        invalid["content"]["completion_checks"] = []
        with self.assertRaisesRegex(ValueError, "When/How/Done"):
            self.memory._prepare(invalid)

    def test_invalid_embedding_is_rejected_before_inserting_any_candidate(self):
        self.trajectory()
        with patch.object(self.memory.embedder, "embed", return_value=[[float("nan"), 0]]):
            with self.assertRaisesRegex(ValueError, "finite"):
                self.memory.extract("t1")
        self.assertEqual(self.memory.connection.execute("SELECT count(*) FROM experiences").fetchone()[0], 0)

    def test_multihop_support_is_deduplicated_and_counterexamples_do_not_boost(self):
        self.trajectory()
        first, second, third = self.make(), self.make(), self.make()
        self.link(second, first)
        self.link(third, second)
        self.link(third, first)
        self.trajectory("t2")
        contrary = self.make("t2", relation="counterexample")
        self.link(third, contrary)
        self.assertEqual(len(self.memory.provenance(third)["trajectories"]), 2)
        self.assertEqual(len(self.memory.provenance(third, supports_only=True)["trajectories"]), 1)

    def test_provenance_cycles_updates_deletes_and_cross_agent_links_are_rejected(self):
        self.trajectory()
        first, second = self.make(), self.make()
        self.link(second, first)
        for target, parent in ((first, first), (first, second)):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "acyclic"):
                self.link(target, parent)
        self.trajectory("other", agent="webgen")
        with self.open(agent="webgen") as other:
            foreign = other.extract_and_validate("other")[0]
        with self.assertRaisesRegex(sqlite3.IntegrityError, "same agent"):
            self.link(first, foreign)
        for statement in ("DELETE FROM memory_sources", "UPDATE memory_sources SET note='changed'"):
            with self.assertRaises(sqlite3.IntegrityError), self.memory.connection:
                self.memory.connection.execute(statement)

    def test_agent_and_mode_isolation_and_format_only_adapter(self):
        self.trajectory()
        ref = self.make()
        self.trajectory("other", agent="webgen")
        with self.open(agent="webgen") as other:
            self.assertEqual(other.retrieve("Filter"), MemoryPacket())
            with self.assertRaises(ValueError):
                other.extract("t1")
            with self.assertRaises(ValueError):
                other.validate(ref)
        before = self.path.read_bytes()
        with self.open(mode="read_only") as reader:
            class Adapter:
                def run(self, task, memory):
                    return task, memory.render()
            task, formatted = reader.run("Filter", Adapter())
            self.assertEqual(task, "Filter")
            self.assertIn("Relevant Experiences", formatted)
            self.assertIn("Relevant Skills", formatted)
            self.assertIn("Filter insight", formatted)
            for call in (lambda: reader.extract("t1"), lambda: reader.validate(ref), reader.consolidate):
                with self.assertRaises(PermissionError):
                    call()
        self.assertEqual(self.path.read_bytes(), before)
        with patch("long_memory_runtime.connect_database", side_effect=AssertionError("Connected")):
            with LongMemory(Path(self.temp.name) / "missing.db", "bolt", memory_mode="disabled") as disabled:
                self.assertEqual(disabled.retrieve("Filter"), MemoryPacket())

    def test_reranking_cannot_promote_irrelevant_memory_and_respects_config(self):
        self.trajectory()
        strong = self.make(title="strong relevant")
        weaker = self.make(title="weaker relevant")
        unrelated = self.make(title="unrelated memory")
        for i in range(2, 7):
            self.trajectory(f"t{i}")
            for ref in (weaker, unrelated):
                with self.memory._transaction():
                    self.memory._source(ref, trajectory_id=f"t{i}", evidence_refs=[{"step_id": "1"}],
                                        relation="supports", note="Independent observation")
        config = MemoryConfig(top_k_experiences=1, evidence_weight=0.1, evidence_cap=5)
        with self.open(mode="read_only", config=config) as reader:
            result = reader.retrieve("Filter").experiences
            self.assertEqual(result[0].ref, weaker)
            self.assertEqual(result[0].supporting_trajectories, 6)
            audit = self.events[-1]["candidates"]["experience"]["discovered"]
            self.assertNotIn(unrelated.record_id, [item["ref"]["record_id"] for item in audit])
        with self.open(mode="read_only", config=MemoryConfig(evidence_weight=0)) as reader:
            self.assertEqual(reader.retrieve("Filter").experiences[0].ref, strong)

    def test_task_aspects_are_bounded_and_retrieval_may_be_empty(self):
        self.trajectory()
        self.make(title="unrelated memory")
        self.llm.responses["aspects"] = {"aspects": ["a", "a", "b", "c", "d"]}
        packet = self.memory.retrieve("Filter")
        self.assertEqual(packet, MemoryPacket())
        self.assertEqual(self.events[-1]["aspects"], ["a", "b", "c"])
        self.assertIn("not planning", self.llm.calls[-1][1]["instructions"])

    def test_semantic_relevance_filters_before_evidence_reranking(self):
        self.trajectory()
        ref = self.make()
        for index in range(2, 7):
            self.trajectory(f"t{index}")
            with self.memory._transaction():
                self.memory._source(ref, trajectory_id=f"t{index}",
                    evidence_refs=[{"step_id": "1"}], relation="supports", note="More evidence")
        self.llm.responses["relevance"] = {
            "applicable": [], "reasons": {ref.record_id: "Conflicts with current task constraints"}}
        self.assertEqual(self.memory.retrieve("Filter a list"), MemoryPacket())
        event = self.events[-1]
        self.assertEqual(len(event["candidates"]["experience"]["discovered"]), 1)
        self.assertEqual(event["candidates"]["experience"]["applicable_ranked"], [])

    def test_wrong_model_or_hash_and_archived_rows_cannot_be_retrieved(self):
        self.trajectory()
        ref = self.make()
        self.memory.embedder.model_id = "different-model"
        self.assertEqual(self.memory.retrieve("Filter"), MemoryPacket())
        self.memory.embedder.model_id = "offline-test@1"
        with self.memory.connection:
            self.memory.connection.execute("UPDATE experiences SET status='archived', archived_at='now'")
        self.assertEqual(self.memory.retrieve("Filter"), MemoryPacket())
        self.assertEqual(self.memory._row(ref)["status"], "archived")

    def test_invalid_outputs_roll_back_and_running_trace_cannot_extract(self):
        self.trajectory(status="running")
        with self.assertRaises(ValueError):
            self.memory.extract("t1")
        self.trajectory("t2")
        invalid = proposal()
        invalid["evidence_refs"] = [{"step_id": "invented"}]
        self.llm.responses["extract"] = {"memories": [invalid]}
        with self.assertRaisesRegex(ValueError, "locator"):
            self.memory.extract("t2")
        self.assertEqual(self.memory.connection.execute("SELECT count(*) FROM experiences").fetchone()[0], 0)
        ref = self.make("t2", active=False)
        self.llm.responses["judge"] = {"action": "SPLIT"}
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.memory.validate(ref)
        self.assertEqual(self.memory._row(ref)["status"], "candidate")

    def test_malformed_extraction_output_is_retried(self):
        self.trajectory()
        invalid = proposal()
        invalid.pop("relation")
        self.llm.responses["extract"] = {"memories": [invalid]}
        with self.assertRaises(ExtractionOutputError):
            self.memory.extract("t1")
        self.assertEqual(self.memory.connection.execute(
            "SELECT count(*) FROM experiences").fetchone()[0], 0)
        self.assertEqual(len([call for call in self.llm.calls if call[0] == "extract"]), 3)

    def test_external_run_log_and_config_validation(self):
        path = Path(self.temp.name) / "run" / "memory.jsonl"
        logger = JsonlRunLog(path)
        logger({"operation": "test", "error": "Example error"})
        self.assertEqual(json.loads(path.read_text())["operation"], "test")
        for kwargs in ({"min_consolidation_evidence": 0}, {"evidence_weight": float("nan")},
                       {"retrieval_min_similarity": 2}, {"max_task_aspects": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MemoryConfig(**kwargs)

    def test_versioned_long_memory_config_is_the_single_runner_source(self):
        settings = load_long_memory_settings(ROOT / "config/long_memory.json")
        self.assertEqual(settings.memory.consolidation_candidates, 4)
        self.assertEqual(settings.memory.max_evidence_chars, 12000)
        self.assertEqual(settings.memory_llm["deployment"], "webgen-memory-gpt41-mini")
        self.assertEqual(settings.embedding["deployment"], "webgen-memory-embedding")

    def test_memory_llm_long_rate_limit_delay_is_opt_in(self):
        class RateLimitError(Exception):
            status_code = 429

        class Completions:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise RateLimitError("limited")
                message = type("Message", (), {"content": '{"ok": true}'})()
                choice = type("Choice", (), {"message": message})()
                return type("Response", (), {"choices": [choice]})()

        completions = Completions()
        chat = type("Chat", (), {"completions": completions})()
        client = type("Client", (), {"chat": chat})()
        llm = AzureMemoryLLM(client, "memory", rate_limit_retries=1,
                             rate_limit_base_seconds=2,
                             rate_limit_long_retry_seconds=3600,
                             rate_limit_long_retries=1)
        with patch("long_memory_integrations.time.sleep") as sleep:
            self.assertEqual(llm.generate("judge", {"instructions": "test"}), {"ok": True})
        self.assertEqual(completions.calls, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 3600])

    def test_memory_llm_does_not_wait_an_hour_by_default(self):
        class RateLimitError(Exception):
            status_code = 429

        class Completions:
            def create(self, **kwargs):
                raise RateLimitError("limited")

        chat = type("Chat", (), {"completions": Completions()})()
        client = type("Client", (), {"chat": chat})()
        llm = AzureMemoryLLM(client, "memory", rate_limit_retries=0)
        with patch("long_memory_integrations.time.sleep") as sleep:
            with self.assertRaises(RateLimitError):
                llm.generate("judge", {"instructions": "test"})
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
