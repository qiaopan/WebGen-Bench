#!/usr/bin/env python3
"""Create a deterministic, domain-block continual-learning task manifest.

This only reorganises the public WebGen-Bench task records.  It does not alter
the memory database or expose ``ui_instruct`` to a generation-time agent.

For every application type, records are ordered by stable task ID and emitted
as one contiguous batch.  This lets the second task in a domain immediately
use the first task's experience.  Batches are ordered by available task count
(largest first), then by name.  The memory bank itself remains global, so
later batches may still use genuinely relevant cross-domain knowledge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/test.jsonl"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("data/experiment_splits/continual_domain_blocks"))
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    domains: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        domain = row.get("application_type")
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError(f"Task {row.get('id')} has no application_type")
        domains[domain].append(row)
    for values in domains.values():
        values.sort(key=lambda row: str(row["id"]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    batches: list[dict] = []
    domain_names = sorted(domains, key=lambda name: (-len(domains[name]), name))
    for index, domain in enumerate(domain_names, start=1):
        batch_rows = domains[domain]
        filename = f"batch_{index:02d}.jsonl"
        path = args.output_dir / filename
        write_jsonl(path, batch_rows)
        batches.append({
            "batch": index,
            "application_type": domain,
            "file": str(path),
            "task_count": len(batch_rows),
            "task_ids": [str(row["id"]) for row in batch_rows],
        })

    manifest = {
        "protocol": "continual-domain-block-v1",
        "input": str(args.input),
        "input_sha256": sha256(args.input),
        "task_count": len(rows),
        "domain_count": len(domains),
        "memory_scope": "global_per_agent",
        "domain_policy": (
            "Domain is a retrieval preference derived from public task content, "
            "not a separate memory store or a hard cross-domain exclusion."
        ),
        "within_domain_order": "stable_task_id",
        "batches": batches,
        "domains": [
            {"application_type": name, "task_count": len(domains[name]),
             "task_ids": [str(row["id"]) for row in domains[name]]}
            for name in domain_names
        ],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output_dir), "task_count": len(rows),
                      "domain_count": len(domains),
                      "batch_sizes": [item["task_count"] for item in batches]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
