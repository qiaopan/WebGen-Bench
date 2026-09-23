#!/usr/bin/env python3
"""Run a resumable, global-memory continual WebGen experiment.

Tasks are supplied by the domain-block manifest created with
``build_continual_domain_manifest.py``.  There is one database per agent/run,
not one database per domain: application type is recorded only as provenance
metadata for later retrieval auditing.  A task is evaluated and locked before
its resulting trajectory is extracted into memory; no evaluator result is fed
back to repair that same task.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from selenium.common.exceptions import WebDriverException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "automatic_bolt_diy"))

from automatic_web_gen import automatic_web_gen  # noqa: E402
from long_memory import connect_database, initialize_database  # noqa: E402
from long_memory_integrations import (AzureEmbedder, AzureMemoryLLM, BoltAgentAdapter,
                                      exported_chat_evidence)  # noqa: E402
from long_memory_runtime import ExtractionOutputError, JsonlRunLog, LongMemory  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from post_task_reflection import (append_reflection, create_reflection,
                                  reflective_evidence_loader)  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402
from run_stage1 import (artifact, completed_keys, evaluations, extraction_refs,
                        extraction_validated, file_hash, run_evaluators)  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_line(message: str) -> None:
    """Emit a timestamped runner message; JSONL events retain full UTC timestamps."""
    print(f"[{utc_now()}] {message}", flush=True)


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": utc_now(), **event}, ensure_ascii=False,
                                sort_keys=True) + "\n")


@contextlib.contextmanager
def exclusive_evaluation_lock() -> None:
    """Serialize evaluators that use the host-global PM2 service namespace.

    Generated sites are evaluated through scripts that invoke ``pm2 delete all``
    and commonly bind port 5173.  Generator providers can run concurrently, but
    allowing two evaluators to run at once would let one evaluation replace the
    other run's website.  The lock deliberately covers evaluation only, not
    website generation or memory extraction.
    """
    lock_path = Path(os.environ.get(
        "WEBGEN_EVALUATION_LOCK", "/tmp/webgen-generated-site-evaluation.lock"
    ))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as stream:
        log_line("[evaluation] waiting for exclusive generated-site environment")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            log_line("[evaluation] acquired exclusive generated-site environment")
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            log_line("[evaluation] released exclusive generated-site environment")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_manifest(path: Path, requested_batches: set[int] | None) -> list[tuple[int, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("protocol") != "continual-domain-block-v1":
        raise ValueError("Unsupported continual manifest")
    result: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for item in data.get("batches", []):
        number = item.get("batch")
        if not isinstance(number, int):
            raise ValueError("Manifest batch is invalid")
        if requested_batches is not None and number not in requested_batches:
            continue
        file_name = item.get("file")
        if not isinstance(file_name, str):
            raise ValueError("Manifest batch has no file")
        group_path = Path(file_name)
        if not group_path.is_absolute():
            group_path = ROOT / group_path
        for task in load_jsonl(group_path):
            task_id = str(task.get("id", ""))
            if not task_id or task_id in seen:
                raise ValueError(f"Manifest task ID is missing or duplicated: {task_id}")
            seen.add(task_id)
            result.append((number, task))
    if not result:
        raise ValueError("Manifest selection contains no tasks")
    return result


def write_single_task(path: Path, task: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")


def upsert_trajectory(database: Path, task: dict, result: dict, destination: Path,
                      model: str, evaluation: list[dict], batch_number: int) -> str:
    chat = Path(result["chat_path"]).resolve()
    archive = Path(result["zip_path"]).resolve()
    with connect_database(database, read_only=False) as connection:
        row = connection.execute(
            "SELECT trajectory_id FROM trajectories WHERE agent_id=? AND task_id=? AND trace_path=?",
            ("bolt", str(task["id"]), str(chat)),
        ).fetchone()
        encoded = json.dumps(evaluation, ensure_ascii=False, sort_keys=True)
        if row:
            connection.execute("UPDATE trajectories SET evaluation_results=? WHERE trajectory_id=?",
                               (encoded, row[0]))
            return row[0]
        attempt = connection.execute(
            "SELECT COALESCE(MAX(attempt_no),0)+1 FROM trajectories WHERE agent_id=? AND task_id=?",
            ("bolt", str(task["id"])),
        ).fetchone()[0]
        trajectory_id = uuid.uuid4().hex
        prompt_path = Path(result.get("prompt_path", ""))
        generation_prompt = (prompt_path.read_text(encoding="utf-8")
                             if prompt_path.is_file() else "")
        connection.execute(
            "INSERT INTO trajectories (trajectory_id,task_id,agent_id,attempt_no,split_group,"
            "task_request,run_config,trace_path,artifact_refs,run_status,evaluation_results,finished_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'completed',?,?)",
            (trajectory_id, str(task["id"]), "bolt", attempt, "g3", task["instruction"],
             json.dumps({"model": model, "memory_mode": "continual", "protocol": "continual",
                         "batch": batch_number, "source_application_type": task["application_type"],
                         "output_directory": str(destination.resolve()),
                         "generation_prompt": generation_prompt,
                         "generation_prompt_path": str(prompt_path) if prompt_path.is_file() else ""}, sort_keys=True),
             str(chat), json.dumps([{"path": str(archive), "sha256": file_hash(archive)}],
                                   sort_keys=True), encoded, utc_now()),
        )
    return trajectory_id


def summary(events: list[dict]) -> dict:
    counts = {"passed": 0, "partial": 0, "failed": 0}
    for event in events:
        for item in event.get("evaluation", []):
            if item.get("outcome") in counts:
                counts[item["outcome"]] += 1
    return {"checks": counts, "total": sum(counts.values())}


def run_with_retries(memory: LongMemory, instruction: str, adapter: BoltAgentAdapter,
                     *, label: str, task_domain: str | None = None) -> dict:
    for attempt in range(3):
        try:
            return memory.run(instruction, adapter, task_domain=task_domain)
        except (TimeoutError, RuntimeError, WebDriverException, FileNotFoundError) as error:
            retryable = (isinstance(error, (TimeoutError, WebDriverException, FileNotFoundError)) or
                         "Generated website failed validation" in str(error))
            if not retryable or attempt == 2:
                raise
            log_line(f"[continual] retrying {label} after generation/browser failure "
                     f"({attempt + 1}/3)")
            time.sleep(5)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "data/experiment_splits/continual_domain_blocks/manifest.json")
    parser.add_argument("--batches", help="Comma-separated manifest batches (default: all)")
    parser.add_argument("--task-ids", help="Comma-separated diagnostic task IDs (default: all)")
    parser.add_argument("--modes", nargs="+", choices=("disabled", "continual"),
                        default=("disabled", "continual"))
    parser.add_argument("--output", type=Path,
                        default=ROOT / "outputs/experiment/continual_domain_blocks")
    parser.add_argument("--database", type=Path,
                        default=ROOT / "outputs/experiment/continual_domain_blocks/memory.db")
    parser.add_argument("--url", default="http://localhost:5173/")
    parser.add_argument("--generator-model",
                        help="Bolt/OpenAI-like model name; defaults to WEBGEN_GENERATOR_API_MODEL")
    parser.add_argument("--memory-base-url",
                        help="OpenAI-compatible Azure base URL for memory LLM and embeddings")
    parser.add_argument("--post-task-reflection", action="store_true",
                        help="Use locked GUI/visual evaluation evidence to build reflective memory for later tasks")
    parser.add_argument("--memory-representation", choices=("abstract", "case_only"),
                        default="abstract",
                        help="abstract = Experience/Skill; case_only = direct structured reflection cases")
    parser.add_argument("--manual-memory-file", type=Path,
                        help="Append a reviewed Golden Source text to the public task prompt")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--memory-config", type=Path,
                        default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    manual_memory = ""
    if args.manual_memory_file:
        manual_memory = args.manual_memory_file.resolve().read_text(encoding="utf-8").strip()
    requested_batches = (None if not args.batches else
                         {int(value.strip()) for value in args.batches.split(",") if value.strip()})
    requested_ids = (None if not args.task_ids else
                     {value.strip() for value in args.task_ids.split(",") if value.strip()})
    tasks = [(batch_no, task) for batch_no, task in load_manifest(args.manifest.resolve(), requested_batches)
             if requested_ids is None or str(task["id"]) in requested_ids]
    if not tasks:
        raise ValueError("No task remains after --task-ids filtering")

    load_dotenv(ROOT / ".env")
    output, database = args.output.resolve(), args.database.resolve()
    output.mkdir(parents=True, exist_ok=True)
    initialize_database(database)
    progress_path = output / "progress.jsonl"
    memory_log = JsonlRunLog(output / "memory-events.jsonl")
    completed = completed_keys(progress_path)
    settings = load_long_memory_settings(args.memory_config.resolve())
    # Generator routing lives inside the selected Bolt service.  Memory LLM and
    # embedding calls stay on Azure regardless of whether Bolt uses GPT or Qwen.
    azure_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    memory_base_url = (args.memory_base_url or os.environ.get("WEBGEN_MEMORY_BASE_URL")
                       or f"{azure_endpoint}/openai/v1")
    memory_api_key = os.environ["AZURE_OPENAI_API_KEY"]
    generator_model = args.generator_model or os.environ["WEBGEN_GENERATOR_API_MODEL"]
    client = OpenAI(api_key=memory_api_key, base_url=memory_base_url,
                    timeout=120, max_retries=2)
    llm = AzureMemoryLLM(client, settings.memory_llm["deployment"],
        max_tokens=settings.memory_llm["max_completion_tokens"],
        rate_limit_retries=settings.memory_llm["rate_limit_retries"],
        rate_limit_base_seconds=settings.memory_llm["rate_limit_base_seconds"],
        rate_limit_max_wait_seconds=settings.memory_llm["rate_limit_max_wait_seconds"],
        rate_limit_long_retry_seconds=settings.memory_llm["rate_limit_long_retry_seconds"],
        rate_limit_long_retries=settings.memory_llm["rate_limit_long_retries"])
    embedder = AzureEmbedder(client, settings.embedding["deployment"],
                             dimensions=settings.embedding["dimensions"])
    max_repair_attempts = int(os.environ.get("WEBGEN_MAX_REPAIR_ATTEMPTS", "1"))
    metadata = {"protocol": "continual-domain-block-v1", "manifest": str(args.manifest.resolve()),
                "manifest_sha256": file_hash(args.manifest.resolve()), "memory_config_sha256": file_hash(args.memory_config.resolve()),
                "generator_model": generator_model, "memory_model": settings.memory_llm["deployment"],
                "embedding_model": settings.embedding["deployment"],
                "evaluation_model": os.environ.get(
                    "WEBGEN_EVALUATOR_MODEL", os.environ.get("WEBVOYAGER_API_MODEL", "")),
                "post_task_reflection": args.post_task_reflection,
                "memory_representation": args.memory_representation,
                "modes": list(args.modes)}
    metadata_path = output / "run-metadata.json"
    if metadata_path.is_file() and json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
        raise RuntimeError(f"Output directory belongs to different continual settings: {metadata_path}")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    reports: list[dict] = []
    reflection_path = output / "post-task-reflections.jsonl"
    for ordinal, (batch_number, task) in enumerate(tasks, start=1):
        task_id = str(task["id"])
        task_file = output / "tasks" / task_id / "task.jsonl"
        write_single_task(task_file, task)
        # Pair order alternates by task so transient provider/Bolt conditions do
        # not consistently favour the same experimental arm.
        if set(args.modes) == {"disabled", "continual"}:
            modes = ("disabled", "continual") if ordinal % 2 else ("continual", "disabled")
        else:
            modes = tuple(args.modes)
        for mode in modes:
            key = f"batch:{batch_number}:task:{task_id}:{mode}"
            if key in completed:
                log_line(f"[resume] {key} complete")
                continue
            destination = output / "tasks" / task_id / mode
            adapter = BoltAgentAdapter(automatic_web_gen, 1, destination, args.url, generator_model,
                                       headless=not args.headed, max_repair_attempts=max_repair_attempts)
            if mode == "disabled":
                with LongMemory(database, "bolt", memory_mode="disabled") as memory:
                    result = run_with_retries(memory, task["instruction"], adapter,
                                              label=f"{task_id}:{mode}")
            elif args.memory_representation == "case_only":
                with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                                          config=settings.memory, log=memory_log) as memory:
                    instruction = task["instruction"] + ("\n\n" + manual_memory if manual_memory else "")
                    if manual_memory:
                        task_aspects = memory._aspects(task["instruction"])
                        adapted = llm.generate("manual_case_implementation_adaptation", {
                            "instructions": "For each historical case, compare it against the supplied task aspects. Reject any concrete field or action absent from the matched aspect (for example, do not add DOB when no aspect requires DOB), but preserve transferable abstract principles such as clear validation feedback. Return JSON {patterns:[{applicable,matched_aspect_index,matched_feature,implementation_pattern,verification,reason}]}.",
                            "current_task": task["instruction"], "task_aspects": task_aspects,
                            "historical_cases": manual_memory})
                        patterns = adapted.get("patterns", []) if isinstance(adapted, dict) else []
                        usable = [str(item.get("implementation_pattern", "")).strip()
                                  for item in patterns if isinstance(item, dict) and item.get("applicable")
                                  and str(item.get("implementation_pattern", "")).strip()]
                        if usable:
                            instruction = task["instruction"] + "\n\nCURRENT-TASK IMPLEMENTATION PATTERNS:\n- " + "\n- ".join(usable)
                    result = run_with_retries(memory, instruction, adapter,
                                              label=f"{task_id}:{mode}",
                                              task_domain=task["application_type"])
            else:
                with LongMemory(database, "bolt", memory_mode="learn", llm=llm,
                                embedder=embedder, config=settings.memory, log=memory_log) as memory:
                    result = run_with_retries(memory, task["instruction"], adapter,
                                              label=f"{task_id}:{mode}",
                                              task_domain=task["application_type"])
            # This is the first point at which hidden benchmark evaluation is accessed.
            # The generated archive has already been written and is never regenerated here.
            with exclusive_evaluation_lock():
                run_evaluators(destination, task_file, 1)
            evaluation = evaluations(destination, 1)
            event = {"key": key, "status": "complete", "batch": batch_number,
                     "task_id": task_id, "mode": mode, "evaluation": evaluation}
            if mode == "continual":
                trajectory_id = upsert_trajectory(database, task, result, destination,
                                                  generator_model, evaluation, batch_number)
                evidence_loader = exported_chat_evidence
                if args.post_task_reflection or args.memory_representation == "case_only":
                    with connect_database(database, read_only=True) as connection:
                        source = connection.execute(
                            "SELECT * FROM trajectories WHERE trajectory_id=?", (trajectory_id,)
                        ).fetchone()
                    reflection = create_reflection(llm, dict(source), exported_chat_evidence(dict(source)))
                    append_reflection(reflection_path, reflection)
                    event["reflection_id"] = reflection["reflection_id"]
                    # ``reflection_count`` used to look like an inner retry count.
                    # Keep it only as a backwards-compatible alias for accepted
                    # strict-provenance items; raw archived cases are reported too.
                    event["accepted_reflection_count"] = reflection["accepted_reflection_count"]
                    event["raw_reflection_count"] = reflection["raw_reflection_count"]
                    event["reflection_count"] = reflection["accepted_reflection_count"]
                if args.memory_representation == "case_only":
                    with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                                              config=settings.memory, log=memory_log) as memory:
                        event["case_ids"] = memory.store(reflection)
                        # A second, cross-task reflection proposes a reusable
                        # Experience/Skill candidate.  It is logged only in this
                        # pilot; candidates are not injected into generation.
                        event["consolidation_review"] = memory.review_recurring_failures(event["case_ids"])
                        event["experience_candidate_record_id"] = memory.persist_experience_candidate(
                            event["consolidation_review"])
                    refs = []
                else:
                    evidence_loader = reflective_evidence_loader(exported_chat_evidence, reflection_path)
                    with LongMemory(database, "bolt", memory_mode="learn", llm=llm,
                                    embedder=embedder, config=settings.memory,
                                    evidence_loader=evidence_loader, log=memory_log) as memory:
                        if extraction_validated(memory_log.path, trajectory_id):
                            refs = []
                        else:
                            existing = extraction_refs(memory_log.path, trajectory_id)
                            try:
                                refs = existing or memory.extract_and_validate(trajectory_id)
                                if existing:
                                    for ref in existing:
                                        memory.validate(ref)
                            except ExtractionOutputError as error:
                                event.update({"status": "pending_memory_schema", "trajectory_id": trajectory_id,
                                              "error": str(error)})
                                append_event(progress_path, event)
                                log_line(f"[continual] pending {ordinal}/{len(tasks)} {task_id}: {error}")
                                continue
                event.update({"trajectory_id": trajectory_id,
                              "candidate_refs": [{"kind": ref.kind, "record_id": ref.record_id}
                                                 for ref in refs]})
            append_event(progress_path, event)
            completed.add(key)
            reports.append(event)
            log_line(f"[continual] completed {ordinal}/{len(tasks)} batch {batch_number} "
                     f"{task_id} {mode}")

    report = {"pipeline_status": "completed", "completed_at": utc_now(), "task_count": len(tasks),
              "selected_batches": sorted(requested_batches) if requested_batches else None,
              "selected_task_ids": sorted(requested_ids) if requested_ids else None,
              "new_events": reports, "new_summary": summary(reports), **metadata}
    (output / "continual-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_line(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
