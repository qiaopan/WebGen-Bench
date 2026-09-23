#!/usr/bin/env python3
"""Promote previously validated continual-memory candidates without another LLM call.

This is a one-time protocol migration for changing the admission threshold from
two independent trajectories to one.  It trusts only an existing ``admission``
event whose semantic action was KEEP or CONSOLIDATE, and only promotes records
that still have direct trajectory provenance.  It never promotes a pending,
rejected, or unsupported candidate.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def load_eligible(events_path: Path) -> set[tuple[str, str]]:
    eligible: set[tuple[str, str]] = set()
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        ref = event.get("ref", {})
        judgement = event.get("judgement", {})
        if (event.get("operation") == "admission" and event.get("status") == "candidate"
                and judgement.get("action") in {"KEEP", "CONSOLIDATE"}
                and ref.get("kind") in {"experience", "skill"}
                and isinstance(ref.get("record_id"), str)):
            eligible.add((ref["kind"], ref["record_id"]))
    return eligible


def direct_trajectory_count(connection: sqlite3.Connection, kind: str, record_id: str) -> int:
    field = "experience_record_id" if kind == "experience" else "skill_record_id"
    return connection.execute(
        f"SELECT COUNT(DISTINCT trajectory_id) FROM memory_sources "
        f"WHERE {field}=? AND trajectory_id IS NOT NULL",
        (record_id,),
    ).fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    eligible = load_eligible(args.events)
    promoted: list[dict[str, object]] = []
    with sqlite3.connect(args.database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for kind, record_id in sorted(eligible):
            table = "experiences" if kind == "experience" else "skills"
            row = connection.execute(
                f"SELECT status FROM {table} WHERE record_id=?", (record_id,)
            ).fetchone()
            if row is None or row[0] != "candidate":
                continue
            evidence_count = direct_trajectory_count(connection, kind, record_id)
            if evidence_count < 1:
                continue
            promoted.append({"kind": kind, "record_id": record_id,
                             "supporting_trajectories": evidence_count})
            if not args.dry_run:
                connection.execute(
                    f"UPDATE {table} SET status='active' WHERE record_id=? AND status='candidate'",
                    (record_id,),
                )

    event = {
        "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "operation": "protocol_migration_activate_validated_candidates",
        "threshold": 1,
        "dry_run": args.dry_run,
        "promoted": promoted,
    }
    print(json.dumps(event, ensure_ascii=False, indent=2))
    if not args.dry_run:
        with args.events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
