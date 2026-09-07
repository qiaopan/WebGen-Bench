#!/usr/bin/env python3
"""Run the complete resumable Stage 1 long-memory experiment for Bolt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "automatic_bolt_diy"))

from automatic_web_gen import automatic_web_gen  # noqa: E402
from experiment_protocol import build_plan  # noqa: E402
from long_memory import connect_database, initialize_database  # noqa: E402
from long_memory_integrations import (AzureEmbedder, AzureMemoryLLM, BoltAgentAdapter,
                                      exported_chat_evidence)  # noqa: E402
from long_memory_runtime import (ExtractionOutputError, JsonlRunLog, LongMemory,
                                 MemoryRef)  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": utc_now(), **event}, ensure_ascii=False,
                                sort_keys=True) + "\n")


def completed_keys(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    latest = {}
    for item in load_jsonl(path):
        if "key" in item:
            latest[item["key"]] = item.get("status")
    return {key for key, status in latest.items() if status == "complete"}


def extraction_validated(path: Path, trajectory_id: str) -> bool:
    events = load_jsonl(path)
    extraction = next((item for item in events
                       if item.get("operation") == "extraction_commit"
                       and item.get("trajectory_id") == trajectory_id), None)
    if extraction is None:
        return False
    candidates = {json.dumps(ref, sort_keys=True)
                  for ref in extraction.get("candidates", [])}
    admitted = {json.dumps(item.get("ref"), sort_keys=True)
                for item in events
                if item.get("operation") == "admission"
                and item.get("ref") is not None}
    return candidates <= admitted


def extraction_refs(path: Path, trajectory_id: str) -> list[MemoryRef]:
    for item in load_jsonl(path):
        if item.get("operation") == "extraction_commit" and item.get("trajectory_id") == trajectory_id:
            return [MemoryRef(**ref) for ref in item.get("candidates", [])]
    return []


def artifact(output_dir: Path, position: int) -> dict:
    prefix = f"{position:06d}"
    result = {"chat_path": str((output_dir / f"{prefix}.json").resolve()),
              "zip_path": str((output_dir / f"{prefix}.zip").resolve()),
              "request_path": str((output_dir / f"{prefix}.request.json").resolve()),
              "skipped": True}
    if not all(Path(result[key]).is_file() for key in ("chat_path", "zip_path", "request_path")):
        raise RuntimeError(f"Incomplete generated artifact for position {position}: {output_dir}")
    return result


def ensure_current_ui_evaluation(output_dir: Path, position: int) -> None:
    results_dir = output_dir / "extracted/results"
    prefix = f"task{position:06d}_"
    if any(results_dir.glob(f"{prefix}*/interact_messages.json")):
        return
    log_path = output_dir / "extracted/log.jsonl"
    if not log_path.is_file():
        return
    current_zip = str((output_dir / f"{position:06d}.zip").resolve())
    entries = load_jsonl(log_path)
    remaining = [item for item in entries if str(Path(item.get("app_path", "")).resolve()) != current_zip]
    if len(remaining) != len(entries):
        log_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n"
                                      for item in remaining), encoding="utf-8")


def run_evaluators(output_dir: Path, group_file: Path, position: int) -> None:
    ensure_current_ui_evaluation(output_dir, position)
    environment = os.environ.copy()
    environment.pop("WEBVOYAGER_TASK_LIMIT", None)
    subprocess.run([sys.executable, str(ROOT / "src/ui_test_bolt/ui_eval_with_answer.py"),
                    "--in_dir", str(output_dir), "--test_file", str(group_file)],
                   cwd=ROOT, env=environment, check=True)
    subprocess.run([sys.executable, str(ROOT / "src/grade_appearance_bolt_diy/eval_appearance.py"),
                    str(output_dir), "-t", str(group_file)], cwd=ROOT,
                   env=environment, check=True)
    subprocess.run([sys.executable, str(ROOT / "src/grade_appearance_bolt_diy/compute_grade.py"),
                    "--in_dir", str(output_dir), "--test_file", str(group_file)],
                   cwd=ROOT, env=environment, check=True)


def evaluations(output_dir: Path, position: int) -> list[dict]:
    prefix = f"task{position:06d}_"
    values = []
    results_dir = output_dir / "extracted/results"
    for path in sorted(results_dir.glob(f"{prefix}*/interact_messages.json")):
        messages = json.loads(path.read_text(encoding="utf-8"))
        answer = next((str(message.get("content", "")) for message in reversed(messages)
                       if message.get("role") == "assistant" and
                       any(token in str(message.get("content", ""))
                           for token in ("ANSWER;", "YES", "NO", "PARTIAL"))), "")
        outcome = "partial" if "PARTIAL" in answer else "passed" if "YES" in answer else "failed"
        values.append({"check": path.parent.name, "outcome": outcome,
                       "answer": answer, "evidence": str(path.resolve())})
    appearance = output_dir / f"extracted/{position:06d}/shots/result.json"
    if appearance.is_file():
        result = json.loads(appearance.read_text(encoding="utf-8"))
        values.append({"check": "appearance", "outcome": "scored",
                       "model_output": result.get("model_output"),
                       "model": result.get("model"), "usage": result.get("usage"),
                       "evidence": str(appearance.resolve())})
    if not values:
        raise RuntimeError(f"No evaluation result for position {position}: {output_dir}")
    return values


def upsert_trajectory(db_path: Path, task: dict, position: int, result: dict,
                      output_dir: Path, model: str, evaluation: list[dict]) -> str:
    chat = Path(result["chat_path"])
    archive = Path(result["zip_path"])
    with connect_database(db_path, read_only=False) as connection:
        row = connection.execute(
            "SELECT trajectory_id FROM trajectories WHERE agent_id=? AND task_id=? AND trace_path=?",
            ("bolt", str(task["id"]), str(chat.resolve())),
        ).fetchone()
        encoded = json.dumps(evaluation, ensure_ascii=False, sort_keys=True)
        if row:
            connection.execute("UPDATE trajectories SET evaluation_results=? WHERE trajectory_id=?",
                               (encoded, row[0]))
            return row[0]
        trajectory_id = uuid.uuid4().hex
        attempt = connection.execute(
            "SELECT COALESCE(MAX(attempt_no),0)+1 FROM trajectories WHERE agent_id=? AND task_id=?",
            ("bolt", str(task["id"])),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO trajectories (trajectory_id,task_id,agent_id,attempt_no,split_group,"
            "task_request,run_config,trace_path,artifact_refs,run_status,evaluation_results,finished_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'completed',?,?)",
            (trajectory_id, str(task["id"]), "bolt", attempt, "g1", task["instruction"],
             json.dumps({"model": model, "memory_mode": "learn", "stage": "stage1",
                         "record_position": position, "output_directory": str(output_dir.resolve())},
                        sort_keys=True), str(chat.resolve()),
             json.dumps([{"path": str(archive.resolve()), "sha256": file_hash(archive)}],
                        sort_keys=True), encoded, utc_now()),
        )
        return trajectory_id


def ui_summary(output_dir: Path) -> dict:
    counts = {"passed": 0, "partial": 0, "failed": 0}
    for path in (output_dir / "extracted/results").glob("task*/interact_messages.json"):
        messages = json.loads(path.read_text(encoding="utf-8"))
        answer = "\n".join(str(item.get("content", "")) for item in messages
                           if item.get("role") == "assistant")
        outcome = "partial" if "PARTIAL" in answer else "passed" if "YES" in answer else "failed"
        counts[outcome] += 1
    return {"counts": counts, "total": sum(counts.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:5173/")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/experiment/stage1")
    parser.add_argument("--database", type=Path,
                        default=ROOT / "outputs/memory/bolt/memory.db")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--memory-config", type=Path,
                        default=ROOT / "config/long_memory.json")
    parser.add_argument("--stop-after-g1", action="store_true",
                        help="Consolidate and freeze G1, then stop before G2 generation")
    parser.add_argument("--accept-frozen-retrieval-update", action="store_true",
                        help="Use a revised retrieval runtime with the verified existing G1 snapshot")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = build_plan(ROOT, ROOT / "config/experiment_protocol.json", "stage1")
    (output / "run-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    progress_path = output / "progress.jsonl"
    memory_log = JsonlRunLog(output / "memory-events.jsonl")

    base_url = os.environ["WEBGEN_GENERATOR_BASE_URL"]
    api_key = os.environ.get("AZURE_OPENAI_API_KEY") or os.environ["DASHSCOPE_API_KEY"]
    generator_model = os.environ["WEBGEN_GENERATOR_API_MODEL"]
    settings = load_long_memory_settings(args.memory_config.resolve())
    memory_model = settings.memory_llm["deployment"]
    embedding_model = settings.embedding["deployment"]
    max_repair_attempts = int(os.environ.get("WEBGEN_MAX_REPAIR_ATTEMPTS", "1"))
    metadata = {"git_commit": plan["git_commit"], "config_sha256": plan["config_sha256"],
                "dataset_manifest_sha256": plan["dataset_manifest_sha256"], "url": args.url,
                "generator_model": generator_model, "memory_model": memory_model,
                "embedding_model": embedding_model}
    metadata["memory_config_sha256"] = file_hash(args.memory_config.resolve())
    metadata_path = output / "run-metadata.json"
    if metadata_path.is_file():
        existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for key in ("generation_git_commit", "generation_memory_config_sha256",
                    "retrieval_policy_updated_after_freeze"):
            if key in existing_metadata:
                metadata[key] = existing_metadata[key]
        revision_keys = {"git_commit", "memory_config_sha256"}
        comparable_existing = {key: existing_metadata.get(key) for key in metadata
                               if key not in revision_keys}
        comparable_current = {key: value for key, value in metadata.items()
                              if key not in revision_keys}
        if comparable_existing != comparable_current:
            raise RuntimeError(
                f"Stage 1 directory belongs to different frozen settings: {metadata_path}")
        revision_changed = (
            existing_metadata.get("git_commit") != metadata["git_commit"] or
            existing_metadata.get("memory_config_sha256") != metadata["memory_config_sha256"]
        )
        if revision_changed and "g1:frozen" in completed_keys(progress_path):
            if not args.accept_frozen_retrieval_update:
                raise RuntimeError(
                    "G1 is frozen under an earlier code/config revision; pass "
                    "--accept-frozen-retrieval-update to retain that snapshot and use the new "
                    "retrieval policy")
            snapshot = output / "frozen-memory.db"
            frozen_events = [item for item in load_jsonl(progress_path)
                             if item.get("key") == "g1:frozen" and item.get("status") == "complete"]
            if not snapshot.is_file() or not frozen_events or file_hash(snapshot) != frozen_events[-1].get("sha256"):
                raise RuntimeError("The existing frozen G1 snapshot failed integrity verification")
            metadata["generation_git_commit"] = existing_metadata.get(
                "generation_git_commit", existing_metadata.get("git_commit"))
            metadata["generation_memory_config_sha256"] = existing_metadata.get(
                "generation_memory_config_sha256", existing_metadata.get("memory_config_sha256"))
            metadata["retrieval_policy_updated_after_freeze"] = True
        elif existing_metadata.get("git_commit") != metadata["git_commit"]:
            metadata["generation_git_commit"] = existing_metadata.get(
                "generation_git_commit", existing_metadata.get("git_commit"))
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120, max_retries=2)
    llm = AzureMemoryLLM(client, memory_model,
        max_tokens=settings.memory_llm["max_completion_tokens"],
        rate_limit_retries=settings.memory_llm["rate_limit_retries"],
        rate_limit_base_seconds=settings.memory_llm["rate_limit_base_seconds"],
        rate_limit_max_wait_seconds=settings.memory_llm["rate_limit_max_wait_seconds"],
        rate_limit_long_retry_seconds=settings.memory_llm["rate_limit_long_retry_seconds"],
        rate_limit_long_retries=settings.memory_llm["rate_limit_long_retries"])
    embedder = AzureEmbedder(client, embedding_model,
                             dimensions=settings.embedding["dimensions"])
    config = settings.memory
    initialize_database(args.database)
    completed = completed_keys(progress_path)

    g1_file = ROOT / "data/experiment_splits/groups/group_01_memory_seed.jsonl"
    g1_records = load_jsonl(g1_file)
    g1_dir = output / "memory_seed/g1/learn"
    for position, task in enumerate(g1_records, start=1):
        key = f"g1:{task['id']}"
        generated_key = key + ":generated"
        if key in completed:
            print(f"[resume] {key} complete", flush=True)
            continue
        if generated_key in completed:
            result = artifact(g1_dir, position)
        else:
            adapter = BoltAgentAdapter(automatic_web_gen, position, g1_dir, args.url,
                                       generator_model, headless=not args.headed,
                                       max_repair_attempts=max_repair_attempts)
            with LongMemory(args.database, "bolt", memory_mode="learn", llm=llm,
                            embedder=embedder, config=config, log=memory_log) as memory:
                result = memory.run(task["instruction"], adapter)
            append_event(progress_path, {"key": generated_key, "status": "complete"})
            completed.add(generated_key)
        run_evaluators(g1_dir, g1_file, position)
        evaluation = evaluations(g1_dir, position)
        trajectory_id = upsert_trajectory(args.database, task, position, result, g1_dir,
                                          generator_model, evaluation)
        validated = extraction_validated(memory_log.path, trajectory_id)
        if not validated:
            existing_refs = extraction_refs(memory_log.path, trajectory_id)
            with LongMemory(args.database, "bolt", memory_mode="learn", llm=llm,
                            embedder=embedder, config=config,
                            evidence_loader=exported_chat_evidence, log=memory_log) as memory:
                if existing_refs:
                    for ref in existing_refs:
                        memory.validate(ref)
                    refs = existing_refs
                else:
                    try:
                        refs = memory.extract_and_validate(trajectory_id)
                    except ExtractionOutputError as error:
                        append_event(progress_path, {
                            "key": key,
                            "status": "retryable_schema_error",
                            "trajectory_id": trajectory_id,
                            "memory_status": "pending_invalid_llm_output",
                            "error": str(error),
                            "candidate_refs": [],
                        })
                        completed.discard(key)
                        print(f"[stage1] pending {position}/{len(g1_records)} G1 "
                              f"(memory schema retry required: {error})", flush=True)
                        continue
        else:
            refs = []
        append_event(progress_path, {"key": key, "status": "complete",
                                     "trajectory_id": trajectory_id,
                                     "candidate_refs": [{"kind": ref.kind,
                                                         "record_id": ref.record_id}
                                                        for ref in refs]})
        completed.add(key)
        print(f"[stage1] completed {position}/{len(g1_records)} G1", flush=True)

    expected_g1 = {f"g1:{task['id']}" for task in g1_records}
    if not expected_g1 <= completed:
        raise RuntimeError("Cannot consolidate or freeze while G1 memory extraction is pending")

    if "g1:consolidated" not in completed:
        with LongMemory(args.database, "bolt", memory_mode="learn", llm=llm,
                        embedder=embedder, config=config,
                        evidence_loader=exported_chat_evidence, log=memory_log) as memory:
            created = memory.consolidate()
        append_event(progress_path, {"key": "g1:consolidated", "status": "complete",
                                     "created": [{"kind": ref.kind, "record_id": ref.record_id}
                                                 for ref in created]})
        completed.add("g1:consolidated")

    snapshot = output / "frozen-memory.db"
    if "g1:frozen" not in completed:
        with sqlite3.connect(args.database) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        append_event(progress_path, {"key": "g1:frozen", "status": "complete",
                                     "sha256": file_hash(snapshot)})
        completed.add("g1:frozen")
    snapshot_hash = file_hash(snapshot)

    if args.stop_after_g1:
        print(json.dumps({"pipeline_status": "g1_frozen",
                          "frozen_memory_sha256": snapshot_hash}, indent=2), flush=True)
        return

    g2_file = ROOT / "data/experiment_splits/groups/group_02_dev_evaluate.jsonl"
    g2_records = load_jsonl(g2_file)
    for position, task in enumerate(g2_records, start=1):
        modes = ("disabled", "read_only") if position % 2 else ("read_only", "disabled")
        for mode in modes:
            key = f"g2:{task['id']}:{mode}:generated"
            if key in completed:
                print(f"[resume] {key} complete", flush=True)
                continue
            destination = output / f"development_evaluation/g2/{mode}"
            adapter = BoltAgentAdapter(automatic_web_gen, position, destination, args.url,
                                       generator_model, headless=not args.headed,
                                       max_repair_attempts=max_repair_attempts)
            if mode == "disabled":
                with LongMemory(snapshot, "bolt", memory_mode="disabled") as memory:
                    memory.run(task["instruction"], adapter)
            else:
                with LongMemory(snapshot, "bolt", memory_mode="read_only", llm=llm,
                                embedder=embedder, config=config, log=memory_log) as memory:
                    memory.run(task["instruction"], adapter)
            append_event(progress_path, {"key": key, "status": "complete"})
            completed.add(key)
            if file_hash(snapshot) != snapshot_hash:
                raise RuntimeError("Frozen memory changed during G2 paired generation")
            print(f"[stage1] generated G2 {position}/{len(g2_records)} {mode}", flush=True)

    summaries = {}
    for mode in ("disabled", "read_only"):
        key = f"g2:{mode}:evaluated"
        destination = output / f"development_evaluation/g2/{mode}"
        if key not in completed:
            run_evaluators(destination, g2_file)
            append_event(progress_path, {"key": key, "status": "complete"})
            completed.add(key)
        summaries[mode] = ui_summary(destination)
        grade_path = destination / "extracted/grade.json"
        summaries[mode]["appearance"] = (json.loads(grade_path.read_text(encoding="utf-8"))
                                          if grade_path.is_file() else None)
    if file_hash(snapshot) != snapshot_hash:
        raise RuntimeError("Frozen memory changed during Stage 1 evaluation")

    with connect_database(snapshot) as connection:
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("trajectories", "experiences", "skills", "memory_sources")}
        memory_statuses = {row[0]: row[1] for row in connection.execute(
            "SELECT status,COUNT(*) FROM (SELECT status FROM experiences UNION ALL "
            "SELECT status FROM skills) GROUP BY status")}
    report = {"pipeline_status": "passed", "completed_at": utc_now(),
              "plan_event_count": plan["event_count"], "mode_event_counts": plan["mode_event_counts"],
              "frozen_memory_sha256": snapshot_hash, "table_counts": counts,
              "memory_status_counts": memory_statuses, "g2_evaluation": summaries,
              **metadata}
    (output / "stage1-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
