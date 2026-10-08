#!/usr/bin/env python3
"""Create or validate an empty long-memory store without calling any model."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from long_memory import SCHEMA_VERSION, TABLE_NAMES, initialize_database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "memory" / "bolt" / "memory.db",
        help="Database file. Relative paths are resolved against the project root.",
    )
    args = parser.parse_args()
    if str(args.db) == ":memory:":
        parser.error("Long memory requires a persistent database file")
    database_path = args.db if args.db.is_absolute() else PROJECT_ROOT / args.db
    try:
        database_path = initialize_database(database_path)
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as error:
        parser.exit(1, f"Initialization failed: {error}\n")
    print(f"Long-memory database ready: {database_path}")
    print(f"Schema version: {SCHEMA_VERSION}")
    print(f"Tables: {', '.join(TABLE_NAMES)}")
    print("Existing data is preserved. No model calls or experiments were run.")


if __name__ == "__main__":
    main()
