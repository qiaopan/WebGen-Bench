#!/usr/bin/env python3
"""Run one G1 learning task, then one frozen G2 disabled/read-only pair."""

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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "automatic_bolt_diy"))

from automatic_web_gen import automatic_web_gen  # noqa: E402
from long_memory import connect_database, initialize_database  # noqa: E402
from long_memory_integrations import (AzureEmbedder, AzureMemoryLLM, BoltAgentAdapter,
                                      exported_chat_evidence)  # noqa: E402
from long_memory_runtime import (JsonlRunLog, LongMemory, MemoryConfig, MemoryPacket,
                                 MemoryRef)  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path, wanted: str) -> tuple[int, dict]:
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if str(value["id"]) == wanted:
            return index, value
    raise ValueError(f"Record {wanted} not found in {path}")


def artifact_result(result: dict) -> tuple[Path, Path]:
    chat, archive = Path(result["chat_path"]), Path(result["zip_path"])
    if not chat.is_file() or not archive.is_file():
        raise RuntimeError("Bolt did not export both chat JSON and project ZIP")
    return chat.resolve(), archive.resolve()


def ui_result(output_dir: Path, group_file: Path) -> tuple[Path, dict]:
    path = output_dir / "extracted/results/task000001_0/interact_messages.json"
    if not path.is_file():
        environment = os.environ.copy()
        environment["WEBVOYAGER_TASK_LIMIT"] = "1"
        subprocess.run([
            sys.executable, str(PROJECT_ROOT / "src/ui_test_bolt/ui_eval_with_answer.py"),
            "--in_dir", str(output_dir), "--test_file", str(group_file),
        ], cwd=PROJECT_ROOT, env=environment, check=True)
    messages = json.loads(path.read_text(encoding="utf-8"))
    answer = next((str(message.get("content", "")) for message in reversed(messages)
                   if message.get("role") == "assistant" and
                   ("ANSWER;" in str(message.get("content", "")) or
                    str(message.get("content", "")).strip() in ("YES", "NO", "PARTIAL"))), "")
    outcome = "partial" if "PARTIAL" in answer else "passed" if "YES" in answer else "failed"
    return path.resolve(), {"check": "webvoyager_ui_task_0", "outcome": outcome,
                            "evidence": str(path.resolve()), "answer": answer}


def insert_trajectory(db_path: Path, *, task: dict, chat: Path, archive: Path,
                      model: str, output_dir: Path, evaluation: dict) -> str:
    with connect_database(db_path, read_only=False) as connection:
        existing = connection.execute(
            "SELECT trajectory_id FROM trajectories WHERE agent_id=? AND task_id=? AND trace_path=?",
            ("bolt", str(task["id"]), str(chat)),
        ).fetchone()
        if existing is not None:
            connection.execute("UPDATE trajectories SET evaluation_results=? WHERE trajectory_id=?",
                               (json.dumps([evaluation], sort_keys=True), existing[0]))
            return existing[0]
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
             json.dumps({"model": model, "memory_mode": "learn", "smoke_test": True,
                         "output_directory": str(output_dir)}, sort_keys=True), str(chat),
             json.dumps([{"path": str(archive), "sha256": sha256(archive)}], sort_keys=True),
             json.dumps([evaluation], sort_keys=True), now()),
        )
    connection.close()
    return trajectory_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g1-id", default="000003")
    parser.add_argument("--g2-id", default="000004")
    parser.add_argument("--url", default="http://localhost:5173/")
    parser.add_argument("--output", type=Path,
                        default=PROJECT_ROOT / "outputs" / "smoke" / "long-memory")
    parser.add_argument("--database", type=Path,
                        default=PROJECT_ROOT / "outputs" / "memory" / "bolt" / "memory.db")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")

    base_url = os.environ["WEBGEN_GENERATOR_BASE_URL"]
    api_key = os.environ.get("AZURE_OPENAI_API_KEY") or os.environ["DASHSCOPE_API_KEY"]
    generator_model = os.environ["WEBGEN_GENERATOR_API_MODEL"]
    memory_model = os.environ.get("MEMORY_LLM_MODEL", generator_model)
    embedding_model = os.environ["MEMORY_EMBEDDING_MODEL"]
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120, max_retries=2)
    llm = AzureMemoryLLM(client, memory_model)
    embedder = AzureEmbedder(client, embedding_model)

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    events = JsonlRunLog(output / "memory-events.jsonl")
    initialize_database(args.database)
    g1_index, g1 = record(PROJECT_ROOT / "data/experiment_splits/groups/group_01_memory_seed.jsonl", args.g1_id)
    g1_dir = output / "g1-learn"
    g1_result = automatic_web_gen(g1_index, g1["instruction"], str(g1_dir), args.url,
                                  generator_model, "OpenAILike", headless=not args.headed)
    chat, archive = artifact_result(g1_result)
    g1_group = PROJECT_ROOT / "data/experiment_splits/groups/group_01_memory_seed.jsonl"
    _, g1_evaluation = ui_result(g1_dir, g1_group)
    trajectory_id = insert_trajectory(args.database, task=g1, chat=chat, archive=archive,
                                      model=generator_model, output_dir=g1_dir,
                                      evaluation=g1_evaluation)
    with LongMemory(args.database, "bolt", memory_mode="learn", llm=llm, embedder=embedder,
                    config=MemoryConfig(), evidence_loader=exported_chat_evidence, log=events) as memory:
        linked = memory.connection.execute(
            "SELECT 'experience', experience_record_id FROM memory_sources "
            "WHERE trajectory_id=? AND experience_record_id IS NOT NULL "
            "UNION SELECT 'skill', skill_record_id FROM memory_sources "
            "WHERE trajectory_id=? AND skill_record_id IS NOT NULL",
            (trajectory_id, trajectory_id),
        ).fetchall()
        if linked:
            candidates = [MemoryRef(kind, record_id) for kind, record_id in linked]
            for candidate in candidates:
                memory.validate(candidate)
        else:
            candidates = memory.extract_and_validate(trajectory_id)

    snapshot = output / "frozen-memory.db"
    with sqlite3.connect(args.database) as source, sqlite3.connect(snapshot) as target:
        source.backup(target)
    snapshot_hash_before = sha256(snapshot)

    g2_index, g2 = record(PROJECT_ROOT / "data/experiment_splits/groups/group_02_dev_evaluate.jsonl", args.g2_id)
    adapter = BoltAgentAdapter(automatic_web_gen, g2_index, output / "g2-disabled", args.url,
                               generator_model, headless=not args.headed)
    with LongMemory(snapshot, "bolt", memory_mode="disabled") as memory:
        disabled_result = memory.run(g2["instruction"], adapter)
    adapter.output_dir = output / "g2-read-only"
    with LongMemory(snapshot, "bolt", memory_mode="read_only", llm=llm, embedder=embedder,
                    config=MemoryConfig(), log=events) as memory:
        read_only_result = memory.run(g2["instruction"], adapter)
    if sha256(snapshot) != snapshot_hash_before:
        raise RuntimeError("Frozen memory changed during paired evaluation")
    artifact_result(disabled_result)
    artifact_result(read_only_result)
    g2_group = PROJECT_ROOT / "data/experiment_splits/groups/group_02_dev_evaluate.jsonl"
    _, disabled_evaluation = ui_result(output / "g2-disabled", g2_group)
    _, read_only_evaluation = ui_result(output / "g2-read-only", g2_group)
    ui_results = {"g1": g1_evaluation, "disabled": disabled_evaluation,
                  "read_only": read_only_evaluation}
    failed_ui = {name: result["outcome"] for name, result in ui_results.items()
                 if result["outcome"] != "passed"}

    retrieved = adapter.last_memory or MemoryPacket()

    with connect_database(snapshot) as connection:
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("trajectories", "experiences", "skills", "memory_sources")}
        statuses = {row[0]: row[1] for row in connection.execute(
            "SELECT status, COUNT(*) FROM (SELECT status FROM experiences UNION ALL "
            "SELECT status FROM skills) GROUP BY status")}
    connection.close()
    report = {"pipeline_status": "passed",
              "evaluation_status": "passed" if not failed_ui else "needs_review",
              "non_passing_ui_results": failed_ui,
              "g1_id": args.g1_id, "g2_id": args.g2_id,
              "generator_model": generator_model, "memory_model": memory_model,
              "embedding_model": embedding_model, "trajectory_id": trajectory_id,
              "candidate_refs": [{"kind": ref.kind, "record_id": ref.record_id} for ref in candidates],
              "frozen_memory_sha256": snapshot_hash_before, "table_counts": counts,
              "memory_status_counts": statuses,
              "ui_smoke_results": ui_results,
              "read_only_retrieved_memory": {
                  "experiences": [item.ref.record_id for item in retrieved.experiences],
                  "skills": [item.ref.record_id for item in retrieved.skills],
                  "packet_sha256": hashlib.sha256(retrieved.render().encode()).hexdigest(),
              },
              "paired_outputs": {"disabled": disabled_result, "read_only": read_only_result}}
    (output / "smoke-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
