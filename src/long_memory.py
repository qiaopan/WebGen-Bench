"""Initialize and open the four-table, file-backed long-memory store.

Runtime policies and thin integration interfaces live in long_memory_runtime.py.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 2
APPLICATION_ID = 0x57474D31  # WGM1: WebGen Memory, format 1.
SCHEMA_PATH = Path(__file__).with_name("long_memory_schema.sql")
TABLE_NAMES = ("trajectories", "experiences", "skills", "memory_sources")


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


def _configure(connection: sqlite3.Connection, *, read_only: bool) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if read_only:
        connection.execute("PRAGMA query_only = ON")


def initialize_database(path: str | Path) -> Path:
    """Create an empty store atomically, or validate an existing version-2 store.

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
