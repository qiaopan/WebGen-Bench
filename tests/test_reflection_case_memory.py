from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from long_memory import initialize_database
from long_memory_runtime import MemoryConfig
from reflection_case_memory import ReflectionCaseMemory


class Embedder:
    model_id = "case-test@1"

    def embed(self, texts):
        # A fixed nonzero vector is enough to test storage/retrieval plumbing.
        return [[1.0, 0.0] for _ in texts]


class LLM:
    def generate(self, operation, payload):
        self.operation, self.payload = operation, payload
        if operation == "case_task_aspects":
            return {"functional_aspects": [{"feature_object": "contact submission",
                     "user_trigger": "submit form", "expected_state_change": "show confirmation"}],
                    "appearance_aspects": []}
        first_candidates = next(iter(payload["candidates_by_aspect"].values()))
        return {"decisions": [{"case_id": first_candidates[0]["case_id"],
                               "matched_aspect_index": 0,
                               "verdict": "hard_match", "matched_current_requirement": "submit contact form",
                               "reason": "Same submit-to-confirm flow",
                               "implementation_checks": ["Show confirmation after submit"]}]}


class ReflectionCaseMemoryTests(unittest.TestCase):
    def test_case_only_stores_direct_case_and_retrieves_it_without_abstraction(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "memory.db")
            initialize_database(database)
            llm = LLM()
            reflection = {
                "trajectory_id": "trajectory-1", "public_task_requirement": "Build a contact page.",
                "appearance_reflection": None,
                "functional_reflections": [{
                    "feature_object": "contact submission", "user_trigger": "Submit valid details.",
                    "expected_state_change": "Show a confirmation.",
                    "observed_result": "No confirmation appeared.", "outcome": "failure",
                    "likely_cause_or_limitation": "Likely missing submit state.",
                    "preventative_action": "Bind submit to confirmation state.",
                    "verification": "Submit once and see confirmation.",
                    "transfer_limits": "Only confirmation-style forms.",
                    "evidence_refs": [{"kind": "evaluation_result", "result_index": 0}],
                    "provenance_status": "exact_or_normalised",
                }],
            }
            # The FK reflects normal runner order: trajectory is written before its case.
            import sqlite3
            with sqlite3.connect(database) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("INSERT INTO trajectories (trajectory_id,task_id,agent_id,attempt_no,split_group,task_request,run_config,trace_path,run_status,finished_at) VALUES ('trajectory-1','1','bolt',1,'g3','Build a contact page.','{}','trace','completed','now')")
            with ReflectionCaseMemory(database, "bolt", llm=llm, embedder=Embedder(),
                                      config=MemoryConfig(retrieval_min_similarity=-1)) as memory:
                created = memory.store(reflection)
                packet = memory.retrieve("Build a form that confirms submission")
            self.assertEqual(len(created), 1)
            self.assertEqual(packet.cases[0].case_id, created[0])
            self.assertEqual(packet.cases[0].content["observed_result"], "No confirmation appeared.")
            self.assertEqual(llm.operation, "case_functional_relevance")
            self.assertNotIn("current_task_application", packet.cases[0].content)


if __name__ == "__main__":
    unittest.main()
