#!/usr/bin/env python3
"""Re-run the GUI evaluation of ONE functional check on an already generated website.

For a check whose evaluator produced no answer at all (an evaluator-side failure that the result parser
scores as failed). The website is not regenerated. The empty record is kept under extracted/noanswer_backup
and the new record replaces it in extracted/results, so the other checks are untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_continual_memory import exclusive_evaluation_lock  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True, help="generation dir holding 000001.zip")
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--check-index", type=int, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    output = args.output_dir.resolve()
    task = json.loads(args.task_file.read_text(encoding="utf-8").splitlines()[0])
    single = {**task, "ui_instruct": [task["ui_instruct"][args.check_index]]}
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "site"
        scratch.mkdir()
        for name in ("000001.zip", "000001.json"):
            shutil.copy(output / name, scratch / name)
        test_file = Path(tmp) / "single.jsonl"
        test_file.write_text(json.dumps(single, ensure_ascii=False) + "\n", encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("WEBVOYAGER_TASK_LIMIT", None)
        with exclusive_evaluation_lock():
            subprocess.run([sys.executable, str(ROOT / "src/ui_test_bolt/ui_eval_with_answer.py"),
                            "--in_dir", str(scratch), "--test_file", str(test_file)],
                           cwd=ROOT, env=environment, check=True)
        new = scratch / "extracted/results/task000001_0"
        if not (new / "interact_messages.json").is_file():
            raise SystemExit("re-evaluation produced no record")
        target = output / f"extracted/results/task000001_{args.check_index}"
        backup = output / "extracted/noanswer_backup" / target.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.move(str(target), str(backup))
        shutil.copytree(new, target)
    print("replaced", target, "(old record kept at", backup, ")")


if __name__ == "__main__":
    main()
