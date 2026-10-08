#!/usr/bin/env python3
"""Validate the experiment protocol and build its deterministic run plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiment_protocol import build_plan  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "experiment_protocol.json",
    )
    parser.add_argument("--stage", choices=("all", "stage1", "stage2", "stage3"), default="all")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output. If omitted, validate and print only a summary.",
    )
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else PROJECT_ROOT / args.config
    plan = build_plan(PROJECT_ROOT, config_path, args.stage)

    if args.output:
        output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Run plan: {output_path}")

    print(f"Protocol valid: {plan['protocol_name']}")
    print(f"Git commit: {plan['git_commit']}")
    print(f"Stage selection: {plan['selected_stage']}")
    print(f"Website-generation events: {plan['event_count']}")
    print("Memory-mode events: " + ", ".join(f"{key}={value}" for key, value in plan["mode_event_counts"].items()))


if __name__ == "__main__":
    main()
