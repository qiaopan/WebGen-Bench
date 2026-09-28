#!/usr/bin/env python3
"""Among several runs of the same task, pick the most representative one (memory ingestion takes one run per task).

For every functional check take the majority outcome across the runs; the representative run is the one that
disagrees with the majority on the fewest checks (ties: the earliest listed). Prints the outcome table.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_stage1 import evaluations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("runs", nargs="+", type=Path, help="run output dirs (with tasks/<id>/continual)")
    args = parser.parse_args()
    table = {}
    for run in args.runs:
        checks = evaluations(run / "tasks" / args.task_id / "continual", 1)
        table[run.name] = {c["check"]: c["outcome"] for c in checks if c["check"] != "appearance"}
    names = list(table)
    majority = {check: Counter(table[n][check] for n in names).most_common(1)[0][0] for check in table[names[0]]}
    distance = {n: sum(table[n][c] != majority[c] for c in majority) for n in names}
    best = min(names, key=lambda n: (distance[n], names.index(n)))
    for n in names:
        print(f"{n:28} disagreements with majority: {distance[n]}  " + " ".join(f"{table[n][c][0]}" for c in majority))
    print("majority:", " ".join(v[0] for v in majority.values()))
    print("representative:", best)


if __name__ == "__main__":
    main()
