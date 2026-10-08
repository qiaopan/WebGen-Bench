from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from post_task_reflection import (append_reflection, create_reflection,
                                  reflective_evidence_loader)


class ReflectionLLM:
    def generate(self, operation, payload):
        assert operation == "post_task_reflection"
        return {
            "task_summary": {"requirement_coverage": "Search and booking were requested.",
                             "verified_strengths": ["Search results appeared."],
                             "primary_functional_risks": ["Booking state was unclear."],
                             "primary_visual_observations": ["Readable hierarchy."]},
            "appearance_reflection": {
                "observed_result": "The screenshot has a readable heading hierarchy.",
                "likely_cause_or_limitation": "Observed visual strength.",
                "preventative_action": "Keep a visible title/result hierarchy.",
                "verification": "Inspect the rendered screenshot.",
                "transfer_limits": "Visual guidance only.",
                "evidence_refs": [{"result_index": 0}],
            },
            "functional_reflections": [{
                "feature_object": "booking confirmation", "user_trigger": "Select a time and submit.",
                "expected_state_change": "A confirmed booking should appear.",
                "observed_result": "The page remained unchanged after submit.",
                "outcome": "failure", "likely_cause_or_limitation": "Likely missing submit state.",
                "preventative_action": "Bind submit to a persisted confirmation state.",
                "verification": "Submit once and verify the confirmation is visible.",
                "transfer_limits": "Only reservation-style submit flows.",
                # A conventional locator, not an exact supplied wrapper.
                "evidence_refs": [{"check": "booking_submit"}],
            }, {
                "feature_object": "search", "user_trigger": "Enter a term.",
                "expected_state_change": "Matching results should update.",
                "observed_result": "Results visibly updated.", "outcome": "success",
                "likely_cause_or_limitation": "Observed in GUI trace.",
                "preventative_action": "Keep query and rendered results connected.",
                "verification": "Search a known term and inspect results.",
                "transfer_limits": "Only search-style flows.",
                # Deliberately unresolvable: it must remain archived, not vanish.
                "evidence_refs": [{"check": "not-present"}],
            }],
        }


class PostTaskReflectionTests(unittest.TestCase):
    def test_archives_unresolved_case_and_normalises_conventional_locator(self):
        trajectory = {"trajectory_id": "t-1", "task_request": "Build a booking search page."}
        evidence = [{"ref": {"kind": "evaluation_result", "result_index": 0,
                             "check": "booking_submit"},
                     "content": {"check": "booking_submit", "evidence": "/tmp/booking.json"}}]
        reflection = create_reflection(ReflectionLLM(), trajectory, evidence)
        self.assertEqual(reflection["raw_reflection_count"], 3)
        self.assertEqual(reflection["accepted_reflection_count"], 2)
        self.assertEqual(reflection["functional_reflections"][0]["provenance_status"],
                         "exact_or_normalised")
        self.assertEqual(reflection["functional_reflections"][1]["provenance_status"],
                         "unresolved")
        self.assertFalse(reflection["functional_reflections"][1]["accepted_for_memory"])

    def test_accepts_an_evaluator_evidence_path_as_an_unambiguous_locator(self):
        trajectory = {"trajectory_id": "t-1", "task_request": "Build a booking search page."}
        evidence = [{"ref": {"kind": "evaluation_result", "result_index": 0},
                     "content": {"evidence": "/tmp/booking.json"}}]
        result = ReflectionLLM().generate("post_task_reflection", {})
        result["functional_reflections"][0]["evidence_refs"] = ["/tmp/booking.json"]

        class PathLLM:
            def generate(self, *_):
                return result

        reflection = create_reflection(PathLLM(), trajectory, evidence)
        self.assertTrue(reflection["functional_reflections"][0]["accepted_for_memory"])
        self.assertEqual(reflection["functional_reflections"][0]["evidence_refs"],
                         [evidence[0]["ref"]])

    def test_loader_attaches_complete_case_even_without_strict_items(self):
        trajectory = {"trajectory_id": "t-1", "task_request": "Build a booking search page."}
        evidence = [{"ref": {"kind": "evaluation_result", "result_index": 0}, "content": "partial"}]
        reflection = create_reflection(ReflectionLLM(), trajectory, evidence)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reflections.jsonl"
            append_reflection(path, reflection)
            loaded = reflective_evidence_loader(lambda _: list(evidence), path)(trajectory)
        self.assertEqual(loaded[-1]["ref"]["kind"], "post_task_case")
        self.assertEqual(loaded[-1]["content"]["reflection_id"], reflection["reflection_id"])


if __name__ == "__main__":
    unittest.main()
