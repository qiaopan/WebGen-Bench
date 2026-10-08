"""Validation and deterministic scheduling for the long-memory experiment."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_MODES = {
    "disabled": {"read": False, "write": False},
    "learn": {"read": True, "write": True},
    "read_only": {"read": True, "write": False},
}
EVALUATION_GROUPS = {"g2", "g4", "g5"}
MEMORY_GROUPS = {"g1", "g3"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def validate_protocol(project_root: Path, config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if config.get("codebase", {}).get("strategy") != "single_branch":
        raise ValueError("The experiment must use one codebase and one Git commit")

    mode_config = config.get("memory_modes", {})
    if set(mode_config) != set(EXPECTED_MODES):
        raise ValueError(f"Expected exactly these memory modes: {sorted(EXPECTED_MODES)}")
    for name, expected in EXPECTED_MODES.items():
        actual = {key: mode_config[name].get(key) for key in ("read", "write")}
        if actual != expected:
            raise ValueError(f"Invalid permissions for memory mode {name}: {actual}")

    group_records: dict[str, list[dict[str, Any]]] = {}
    all_ids: list[str] = []
    for group_name, group in config["groups"].items():
        path = project_root / group["file"]
        if not path.is_file():
            raise FileNotFoundError(path)
        records = load_jsonl(path)
        ids = [str(record["id"]) for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate IDs inside {group_name}")
        group_records[group_name] = records
        all_ids.extend(ids)

        allowed = set(group["allowed_modes"])
        expected_allowed = {"learn"} if group_name in MEMORY_GROUPS else {"disabled", "read_only"}
        if allowed != expected_allowed:
            raise ValueError(f"Unsafe allowed_modes for {group_name}: {sorted(allowed)}")

    if len(all_ids) != 101 or len(set(all_ids)) != 101:
        raise ValueError("The five groups must be disjoint and cover exactly 101 websites")

    manifest_path = project_root / config["dataset_manifest"]
    manifest = load_json(manifest_path)
    manifest_ids = {
        str(record_id)
        for group in manifest["groups"].values()
        for record_id in group["ids"]
    }
    if set(all_ids) != manifest_ids:
        raise ValueError("Protocol group files do not match the frozen split manifest")

    seen_stage_groups = set()
    for stage_name, phases in config["stages"].items():
        for phase in phases:
            group_name = phase["group"]
            modes = set(phase["modes"])
            allowed = set(config["groups"][group_name]["allowed_modes"])
            if not modes <= allowed:
                raise ValueError(f"{stage_name}/{group_name} requests a forbidden memory mode")
            if group_name in EVALUATION_GROUPS and "learn" in modes:
                raise ValueError(f"Evaluation group {group_name} must never write memory")
            if phase.get("paired") and modes != {"disabled", "read_only"}:
                raise ValueError(f"Paired phase {stage_name}/{group_name} must compare both conditions")
            seen_stage_groups.add(group_name)
    if seen_stage_groups != set(config["groups"]):
        raise ValueError("Every group must be assigned to at least one stage")

    return group_records


def _event(
    sequence: int,
    stage: str,
    phase: str,
    group_name: str,
    group_file: str,
    record: dict[str, Any],
    position: int,
    mode: str,
    mode_config: dict[str, Any],
    pair_id: str | None = None,
) -> dict[str, Any]:
    event = {
        "sequence": sequence,
        "stage": stage,
        "phase": phase,
        "group": group_name,
        "group_file": group_file,
        "record_position": position,
        "record_id": str(record["id"]),
        "application_type": record["application_type"],
        "memory_mode": mode,
        "memory_read": bool(mode_config[mode]["read"]),
        "memory_write": bool(mode_config[mode]["write"]),
        "output_directory": f"outputs/experiment/{stage}/{phase}/{group_name}/{mode}",
    }
    if pair_id is not None:
        event["pair_id"] = pair_id
    return event


def build_plan(project_root: Path, config_path: Path, selected_stage: str = "all") -> dict[str, Any]:
    config = load_json(config_path)
    group_records = validate_protocol(project_root, config)
    stages = list(config["stages"])
    if selected_stage != "all":
        if selected_stage not in config["stages"]:
            raise ValueError(f"Unknown stage: {selected_stage}")
        stages = [selected_stage]

    events: list[dict[str, Any]] = []
    sequence = 1
    for stage_name in stages:
        for phase in config["stages"][stage_name]:
            group_name = phase["group"]
            group_file = config["groups"][group_name]["file"]
            for position, record in enumerate(group_records[group_name], start=1):
                if phase.get("paired"):
                    order_key = "odd_record_position" if position % 2 else "even_record_position"
                    mode_order = config["paired_order"][order_key]
                    pair_id = f"{stage_name}-{group_name}-{record['id']}"
                else:
                    mode_order = phase["modes"]
                    pair_id = None
                for mode in mode_order:
                    events.append(
                        _event(
                            sequence,
                            stage_name,
                            phase["phase"],
                            group_name,
                            group_file,
                            record,
                            position,
                            mode,
                            config["memory_modes"],
                            pair_id,
                        )
                    )
                    sequence += 1

    mode_totals = {mode: sum(event["memory_mode"] == mode for event in events) for mode in EXPECTED_MODES}
    return {
        "schema_version": 1,
        "protocol_name": config["protocol_name"],
        "selected_stage": selected_stage,
        "git_commit": git_commit(project_root),
        "config_path": str(config_path.relative_to(project_root)),
        "config_sha256": sha256(config_path),
        "dataset_manifest": config["dataset_manifest"],
        "dataset_manifest_sha256": sha256(project_root / config["dataset_manifest"]),
        "event_count": len(events),
        "mode_event_counts": mode_totals,
        "events": events,
    }
