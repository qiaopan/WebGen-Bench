"""Initialize and open the file-backed long-memory store.

Runtime policies and thin integration interfaces live in long_memory_runtime.py.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 3
APPLICATION_ID = 0x57474D31  # WGM1: WebGen Memory, format 1.
SCHEMA_PATH = Path(__file__).with_name("long_memory_schema.sql")
TABLE_NAMES = ("trajectories", "reflection_cases", "experiences", "skills", "memory_sources")
# Optional side tables are created on first use and are not part of the validated core
# schema, so databases written before they existed still open. Core tables stay strict.
OPTIONAL_TABLES_DDL = {
    "run_facts": """CREATE TABLE IF NOT EXISTS run_facts (
    fact_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    trajectory_id TEXT,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    stack TEXT NOT NULL,
    generation_ok INTEGER NOT NULL CHECK (generation_ok IN (0, 1)),
    generation_attempts INTEGER,
    failure_phase TEXT,
    checks_passed INTEGER NOT NULL DEFAULT 0,
    checks_partial INTEGER NOT NULL DEFAULT 0,
    checks_failed INTEGER NOT NULL DEFAULT 0,
    causes TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(causes) AND json_type(causes) = 'array'),
    cause_outcomes TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(cause_outcomes) AND json_type(cause_outcomes) = 'object'),
    prompt_delivered INTEGER CHECK (prompt_delivered IN (0, 1)),
    guidance_case_ids TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(guidance_case_ids) AND json_type(guidance_case_ids) = 'array'),
    guidance_total INTEGER,
    guidance_followed INTEGER,
    UNIQUE (agent_id, task_id, trajectory_id)
) STRICT""",
    "check_facts": """CREATE TABLE IF NOT EXISTS check_facts (
    fact_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    trajectory_id TEXT NOT NULL,
    check_index INTEGER NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    category TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('passed', 'partial', 'failed')),
    stack TEXT NOT NULL,
    evidence_source TEXT CHECK (evidence_source IN ('operation', 'code', 'screenshot')),
    requirement_stated INTEGER CHECK (requirement_stated IN (0, 1)),
    UNIQUE (agent_id, trajectory_id, check_index)
) STRICT""",
    "case_supports": """CREATE TABLE IF NOT EXISTS case_supports (
    support_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    supported_case_id TEXT NOT NULL REFERENCES reflection_cases(case_id),
    supporting_trajectory_id TEXT NOT NULL REFERENCES trajectories(trajectory_id),
    channel TEXT NOT NULL CHECK (channel = 'appearance'),
    observed_result TEXT NOT NULL,
    preventative_action TEXT NOT NULL,
    evidence_refs TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(evidence_refs) AND json_type(evidence_refs) = 'array'),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (agent_id, supported_case_id, supporting_trajectory_id, preventative_action)
) STRICT""",
}


def _require_sqlite_features() -> None:
    if sqlite3.sqlite_version_info < (3, 38, 0):
        raise RuntimeError("Long memory requires SQLite 3.38 or newer with JSON support")


def _file_path(path: str | Path) -> Path:
    if str(path) == ":memory:":
        raise ValueError("Long memory requires a persistent database file")
    return Path(path).expanduser().resolve()


def _schema_statements() -> Iterator[str]:
    """Keep trigger bodies intact instead of splitting SQL on semicolons."""
    pending = ""
    for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise ValueError("The schema contains an incomplete SQL statement")


def _schema_signature(connection: sqlite3.Connection) -> tuple[tuple, ...]:
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT GLOB 'sqlite_*' ORDER BY type, name"
        )
        if row[2] not in OPTIONAL_TABLES_DDL
    )


@lru_cache(maxsize=1)
def _expected_signature() -> tuple[tuple, ...]:
    with closing(sqlite3.connect(":memory:")) as connection:
        for statement in _schema_statements():
            connection.execute(statement)
        return _schema_signature(connection)


def _validate_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    if version != SCHEMA_VERSION or application_id != APPLICATION_ID:
        raise ValueError(
            f"Not a supported long-memory database: version={version}, "
            f"application_id={application_id}. Expected schema version {SCHEMA_VERSION}."
        )
    if _schema_signature(connection) != _expected_signature():
        raise ValueError("Database schema differs from the current format; use a fresh database")


def ensure_optional_tables(connection: sqlite3.Connection) -> None:
    """Create side tables that a writable connection needs (idempotent, never drops data)."""
    for ddl in OPTIONAL_TABLES_DDL.values():
        connection.execute(ddl)
    # Columns added after a side table first shipped are migrated in place (core tables never change).
    columns = {row[1] for row in connection.execute("PRAGMA table_info(run_facts)")}
    for name, definition in (
            ("cause_outcomes", "TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(cause_outcomes) AND json_type(cause_outcomes) = 'object')"),
            ("prompt_delivered", "INTEGER CHECK (prompt_delivered IN (0, 1))"),
            ("guidance_case_ids", "TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(guidance_case_ids) AND json_type(guidance_case_ids) = 'array')"),
            ("guidance_total", "INTEGER"), ("guidance_followed", "INTEGER")):
        if name not in columns:
            connection.execute(f"ALTER TABLE run_facts ADD COLUMN {name} {definition}")


def _configure(connection: sqlite3.Connection, *, read_only: bool) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if read_only:
        connection.execute("PRAGMA query_only = ON")


def initialize_database(path: str | Path) -> Path:
    """Create an empty store atomically, or validate an existing version-3 store.

    Existing data is never dropped or overwritten. Unknown databases and schema
    versions are rejected. Initialization is an explicit setup operation, never
    part of a read-only or disabled experiment event.
    """
    _require_sqlite_features()
    database_path = _file_path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(database_path), timeout=5.0)) as connection:
        _configure(connection, read_only=False)
        # Acquire the write lock before checking so concurrent initializers agree.
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            if version == 0 and application_id == 0 and not _schema_signature(connection):
                for statement in _schema_statements():
                    connection.execute(statement)
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            _validate_schema(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return database_path


def connect_database(path: str | Path, *, read_only: bool = True) -> sqlite3.Connection:
    """Open an existing store with foreign keys enabled; callers must close it.

    Read-only is the default. This never creates a file or initializes a schema.
    Use read_only=False only for authorized learning writes during G1/G3.
    """
    _require_sqlite_features()
    database_path = _file_path(path)
    mode = "ro" if read_only else "rw"
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode={mode}", uri=True, timeout=5.0)
    try:
        _configure(connection, read_only=read_only)
        _validate_schema(connection)
    except BaseException:
        connection.close()
        raise
    return connection
