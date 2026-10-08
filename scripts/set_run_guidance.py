#!/usr/bin/env python3
"""Record on a run's run_facts row which memory lines its prompt carried and how many were implemented.

For runs made before this was recorded automatically. Inputs are the run's stage2.json (guidance and common
lines with their source cases) and a compliance.json from measure_guidance_compliance.py. Writes to the DB you name.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from long_memory import connect_database, ensure_optional_tables  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--trajectory-id", required=True)
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--compliance", type=Path)
    parser.add_argument("--delivered", choices=("yes", "no"), required=True)
    args = parser.parse_args()
    stage2 = json.loads(args.stage2.read_text(encoding="utf-8"))
    ids = [g["case_id"] for g in stage2.get("guidance", [])]
    ids += [cid for item in stage2.get("common_adaptation", {}).get("patterns", []) for cid in item.get("source_case_ids", [])]
    total = len(stage2.get("guidance", [])) + len(stage2.get("common", []))
    followed = None
    if args.compliance:
        followed = json.loads(args.compliance.read_text(encoding="utf-8"))["counts"].get("yes")
    with connect_database(args.database, read_only=False) as connection:
        ensure_optional_tables(connection)
        connection.execute("UPDATE run_facts SET prompt_delivered=?, guidance_case_ids=?, guidance_total=?, "
                           "guidance_followed=? WHERE trajectory_id=?",
                           (int(args.delivered == "yes"), json.dumps(list(dict.fromkeys(ids))), total, followed,
                            args.trajectory_id))
    print("ok", len(set(ids)), "cases,", followed, "/", total, "followed")


if __name__ == "__main__":
    main()
