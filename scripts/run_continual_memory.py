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
from guidance_selfcheck import make_compliance_check
from generation_failure_memory import (failed_evaluation, failed_generation_evidence, failure_reflection,
                                       repair_hint_factory)
from memory_statistics import (BUILD_FAILURE_LABEL, prompt_stats, setup_label, build_check_rows, detect_stack, known_categories, known_labels, label_causes,
                               record_checks, record_run)
from long_memory_integrations import (AzureEmbedder, AzureMemoryLLM, BoltAgentAdapter, memory_llm_from_settings,
                                      exported_chat_evidence, case_reflection_evidence,
                                      earlier_trajectories, setup_history)  # noqa: E402
from long_memory_runtime import ExtractionOutputError, JsonlRunLog, LongMemory  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from post_task_reflection import (append_reflection, create_reflection,
                                  reflective_evidence_loader)  # noqa: E402
from reflection_case_memory import CasePacket, ReflectionCaseMemory, RetrievedCase  # noqa: E402
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


def with_unreached_checks(evaluation: list[dict], task: dict) -> list[dict]:
    """A check with no evaluator transcript means the UI agent never reached the site (the official
    evaluation skips apps whose dev server did not come up). The official accuracy keeps those checks
    in the denominator with score 0, so record them as failed instead of dropping them."""
    present = {item.get("check") for item in evaluation}
    missing = [{"check": f"task000001_{index}", "outcome": "failed", "answer": "",
                "failure_stage": "start", "failure_type": "start_failed",
                "failure_reason": "No evaluator transcript: the site was not reachable under PM2",
                "reached_target_action": False, "logic_failure_observed": False}
               for index in range(len(task.get("ui_instruct", [])))
               if f"task000001_{index}" not in present]
    functional = [item for item in evaluation if item.get("check") != "appearance"]
    appearance = [item for item in evaluation if item.get("check") == "appearance"]
    if not appearance:
        appearance = [{"check": "appearance", "outcome": "scored", "score": None,
                       "failure_stage": "start", "failure_type": "start_failed"}]
    return sorted(functional + missing, key=lambda item: int(item["check"].rsplit("_", 1)[-1])) + appearance


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
                      model: str, evaluation: list[dict], batch_number: int,
                      delivered: bool | None = None) -> str:
    chat = Path(result["chat_path"]).resolve()
    archive = Path(result["zip_path"]).resolve()
    with connect_database(database, read_only=False) as connection:
        # A rerun after the old task directory was moved aside writes to the same chat path; it is
        # still a new run, so only reuse a trajectory whose recorded archive is this exact archive.
        archive_hash = file_hash(archive)
        row = next((found for found in connection.execute(
            "SELECT trajectory_id, artifact_refs FROM trajectories WHERE agent_id=? AND task_id=? AND trace_path=?",
            ("bolt", str(task["id"]), str(chat)),
        ) if any(ref.get("sha256") == archive_hash for ref in json.loads(found[1] or "[]"))), None)
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
                         "generation_prompt": generation_prompt, "prompt_delivered": delivered,
                         "generation_prompt_path": str(prompt_path) if prompt_path.is_file() else ""}, sort_keys=True),
             str(chat), json.dumps([{"path": str(archive), "sha256": archive_hash}],
                                   sort_keys=True), encoded, utc_now()),
        )
    return trajectory_id


def insert_failed_trajectory(database: Path, task: dict, destination: Path, model: str,
                             batch_number: int, evidence: dict, evaluation: list[dict]) -> str:
    """Generation never produced a working project: keep it as provenance, status execution_error."""
    archives = [Path(a) for a in sorted(destination.glob("000001.attempt-*.failed.zip"))]
    with connect_database(database, read_only=False) as connection:
        attempt = connection.execute(
            "SELECT COALESCE(MAX(attempt_no),0)+1 FROM trajectories WHERE agent_id=? AND task_id=?",
            ("bolt", str(task["id"]))).fetchone()[0]
        trajectory_id = uuid.uuid4().hex
        prompt_path = destination / "000001.prompt.txt"
        connection.execute(
            "INSERT INTO trajectories (trajectory_id,task_id,agent_id,attempt_no,split_group,"
            "task_request,run_config,trace_path,artifact_refs,run_status,evaluation_results,finished_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'execution_error',?,?)",
            (trajectory_id, str(task["id"]), "bolt", attempt, "g3", task["instruction"],
             json.dumps({"model": model, "memory_mode": "continual", "protocol": "continual",
                         "batch": batch_number, "source_application_type": task["application_type"],
                         "output_directory": str(destination.resolve()), "generation_failed": True,
                         "generation_prompt": prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else "",
                         "attempts": evidence["attempts"]}, sort_keys=True),
             evidence["report"], json.dumps([{"path": str(a.resolve()), "sha256": file_hash(a)} for a in archives],
                                            sort_keys=True),
             json.dumps(evaluation, ensure_ascii=False, sort_keys=True), utc_now()))
    return trajectory_id


def prompt_delivered(result: dict) -> bool | None:
    """Did Bolt receive the whole prompt? Compares the prompt we typed with the first user message in the
    exported chat (what the model actually got). None when either file is missing."""
    import re
    try:
        sent = Path(result["prompt_path"]).read_text(encoding="utf-8")
        messages = json.loads(Path(result["chat_path"]).read_text(encoding="utf-8")).get("messages", [])
        first = next(m for m in messages if m.get("role") == "user")["content"]
    except (KeyError, OSError, ValueError, StopIteration):
        return None
    received = " ".join(str(part.get("text", "")) for part in first) if isinstance(first, list) else str(first)
    norm = lambda text: re.sub(r"\s+", " ", text).strip()
    return norm(sent) in norm(received)


def guidance_run_info(llm, adapter, archive: str, delivered: bool | None) -> dict:
    """Which memory lines this run's prompt carried, and how many the generated code actually implements
    (one small Memory-LLM call per line; only when delivery was verified)."""
    from guidance_selfcheck import check_requirement, project_code
    packet = adapter.last_memory
    patterns = [str(c.content.get("implementation_pattern", "")).strip() for c in getattr(packet, "cases", ())]
    lines = [text for text in [*patterns, *getattr(packet, "common", ())] if text]
    ids = [*(cid for c in getattr(packet, "cases", ())
             for cid in (c.content.get("source_case_ids") or [c.case_id])),
           *getattr(packet, "common_case_ids", ())]
    info = {"delivered": delivered, "case_ids": list(dict.fromkeys(ids)), "total": len(lines) or None, "followed": None}
    if lines and delivered:
        code = project_code(archive)
        info["followed"] = sum(check_requirement(llm, text, code)["verdict"] == "yes" for text in lines)
    return info


def statistics_outcomes(evaluation: list[dict]) -> dict:
    counts = {"passed": 0, "partial": 0, "failed": 0}
    for item in evaluation:
        if item.get("check") != "appearance" and item.get("outcome") in counts:
            counts[item["outcome"]] += 1
    return counts


def record_statistics(database: Path, llm, task: dict, trajectory_id: str, archive: str, evaluation: list[dict],
                      causes: list[str], destination: Path, *, generation_ok: bool,
                      cases: list[dict] | None = None, guidance: dict | None = None) -> None:
    """Append this run's facts to the statistics table (Long Memory arm only)."""
    report = destination / "000001.generation.json"
    attempts = (len(json.loads(report.read_text(encoding="utf-8")).get("attempts", []))
                if report.is_file() else None)
    phase = None
    if not generation_ok and attempts:
        phase = json.loads(report.read_text(encoding="utf-8"))["attempts"][-1].get("phase")
    with connect_database(database, read_only=True) as connection:
        existing = known_labels(connection, "bolt")
    stack = detect_stack(archive) if archive else "unknown"
    lost = statistics_outcomes(evaluation)["failed"]
    outcomes: dict[str, dict[str, int]] = {}

    def add(label: str, kind: str, amount: int = 1) -> None:
        outcomes.setdefault(label, {})
        outcomes[label][kind] = outcomes[label].get(kind, 0) + amount

    if generation_ok:
        labels = label_causes(llm, causes, existing)
        for label, item in zip(labels, cases or []):
            add(label, "failed" if item.get("outcome") == "failure" else "partial")
        implementation = [c for c in (cases or []) if str(c.get("feature_object", "")).startswith("[implementation]")]
        if implementation:
            labels = [*labels, setup_label(stack)]
            for item in implementation:
                add(setup_label(stack), "failed" if item.get("outcome") == "failure" else "partial")
    else:
        # A generation that never built loses every check.
        labels = [BUILD_FAILURE_LABEL, setup_label(stack)]
        add(BUILD_FAILURE_LABEL, "failed", lost)
        add(setup_label(stack), "failed", lost)
    record_run(database, agent_id="bolt", task_id=str(task["id"]), trajectory_id=trajectory_id,
               stack=stack, generation_ok=generation_ok,
               generation_attempts=attempts, failure_phase=phase,
               outcomes=statistics_outcomes(evaluation), causes=labels, cause_outcomes=outcomes,
               prompt_delivered=(guidance or {}).get("delivered"),
               guidance_case_ids=(guidance or {}).get("case_ids", ()),
               guidance_total=(guidance or {}).get("total"), guidance_followed=(guidance or {}).get("followed"),
               prompt_stats=run_prompt_stats(task, destination))
    if not generation_ok:
        return  # a project that never built says nothing about individual features; run_facts holds it
    checks = []
    for item in evaluation:
        name = str(item.get("check", ""))
        if name == "appearance" or item.get("outcome") not in ("passed", "partial", "failed"):
            continue
        index = int(name.rsplit("_", 1)[-1])
        instructions = task.get("ui_instruct", [])
        checks.append({"index": index, "outcome": item["outcome"],
                       "task": str(instructions[index].get("task", "")) if index < len(instructions) else name})
    with connect_database(database, read_only=True) as connection:
        categories = known_categories(connection, "bolt")
    record_checks(database, agent_id="bolt", task_id=str(task["id"]), trajectory_id=trajectory_id,
                  stack=detect_stack(archive) if archive else "unknown",
                  rows=build_check_rows(llm, categories, checks, cases or []))


def run_prompt_stats(task: dict, destination: Path) -> dict:
    """Requirement vs injected-memory size for this run, plus the condense step's own numbers when it ran
    (taken from this task's latest case_retrieval event; destination is <output>/tasks/<id>/<mode>)."""
    prompt = destination / "000001.prompt.txt"
    if not prompt.is_file():
        return {}
    events = destination.parents[2] / "memory-events.jsonl"
    condense = None
    if events.is_file():
        for line in events.read_text(encoding="utf-8").splitlines():
            if '"case_retrieval"' in line:
                event = json.loads(line)
                if event.get("operation") == "case_retrieval" and event.get("task") == task["instruction"]:
                    condense = event.get("guidance_condense")
    return prompt_stats(prompt.read_text(encoding="utf-8"), task["instruction"], condense)


def summary(events: list[dict]) -> dict:
    counts = {"passed": 0, "partial": 0, "failed": 0}
    for event in events:
        for item in event.get("evaluation", []):
            if item.get("outcome") in counts:
                counts[item["outcome"]] += 1
    return {"checks": counts, "total": sum(counts.values())}


class FixedGuidanceMemory:
    """Injects an already reviewed guidance packet; no retrieval or adaptation."""

    def __init__(self, packet: CasePacket):
        self.packet = packet

    def run(self, task: str, adapter: BoltAgentAdapter, *, task_domain: str | None = None) -> dict:
        del task_domain
        return adapter.run(task, self.packet)


def run_with_retries(memory: LongMemory, instruction: str, adapter: BoltAgentAdapter,
                     *, label: str, task_domain: str | None = None, tolerate_failure: bool = False) -> dict:
    for attempt in range(3):
        try:
            return memory.run(instruction, adapter, task_domain=task_domain)
        except (TimeoutError, RuntimeError, WebDriverException, FileNotFoundError) as error:
            validation_failed = "Generated website failed validation" in str(error)
            if tolerate_failure and validation_failed:
                # Every repair round is already spent inside one generation; regenerating from scratch at
                # temperature 0 reproduces the same project and overwrites the attempt record (2026-10-02).
                log_line(f"[continual] {label}: generation failed validation; recorded as a failed run")
                return {"generation_failed": True, "error": str(error)}
            retryable = isinstance(error, (TimeoutError, WebDriverException, FileNotFoundError)) or validation_failed
            if not retryable or attempt == 2:
                if tolerate_failure and "Generated website failed validation" in str(error):
                    log_line(f"[continual] {label}: generation failed validation; recorded as a failed run")
                    return {"generation_failed": True, "error": str(error)}
                if tolerate_failure and retryable:
                    # Browser/Bolt crashes are infrastructure faults, not model outcomes: do not
                    # score or reflect on them; leave the task unrecorded so a resumed run retries it.
                    log_line(f"[continual] {label}: infrastructure failure after 3 tries; skipped, "
                             f"not recorded: {type(error).__name__}: {str(error)[-300:]}")
                    return {"infrastructure_failure": True, "error": str(error)}
                raise
            log_line(f"[continual] retrying {label} after generation/browser failure "
                     f"({attempt + 1}/3)")
            time.sleep(5)
    raise AssertionError("unreachable")


def exhausted_generation_failure(destination: Path) -> dict | None:
    """Return a prior terminal build failure so a resumed run does not pay to regenerate it."""
    report = destination / "000001.generation.json"
    if not report.is_file():
        return None
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        attempts = payload.get("attempts", [])
        maximum = int(payload.get("max_repair_attempts", 0)) + 1
    except (OSError, ValueError, TypeError):
        return None
    if len(attempts) < maximum or not attempts or any(item.get("ok") for item in attempts):
        return None
    return {"generation_failed": True, "error": str(attempts[-1].get("error", ""))}


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
    parser.add_argument("--guidance-file", type=Path,
                        help="stage2.json from memory_stage2_guidance.py; its reviewed guidance is injected "
                             "as-is and retrieval/adaptation are skipped (single-task runs)")
    parser.add_argument("--guidance-selfcheck", action="store_true",
                        help="Long Memory diagnostic: after a build passes, check it against the prompt's guidance "
                             "lines and request one extra repair round for missing ones (default off)")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--memory-config", type=Path,
                        default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    guidance: dict | None = None
    if args.guidance_file:
        guidance = json.loads(args.guidance_file.resolve().read_text(encoding="utf-8"))
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
    # Generator routing lives inside the selected Bolt service.  Memory/reflection LLM and embedding
    # default to Azure; WEBGEN_MEMORY_* / WEBGEN_EMBEDDING_* point them at self-hosted servers
    # (cluster profile), where the embedding model is served separately from the memory LLM.
    memory_base_url = args.memory_base_url or os.environ.get("WEBGEN_MEMORY_BASE_URL")
    if not memory_base_url:
        memory_base_url = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1"
    memory_api_key = os.environ.get("WEBGEN_MEMORY_API_KEY") or os.environ["AZURE_OPENAI_API_KEY"]
    generator_model = args.generator_model or os.environ["WEBGEN_GENERATOR_API_MODEL"]
    client = OpenAI(api_key=memory_api_key, base_url=memory_base_url,
                    timeout=600, max_retries=2)
    embedding_base_url = os.environ.get("WEBGEN_EMBEDDING_BASE_URL")
    embedding_client = client if not embedding_base_url else OpenAI(
        api_key=os.environ.get("WEBGEN_EMBEDDING_API_KEY") or memory_api_key,
        base_url=embedding_base_url, timeout=120, max_retries=2)
    llm = AzureMemoryLLM(client, settings.memory_llm["deployment"],
        max_tokens=settings.memory_llm["max_completion_tokens"],
        rate_limit_retries=settings.memory_llm["rate_limit_retries"],
        rate_limit_base_seconds=settings.memory_llm["rate_limit_base_seconds"],
        rate_limit_max_wait_seconds=settings.memory_llm["rate_limit_max_wait_seconds"],
        rate_limit_long_retry_seconds=settings.memory_llm["rate_limit_long_retry_seconds"],
        rate_limit_long_retries=settings.memory_llm["rate_limit_long_retries"])
    reflection_llm = memory_llm_from_settings(client, settings.reflection_llm)
    embedder = AzureEmbedder(embedding_client, settings.embedding["deployment"],
                             dimensions=settings.embedding["dimensions"])
    max_repair_attempts = int(os.environ.get("WEBGEN_MAX_REPAIR_ATTEMPTS", "1"))
    official = os.environ.get("WEBGEN_OFFICIAL_PROTOCOL") == "1"
    if official:
        max_repair_attempts = 0  # the WebGen-Bench protocol generates once and evaluates it as is
    metadata = {"protocol": "continual-domain-block-v1", "manifest": str(args.manifest.resolve()),
                "manifest_sha256": file_hash(args.manifest.resolve()), "memory_config_sha256": file_hash(args.memory_config.resolve()),
                "generator_model": generator_model, "memory_model": settings.memory_llm["deployment"],
                "embedding_model": settings.embedding["deployment"],
                "functional_evaluator_model": os.environ.get(
                    "WEBGEN_FUNCTIONAL_EVALUATOR_MODEL",
                    os.environ.get("WEBGEN_EVALUATOR_MODEL", os.environ.get("WEBVOYAGER_API_MODEL", "")),
                ),
                "appearance_evaluator_model": os.environ.get(
                    "WEBGEN_APPEARANCE_EVALUATOR_MODEL",
                    os.environ.get("WEBGEN_EVALUATOR_MODEL", os.environ.get("WEBVOYAGER_API_MODEL", "")),
                ),
                "post_task_reflection": args.post_task_reflection,
                "memory_representation": args.memory_representation,
                "modes": list(args.modes),
                "official_protocol": official, "max_repair_attempts": max_repair_attempts,
                "guidance_selfcheck": args.guidance_selfcheck,
                "guidance_file_sha256": file_hash(args.guidance_file.resolve()) if args.guidance_file else None}
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
                                       headless=not args.headed, max_repair_attempts=max_repair_attempts,
                                       base_constraints=settings.memory.base_constraints_in_prompt)
            if mode == "continual" and settings.memory.statistics_memory:
                adapter.repair_hint = repair_hint_factory(str(database), "bolt", embedder, task_id)
            if mode == "continual" and args.guidance_selfcheck:
                def selfcheck_lines(adapter=adapter) -> list[str]:
                    packet = adapter.last_memory
                    patterns = [str(c.content.get("implementation_pattern", "")) for c in getattr(packet, "cases", ())]
                    return [*patterns, *getattr(packet, "common", ())]
                adapter.compliance_check = (
                    lambda archive, adapter=adapter, lines=selfcheck_lines:
                    make_compliance_check(llm, lines(), memory_log)(archive))
            prior_failure = exhausted_generation_failure(destination)
            if prior_failure is not None:
                log_line(f"[resume] {task_id}:{mode}: recording prior terminal generation failure")
                result = prior_failure
            elif mode == "disabled":
                with LongMemory(database, "bolt", memory_mode="disabled") as memory:
                    result = run_with_retries(memory, task["instruction"], adapter,
                                              label=f"{task_id}:{mode}", tolerate_failure=True)
            elif guidance is not None:
                if guidance["task_id"] != task_id or guidance["task"] != task["instruction"]:
                    raise ValueError(f"--guidance-file was built for task {guidance['task_id']}, not {task_id}")
                packet = CasePacket(tuple(RetrievedCase(item["case_id"], {
                    "case_type": item["case_type"], "implementation_pattern": item["implementation_pattern"]}, 0.0)
                    for item in guidance["guidance"]),
                    common=tuple(guidance.get("common", [])),
                    common_case_ids=tuple(dict.fromkeys(
                        cid for item in guidance.get("common_adaptation", {}).get("patterns", [])
                        for cid in item.get("source_case_ids", []))),
                    statistics=guidance.get("statistics", ""))
                result = run_with_retries(FixedGuidanceMemory(packet), task["instruction"], adapter,
                                          label=f"{task_id}:{mode}", tolerate_failure=True)
            elif args.memory_representation == "case_only":
                with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                                          config=settings.memory, log=memory_log) as memory:
                    instruction = task["instruction"] + ("\n\n" + manual_memory if manual_memory else "")
                    if manual_memory:
                        task_aspects = memory._aspects(task["instruction"])
                        adapted = llm.generate("manual_case_implementation_adaptation", {
                            "instructions": "For each historical case, compare it against the supplied task aspects. Reject any concrete field or action absent from the matched aspect (for example, do not add DOB when no aspect requires DOB), but preserve transferable abstract principles such as clear validation feedback. Return JSON {patterns:[{applicable,matched_aspect_index,matched_feature,implementation_pattern,verification,reason}]}.",
                            "current_task": task["instruction"], "task_aspects": task_aspects,
                            "historical_cases": manual_memory,
                            "adaptation_policy": "Output implementation constraints only. Translate any historical GUI trigger or verification into code/design requirements; never output click/select/open/navigate/observe instructions."})
                        patterns = adapted.get("patterns", []) if isinstance(adapted, dict) else []
                        forbidden = ("click", "select", "open the", "navigate to", "observe", "verify by", "user clicks")
                        usable = [str(item.get("implementation_pattern", "")).strip()
                                  for item in patterns if isinstance(item, dict) and item.get("applicable")
                                  and str(item.get("implementation_pattern", "")).strip()
                                  and not any(term in str(item.get("implementation_pattern", "")).lower() for term in forbidden)]
                        memory_log({
                            "operation": "manual_case_adaptation",
                            "task_id": str(task["id"]),
                            "source_file": str(args.manual_memory_file.resolve()),
                            "source_sha256": hashlib.sha256(manual_memory.encode("utf-8")).hexdigest(),
                            "task_aspects": task_aspects,
                            "raw_patterns": patterns,
                            "accepted_patterns": usable,
                            "retrieval_mode": "manual",
                        })
                        if usable:
                            instruction = task["instruction"] + "\n\nCURRENT-TASK IMPLEMENTATION PATTERNS:\n- " + "\n- ".join(usable)
                    memory.statistics_task_id = task_id
                    memory.record_code_uses = bool(settings.memory.memory_write)
                    result = run_with_retries(memory, instruction, adapter,
                                              label=f"{task_id}:{mode}",
                                              task_domain=task["application_type"], tolerate_failure=True)
            else:
                with LongMemory(database, "bolt", memory_mode="learn", llm=llm,
                                embedder=embedder, config=settings.memory, log=memory_log) as memory:
                    result = run_with_retries(memory, task["instruction"], adapter,
                                              label=f"{task_id}:{mode}",
                                              task_domain=task["application_type"], tolerate_failure=True)
            if isinstance(result, dict) and result.get("infrastructure_failure"):
                continue
            # This is the first point at which hidden benchmark evaluation is accessed.
            # The generated archive has already been written and is never regenerated here.
            generation_failed = isinstance(result, dict) and bool(result.get("generation_failed"))
            if generation_failed:
                evaluation = failed_evaluation(task)
            else:
                with exclusive_evaluation_lock():
                    run_evaluators(destination, task_file, 1)
                try:
                    evaluation = evaluations(destination, 1)
                except RuntimeError:  # no transcript and no screenshot: the site never came up under PM2
                    evaluation = []
                evaluation = with_unreached_checks(evaluation, task)
            event = {"key": key, "status": "complete", "batch": batch_number,
                     "task_id": task_id, "mode": mode, "evaluation": evaluation}
            if generation_failed:
                event.update({"generation_failed": True, "error": result.get("error", "")[-500:]})
            if not generation_failed:
                event["prompt_delivered"] = prompt_delivered(result)
                if event["prompt_delivered"] is False:
                    log_line(f"[continual] WARNING {task_id}:{mode}: Bolt did not receive the whole prompt")
            if mode == "continual" and not settings.memory.memory_write:
                # Prompt-only ablation (e.g. checklist without memory): the prompt pipeline ran, but nothing from
                # this run is stored, so every later task starts from the same empty memory.
                append_event(progress_path, event)
                completed.add(key)
                reports.append(event)
                log_line(f"[continual] completed {ordinal}/{len(tasks)} batch {batch_number} "
                         f"{task_id} {mode} (memory_write off: nothing stored)")
                continue
            if mode == "continual" and generation_failed:
                # The project never built: keep it as provenance, count every check as failed, and learn from it.
                evidence = failed_generation_evidence(destination)
                trajectory_id = insert_failed_trajectory(database, task, destination, generator_model,
                                                         batch_number, evidence, evaluation)
                stack = detect_stack(evidence["archive"]) if evidence["archive"] else "unknown"
                lesson = failure_reflection(reflection_llm, task["instruction"], trajectory_id, stack, evidence)
                case_ids: list[str] = []
                if lesson:
                    append_reflection(reflection_path, lesson)
                    with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                                              config=settings.memory, log=memory_log) as memory:
                        case_ids = memory.store(lesson)
                record_statistics(database, llm, task, trajectory_id, evidence["archive"], evaluation,
                                  [lesson["implementation_reflection"]["likely_cause_or_limitation"]] if lesson else [],
                                  destination, generation_ok=False)
                if settings.memory.code_pool:  # failed task: its injected code memories count as not preventing it
                    with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                                              config=settings.memory, log=memory_log) as memory:
                        event["code_pool"] = memory.update_code_pool(task_id)
                event.update({"trajectory_id": trajectory_id, "generation_failed": True, "stack": stack,
                              "case_ids": case_ids, "error": result.get("error", "")[-500:]})
                append_event(progress_path, event)
                completed.add(key)
                reports.append(event)
                log_line(f"[continual] completed {ordinal}/{len(tasks)} batch {batch_number} "
                         f"{task_id} {mode} (generation failed; {len(case_ids)} case(s) stored)")
                continue
            if mode == "continual":
                trajectory_id = upsert_trajectory(database, task, result, destination,
                                                  generator_model, evaluation, batch_number,
                                                  delivered=event.get("prompt_delivered"))
                evidence_loader = exported_chat_evidence
                if args.post_task_reflection or args.memory_representation == "case_only":
                    with connect_database(database, read_only=True) as connection:
                        source = connection.execute(
                            "SELECT * FROM trajectories WHERE trajectory_id=?", (trajectory_id,)
                        ).fetchone()
                    reflection = create_reflection(reflection_llm, dict(source),
                                                 (case_reflection_evidence if args.memory_representation == "case_only"
                                                  else exported_chat_evidence)(dict(source)),
                                                 review=settings.memory.post_task_case_review,
                                                 style=settings.memory.reflection_style,
                                                 appearance_mode=settings.memory.appearance_reflection,
                                                 setup_history=(setup_history(earlier_trajectories(connection, dict(source)))
                                                                if args.memory_representation == "case_only" else None))
                    append_reflection(reflection_path, reflection)
                    event["reflection_id"] = reflection["reflection_id"]
                    if reflection.get("appearance_all_dropped"):
                        event["appearance_all_dropped"] = True
                        log_line(f"[continual] WARNING {task_id}: every appearance case lacked a verified code "
                                 "citation and was not stored (see appearance_dropped_no_citation in the reflection)")
                    # ``reflection_count`` used to look like an inner retry count.
                    # Keep it only as a backwards-compatible alias for accepted
                    # strict-provenance items; raw archived cases are reported too.
                    event["accepted_reflection_count"] = reflection["accepted_reflection_count"]
                    event["raw_reflection_count"] = reflection["raw_reflection_count"]
                    event["reflection_count"] = reflection["accepted_reflection_count"]
                    if getattr(reflection_llm, "context_trims", None):
                        event["reflection_context_trims"] = reflection_llm.context_trims
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
                    causes = [str(item.get("likely_cause_or_limitation", ""))
                              for item in [*reflection.get("functional_reflections", []),
                                           reflection.get("implementation_reflection")]
                              if isinstance(item, dict) and item.get("outcome") != "success"]
                    record_statistics(database, llm, task, trajectory_id, result["zip_path"], evaluation,
                                      causes, destination, generation_ok=True,
                                      guidance=guidance_run_info(llm, adapter, result["zip_path"],
                                                                 event.get("prompt_delivered")),
                                      cases=[item for item in [*reflection.get("functional_reflections", []),
                                                               reflection.get("implementation_reflection")]
                                             if isinstance(item, dict) and item.get("outcome") != "success"])
                    if settings.memory.code_pool:
                        with ReflectionCaseMemory(str(database), "bolt", llm=llm, embedder=embedder,
                                                  config=settings.memory, log=memory_log) as memory:
                            event["code_pool"] = memory.update_code_pool(task_id)
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
