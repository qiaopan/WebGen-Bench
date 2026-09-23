#!/usr/bin/env python3
"""Resume only missing UI evaluator checks for one already-generated Bolt site."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/ui_test_bolt"))

from dotenv import load_dotenv
from start_service import start_services
from ui_eval_with_answer import (
    get_shell_start,
    run_webvoyager,
    ui_prompt_template,
    unzip_files,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--group-file", type=Path, required=True)
    parser.add_argument("--position", type=int, required=True,
                        help="1-based position of this website in group-file")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    output_dir = args.output_dir.resolve()
    group_file = args.group_file.resolve()
    position = args.position
    site_key = f"{position:06d}"
    zip_path = output_dir / f"{site_key}.zip"
    if not zip_path.is_file():
        raise FileNotFoundError(f"Generated website ZIP not found: {zip_path}")

    records = [json.loads(line) for line in group_file.read_text(encoding="utf-8").splitlines()]
    if not 1 <= position <= len(records):
        raise ValueError(f"position {position} is outside group (1..{len(records)})")
    record = records[position - 1]
    results_dir = output_dir / "extracted/results"
    missing = []
    for check_index, item in enumerate(record["ui_instruct"]):
        result_path = results_dir / f"task{site_key}_{check_index}" / "interact_messages.json"
        if result_path.is_file():
            continue
        missing.append({
            "web_name": record["id"],
            "id": f"{site_key}_{check_index}",
            "ques": ui_prompt_template.format(
                task=item["task"], expected_result=item["expected_result"]),
            "web": None,
            "expected_result": item["expected_result"],
            "task": item["task"],
        })

    if not missing:
        print(f"No missing UI checks for task {record['id']} (position {position}).")
        return

    output_root = output_dir / "extracted"
    unzip_files([str(zip_path)], str(output_root))
    commands = get_shell_start([str(zip_path)], str(output_root))
    ports = start_services(str(output_root), commands)
    port = ports.get(site_key)
    if not port:
        raise RuntimeError(f"Could not start generated website {site_key}; ports={ports}")

    for item in missing:
        item["web"] = f"http://localhost:{port}/"
    tasks_file = output_root / "tasks_test_with_answer.jsonl"
    tasks_file.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n"
                                          for item in missing), encoding="utf-8")
    print(f"Evaluating {len(missing)} missing checks for task {record['id']}: "
          f"{', '.join(item['id'] for item in missing)}", flush=True)
    try:
        run_webvoyager(output_root)
    finally:
        subprocess.run(["pm2", "delete", "all"], check=False)

    print(f"Finished missing checks for task {record['id']}.")


if __name__ == "__main__":
    main()
