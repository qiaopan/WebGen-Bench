from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiment_protocol import build_plan, load_json, validate_protocol  # noqa: E402


CONFIG_PATH = PROJECT_ROOT / "config" / "experiment_protocol.json"


class ExperimentProtocolTests(unittest.TestCase):
    def test_full_plan_has_expected_counts_and_no_evaluation_writes(self) -> None:
        plan = build_plan(PROJECT_ROOT, CONFIG_PATH)
        self.assertEqual(plan["event_count"], 201)
        self.assertEqual(plan["mode_event_counts"], {"disabled": 80, "learn": 41, "read_only": 80})
        evaluation_events = [event for event in plan["events"] if event["group"] in {"g2", "g4", "g5"}]
        self.assertTrue(evaluation_events)
        self.assertTrue(all(not event["memory_write"] for event in evaluation_events))

    def test_paired_order_alternates(self) -> None:
        plan = build_plan(PROJECT_ROOT, CONFIG_PATH, "stage1")
        paired = [event for event in plan["events"] if event["group"] == "g2"]
        self.assertEqual([event["memory_mode"] for event in paired[:4]], ["disabled", "read_only", "read_only", "disabled"])

    def test_disabled_mode_has_no_memory_access(self) -> None:
        plan = build_plan(PROJECT_ROOT, CONFIG_PATH)
        disabled = [event for event in plan["events"] if event["memory_mode"] == "disabled"]
        self.assertTrue(all(not event["memory_read"] and not event["memory_write"] for event in disabled))

    def test_learning_on_evaluation_group_is_rejected(self) -> None:
        config = copy.deepcopy(load_json(CONFIG_PATH))
        config["groups"]["g2"]["allowed_modes"] = ["learn"]
        with self.assertRaises(ValueError):
            validate_protocol(PROJECT_ROOT, config)

    def test_plan_is_deterministic_except_for_git_commit(self) -> None:
        first = build_plan(PROJECT_ROOT, CONFIG_PATH)
        second = build_plan(PROJECT_ROOT, CONFIG_PATH)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
