from __future__ import annotations

import hashlib
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from long_memory import (  # noqa: E402
    APPLICATION_ID,
    SCHEMA_VERSION,
    TABLE_NAMES,
    connect_database,
    initialize_database,
)


class LongMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "memory.db"
        initialize_database(self.path)
        self.connection = connect_database(self.path, read_only=False)
        self.addCleanup(self.connection.close)

    def insert(self, table: str, values: dict) -> None:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self.connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values())
        )

    def trajectory(self, **overrides) -> None:
        values = {
            "trajectory_id": "t1", "task_id": "task1", "agent_id": "bolt",
            "attempt_no": 1, "split_group": "g1", "task_request": "Build a product list",
            "run_config": '{"model":"test-model","memory_mode":"learn"}',
            "trace_path": "traces/t1.jsonl",
        }
        self.insert("trajectories", values | overrides)

    def experience(self, **overrides) -> None:
        values = {
            "record_id": "e1v1", "experience_id": "e1", "agent_id": "bolt", "version_no": 1,
            "title": "Reset pagination after filtering", "condition": "A filter changes",
            "recommended_action": "Reset the page before rendering the filtered list",
            "verification": "The first page shows the expected filtered items",
            "status": "active",
        }
        self.insert("experiences", values | overrides)

    def skill(self, **overrides) -> None:
        values = {
            "record_id": "s1v1", "skill_id": "s1", "agent_id": "bolt", "version_no": 1,
            "name": "Build a filterable list", "goal": "Deliver a working product list",
            "conditions": "Client-side filtering and pagination",
            "workflow": '[{"step_id":"filter","action":"Filter before pagination"}]',
            "completion_checks": '["Changing a filter updates the list"]',
            "status": "active",
        }
        self.insert("skills", values | overrides)

    def source(self, **overrides) -> None:
        values = {
            "source_id": "source1", "experience_record_id": "e1v1", "trajectory_id": "t1",
            "evidence_refs": '[{"kind":"trace_step","step_id":"step7"}]',
            "relation": "supports", "note": "The recorded filter check passed",
        }
        self.insert("memory_sources", values | overrides)

    def archive(self, table: str, record_id: str) -> None:
        self.connection.execute(
            f"UPDATE {table} SET status = 'archived', archived_at = ? WHERE record_id = ?",
            ("2026-09-05T12:00:00.000Z", record_id),
        )

    def test_exactly_four_tables_and_expected_pragmas(self) -> None:
        tables = self.connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
        self.assertEqual({row[0] for row in tables}, set(TABLE_NAMES))
        for name, expected in (("user_version", SCHEMA_VERSION), ("application_id", APPLICATION_ID),
                               ("foreign_keys", 1)):
            self.assertEqual(self.connection.execute(f"PRAGMA {name}").fetchone()[0], expected)
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_reinitialization_preserves_rows_and_file(self) -> None:
        self.trajectory()
        self.connection.commit()
        before = self.path.read_bytes()
        initialize_database(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM trajectories").fetchone()[0], 1)

    def test_unknown_database_is_not_modified(self) -> None:
        foreign_path = Path(self.directory.name) / "unrelated.db"
        with closing(sqlite3.connect(foreign_path)) as other:
            # The underscore must be literal when filtering internal SQLite names.
            other.execute("CREATE TABLE sqliteXuser_data (value TEXT)")
            other.execute("INSERT INTO sqliteXuser_data VALUES ('preserve this')")
            other.commit()
        before = foreign_path.read_bytes()
        with self.assertRaises(ValueError):
            initialize_database(foreign_path)
        self.assertEqual(foreign_path.read_bytes(), before)

    def test_unknown_schema_version_is_rejected(self) -> None:
        self.connection.execute("PRAGMA user_version = 99")
        with self.assertRaises(ValueError):
            initialize_database(self.path)
        with self.assertRaises(ValueError):
            connect_database(self.path)

    def test_changed_schema_requires_fresh_database(self) -> None:
        self.connection.execute("DROP INDEX experiences_one_active_version")
        with self.assertRaisesRegex(ValueError, "fresh database"):
            initialize_database(self.path)

    def test_failed_initialization_rolls_back_all_schema_changes(self) -> None:
        target = Path(self.directory.name) / "failed.db"
        with patch("long_memory._validate_schema", side_effect=ValueError("Simulated validation failure")):
            with self.assertRaises(ValueError):
                initialize_database(target)
        with closing(sqlite3.connect(target)) as other:
            self.assertEqual(other.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone()[0], 0)
            self.assertEqual(other.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(other.execute("PRAGMA application_id").fetchone()[0], 0)

    def test_concurrent_initialization_is_safe(self) -> None:
        target = Path(self.directory.name) / "concurrent.db"
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(initialize_database, [target] * 4))
        self.assertEqual(paths, [target.resolve()] * 4)
        with closing(connect_database(target)) as other:
            self.assertEqual(other.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_read_only_is_default_and_rejects_data_and_schema_writes(self) -> None:
        with closing(connect_database(self.path)) as reader:
            self.assertEqual(reader.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            for statement in ("DELETE FROM trajectories", "CREATE TABLE forbidden (id INTEGER)"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.OperationalError):
                    reader.execute(statement)

    def test_opening_a_missing_file_never_creates_it(self) -> None:
        target = Path(self.directory.name) / "missing.db"
        for read_only in (True, False):
            with self.subTest(read_only=read_only), self.assertRaises(sqlite3.OperationalError):
                connect_database(target, read_only=read_only)
            self.assertFalse(target.exists())

    def test_memory_only_database_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            initialize_database(":memory:")

    def test_paths_with_uri_characters_work(self) -> None:
        target = Path(self.directory.name) / "a folder" / "memory #1?.db"
        initialize_database(target)
        with closing(connect_database(target)) as other:
            self.assertEqual(other.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_unknown_counts_and_usage_remain_null(self) -> None:
        self.trajectory()
        row = self.connection.execute("SELECT * FROM trajectories").fetchone()
        for field in ("agent_turn_count", "api_retry_count", "repair_round_count", "token_usage",
                      "evaluation_results", "finished_at"):
            self.assertIsNone(row[field])

    def test_counts_and_completion_state_are_checked(self) -> None:
        for invalid in ({"agent_turn_count": -1}, {"api_retry_count": -1},
                        {"repair_round_count": -1}, {"attempt_no": 0},
                        {"agent_turn_count": 2, "repair_round_count": 3},
                        {"run_status": "completed"}, {"finished_at": "2026-09-05T12:00:00.000Z"}):
            with self.subTest(invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.trajectory(**invalid)
        self.trajectory(agent_turn_count=4, api_retry_count=2, repair_round_count=1,
                        run_status="completed", finished_at="2026-09-05T12:00:00.000Z")

    def test_evaluation_groups_cannot_enter_the_memory_store(self) -> None:
        for group in ("g2", "g4", "g5", "unknown"):
            with self.subTest(group=group), self.assertRaises(sqlite3.IntegrityError):
                self.trajectory(split_group=group)
        self.trajectory(split_group="g3")

    def test_full_task_retries_need_distinct_attempt_numbers(self) -> None:
        self.trajectory()
        with self.assertRaises(sqlite3.IntegrityError):
            self.trajectory(trajectory_id="t2")
        self.trajectory(trajectory_id="t2", attempt_no=2)

    def test_trajectory_identity_is_immutable_but_run_metrics_can_update(self) -> None:
        self.trajectory()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("UPDATE trajectories SET agent_id = 'another-agent'")
        self.connection.execute("UPDATE trajectories SET agent_turn_count = 3")

    def test_json_fields_reject_invalid_or_wrong_container_types(self) -> None:
        cases = (
            (self.trajectory, {"run_config": "[]"}),
            (self.trajectory, {"artifact_refs": "{}"}),
            (self.trajectory, {"evaluation_results": "{}"}),
            (self.trajectory, {"token_usage": "[]"}),
            (self.trajectory, {"run_config": "not-json"}),
            (self.skill, {"workflow": "[]"}),
            (self.skill, {"completion_checks": "[]"}),
            (self.skill, {"experience_refs": "{}"}),
            (self.skill, {"inputs": "[]"}),
            (self.skill, {"tool_templates": "{}"}),
        )
        for helper, invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(sqlite3.DatabaseError):
                helper(**invalid)

    def test_experience_needs_a_lesson_or_legacy_action(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.experience(recommended_action=None)
        self.experience(recommended_action=None, avoid_action="Do not keep an invalid page index")
        self.experience(record_id="observation", experience_id="observation",
                        recommended_action=None, lesson="A stale page index hides matching items")

    def test_one_active_version_and_unique_version_numbers_for_both_types(self) -> None:
        for table, helper, prefix in (("experiences", self.experience, "e"), ("skills", self.skill, "s")):
            with self.subTest(table=table):
                helper()
                with self.assertRaises(sqlite3.IntegrityError):
                    helper(record_id=f"{prefix}1v2", version_no=2)
                self.archive(table, f"{prefix}1v1")
                with self.assertRaises(sqlite3.IntegrityError):
                    helper(record_id=f"{prefix}duplicate", version_no=1)
                helper(record_id=f"{prefix}1v2", version_no=2)
                self.assertEqual(self.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE status = 'active'"
                ).fetchone()[0], 1)

    def test_memory_content_cannot_be_edited_in_place(self) -> None:
        self.experience()
        self.skill()
        for statement in ("UPDATE experiences SET title = 'Changed title'",
                          "UPDATE skills SET workflow = '[\"Changed step\"]'"):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(statement)

    def test_failed_version_replacement_restores_previous_active_state(self) -> None:
        self.experience()
        self.connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.connection:
                self.archive("experiences", "e1v1")
                self.experience(record_id="e1v2", version_no=2, title="")
        self.assertEqual(self.connection.execute(
            "SELECT status FROM experiences WHERE record_id = 'e1v1'"
        ).fetchone()[0], "active")

    def test_rollback_creates_new_version_instead_of_reactivating_archive(self) -> None:
        for table, helper, prefix in (("experiences", self.experience, "e"), ("skills", self.skill, "s")):
            with self.subTest(table=table):
                helper()
                self.archive(table, f"{prefix}1v1")
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(
                        f"UPDATE {table} SET status = 'active', archived_at = NULL"
                    )
                helper(record_id=f"{prefix}1v2", version_no=2, restored_from_record_id=f"{prefix}1v1")

    def test_restoration_cannot_reference_another_identity(self) -> None:
        self.experience()
        with self.assertRaises(sqlite3.IntegrityError):
            self.experience(record_id="e2v2", experience_id="e2", version_no=2,
                            restored_from_record_id="e1v1")
        self.skill()
        with self.assertRaises(sqlite3.IntegrityError):
            self.skill(record_id="s2v2", skill_id="s2", version_no=2, restored_from_record_id="s1v1")

    def test_embeddings_require_complete_consistent_metadata(self) -> None:
        valid = {
            "embedding": struct.pack("<2f", 1.0, 0.0), "embedding_dim": 2,
            "embedding_model": "test-encoder@fixed-revision",
            "embedding_text_hash": hashlib.sha256(b"Exact encoded text").hexdigest(),
        }
        for helper in (self.experience, self.skill):
            for invalid in ({"embedding": valid["embedding"]}, valid | {"embedding_dim": 3},
                            valid | {"embedding_model": ""}, valid | {"embedding_text_hash": "invalid"}):
                with self.subTest(helper=helper.__name__, invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                    helper(**invalid)
            helper(**valid)

    def test_sources_target_exactly_one_existing_memory_version(self) -> None:
        self.trajectory()
        self.experience()
        self.skill()
        for invalid in ({"experience_record_id": None}, {"skill_record_id": "s1v1"},
                        {"experience_record_id": "missing"}, {"trajectory_id": "missing"}):
            with self.subTest(invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.source(**invalid)
        self.source()

    def test_sources_reject_cross_agent_inserts_and_updates(self) -> None:
        self.trajectory()
        self.trajectory(trajectory_id="t2", agent_id="webgen-agent")
        self.experience()
        with self.assertRaises(sqlite3.IntegrityError):
            self.source(trajectory_id="t2")
        self.source()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("UPDATE memory_sources SET trajectory_id = 't2'")

    def test_many_to_many_sources_survive_archival_and_do_not_move_to_new_version(self) -> None:
        self.trajectory()
        self.trajectory(trajectory_id="t2", task_id="task2")
        self.experience()
        self.skill()
        self.source()
        self.source(source_id="source2", experience_record_id=None, skill_record_id="s1v1")
        self.source(source_id="source3", experience_record_id=None, skill_record_id="s1v1",
                    trajectory_id="t2", relation="counterexample")
        self.archive("skills", "s1v1")
        self.skill(record_id="s1v2", version_no=2)
        rows = self.connection.execute(
            "SELECT s.status, COUNT(*) FROM memory_sources AS m "
            "JOIN skills AS s ON s.record_id = m.skill_record_id GROUP BY s.status"
        ).fetchall()
        self.assertEqual([tuple(row) for row in rows], [("archived", 2)])
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_duplicate_evidence_is_rejected_but_a_counterexample_is_distinct(self) -> None:
        self.trajectory()
        self.experience()
        self.source()
        with self.assertRaises(sqlite3.IntegrityError):
            self.source(source_id="duplicate")
        self.source(source_id="counterexample", relation="counterexample")

    def test_source_evidence_note_and_relation_are_required(self) -> None:
        self.trajectory()
        self.experience()
        for invalid in ({"evidence_refs": "[]"}, {"evidence_refs": "{}"},
                        {"note": ""}, {"relation": "unknown"}):
            with self.subTest(invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.source(**invalid)

    def test_referenced_trajectory_or_memory_cannot_be_deleted(self) -> None:
        self.trajectory()
        self.experience()
        self.source()
        for table in ("trajectories", "experiences"):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(f"DELETE FROM {table}")

    def test_cli_creates_an_empty_database_and_can_be_repeated(self) -> None:
        target = Path(self.directory.name) / "cli.db"
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / "init_long_memory.py"), "--db", str(target)],
                check=True, capture_output=True, text=True,
            )
            self.assertIn(f"Schema version: {SCHEMA_VERSION}", result.stdout)
        with closing(connect_database(target)) as other:
            for table in TABLE_NAMES:
                self.assertEqual(other.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_cli_rejects_memory_only_path(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "init_long_memory.py"), "--db", ":memory:"],
            check=False, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("persistent database file", result.stderr)


if __name__ == "__main__":
    unittest.main()
