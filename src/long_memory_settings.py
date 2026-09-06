"""Load the single versioned configuration for long-memory experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from long_memory_runtime import MemoryConfig


@dataclass(frozen=True)
class LongMemorySettings:
    memory: MemoryConfig
    memory_llm: dict[str, Any]
    embedding: dict[str, Any]


def load_long_memory_settings(path: Path) -> LongMemorySettings:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or set(raw) != {
        "schema_version", "memory_llm", "embedding", "runtime"
    }:
        raise ValueError("Unsupported long-memory configuration schema")
    llm = raw["memory_llm"]
    embedding = raw["embedding"]
    required_llm = {"deployment", "max_completion_tokens", "rate_limit_retries",
                    "rate_limit_base_seconds", "rate_limit_max_wait_seconds",
                    "rate_limit_long_retry_seconds", "rate_limit_long_retries"}
    if set(llm) != required_llm or not str(llm["deployment"]).strip():
        raise ValueError("Invalid memory_llm configuration")
    if set(embedding) != {"deployment", "dimensions"} or not str(
        embedding["deployment"]
    ).strip():
        raise ValueError("Invalid embedding configuration")
    return LongMemorySettings(MemoryConfig(**raw["runtime"]), dict(llm), dict(embedding))
