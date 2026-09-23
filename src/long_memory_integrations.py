"""Small concrete integrations used by the Bolt long-memory experiment."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from long_memory_runtime import MemoryPacket


class AzureMemoryLLM:
    """Structured MemoryLLM over an OpenAI-compatible Azure deployment."""

    def __init__(self, client: Any, model_id: str, *, max_tokens: int = 4096,
                 rate_limit_retries: int | None = None,
                 rate_limit_base_seconds: float | None = None,
                 rate_limit_max_wait_seconds: float | None = None,
                 rate_limit_long_retry_seconds: float | None = None,
                 rate_limit_long_retries: int | None = None):
        if not model_id.strip():
            raise ValueError("Memory LLM deployment name is required")
        self.client = client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.rate_limit_retries = 6 if rate_limit_retries is None else rate_limit_retries
        self.rate_limit_base_seconds = (10 if rate_limit_base_seconds is None
                                        else rate_limit_base_seconds)
        self.rate_limit_max_wait_seconds = (300 if rate_limit_max_wait_seconds is None
                                            else rate_limit_max_wait_seconds)
        self.rate_limit_long_retry_seconds = (300 if rate_limit_long_retry_seconds is None
                                              else rate_limit_long_retry_seconds)
        self.rate_limit_long_retries = (0 if rate_limit_long_retries is None
                                        else rate_limit_long_retries)
        if (self.rate_limit_retries < 0 or self.rate_limit_base_seconds < 0
                or self.rate_limit_max_wait_seconds < 0
                or self.rate_limit_long_retry_seconds < 0
                or self.rate_limit_long_retries < 0):
            raise ValueError("Memory LLM retry settings must be nonnegative")

    def generate(self, operation: str, payload: Mapping[str, Any]) -> dict:
        arguments = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": str(payload["instructions"]) +
                 " Return one valid JSON object and no surrounding prose."},
                {"role": "user", "content": json.dumps(
                    {"operation": operation, **{key: value for key, value in payload.items()
                     if key != "instructions"}}, ensure_ascii=False, default=str)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_completion_tokens": self.max_tokens,
        }
        last_error = None
        for attempt in range(self.rate_limit_retries + 1):
            try:
                response = self.client.chat.completions.create(**arguments)
                break
            except Exception as error:
                if getattr(error, "status_code", None) != 429 or attempt >= self.rate_limit_retries:
                    last_error = error
                    break
                retry_after = getattr(error, "response", None)
                retry_after = getattr(retry_after, "headers", {}).get("retry-after")
                try:
                    delay = max(float(retry_after), 0.0)
                except (TypeError, ValueError):
                    delay = self.rate_limit_base_seconds * (2 ** attempt)
                time.sleep(min(delay, self.rate_limit_max_wait_seconds))
        if last_error is not None:
            if getattr(last_error, "status_code", None) != 429:
                raise last_error
            for _ in range(self.rate_limit_long_retries):
                time.sleep(self.rate_limit_long_retry_seconds)
                try:
                    response = self.client.chat.completions.create(**arguments)
                    last_error = None
                    break
                except Exception as error:
                    if getattr(error, "status_code", None) != 429:
                        raise
                    last_error = error
            if last_error is not None:
                raise last_error
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Memory LLM returned empty content")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("Memory LLM response must be a JSON object")
        return result


class AzureEmbedder:
    """Embedder over a frozen OpenAI-compatible Azure deployment."""

    def __init__(self, client: Any, model_id: str, *, dimensions: int | None = None):
        if not model_id.strip():
            raise ValueError("Embedding deployment name is required")
        self.client = client
        self.model_id = model_id
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        arguments = {"model": self.model_id, "input": list(texts)}
        if self.dimensions is not None:
            arguments["dimensions"] = self.dimensions
        response = self.client.embeddings.create(**arguments)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


def bolt_memory_prompt(task: str, memory: MemoryPacket) -> str:
    """Format only. Stored memory content is copied without summarisation."""
    prompt = task
    rendered_memory = memory.render()
    if rendered_memory:
        prompt += (
        "\n\nHISTORICAL LONG-TERM CASES (REFERENCE ONLY):\n"
        "The current task requirement above is binding and has the highest priority. "
        "The following cases are historical evidence, not new requirements. Do not copy "
        "their old business content, text, colours, or layout; use them only when they "
        "happen to apply to the current task.\n\n"
        + rendered_memory
        )
    # Baseline reliability constraints apply to both No Memory and Long Memory;
    # memory can add task-specific lessons but must not be the sole safeguard.
    return prompt + (
        "\n\nBASE IMPLEMENTATION RELIABILITY CONSTRAINTS:\n"
        "Return a complete, buildable application. Before finishing, run the "
        "project build check and fix all syntax errors. In React/JSX, never write "
        "dynamic text as `<{value}>`; use `{value}` or escaped text such as "
        "`&lt;{value}&gt;`. Escape literal comparison text too: use `&lt;550`, "
        "not `<550`, inside a JSX text node. Ensure every JSX tag and expression is closed."
    )


@dataclass
class BoltAgentAdapter:
    generate: Callable[..., Any]
    index: int
    output_dir: Path
    url: str
    model: str
    provider: str = "OpenAILike"
    headless: bool = True
    max_repair_attempts: int = 1
    generation_guard: str = ""
    last_memory: MemoryPacket | None = field(default=None, init=False)

    def run(self, task: str, memory: MemoryPacket) -> Any:
        self.last_memory = memory
        prompt = bolt_memory_prompt(task, memory)
        if self.generation_guard:
            prompt += "\n\nFINAL IMPLEMENTATION CONSTRAINTS:\n" + self.generation_guard
        return self.generate(
            idx=self.index,
            instruction=prompt,
            download_dir=str(self.output_dir),
            url=self.url,
            desired_model=self.model,
            provider=self.provider,
            headless=self.headless,
            max_repair_attempts=self.max_repair_attempts,
        )


def exported_chat_evidence(trajectory: dict) -> list[dict]:
    """Load exact message evidence referenced by a trajectory's trace path."""
    path = Path(trajectory["trace_path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    evidence = []
    for index, message in enumerate(data.get("messages", [])):
        if message.get("role") not in ("user", "assistant"):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        evidence.append({
            "ref": {"kind": "chat_message", "message_index": index, "role": message["role"]},
            "content": content,
        })
    for index, result in enumerate(json.loads(trajectory["evaluation_results"] or "[]")):
        evidence.append({
            "ref": {"kind": "evaluation_result", "result_index": index},
            "content": result,
        })
        # The final evaluator summary alone loses the browser's observed action
        # sequence.  Preserve assistant-only GUI steps as evidence; evaluator
        # prompts (which can contain benchmark-only expected results) are never
        # copied into continual memory evidence.
        path = result.get("evidence") if isinstance(result, dict) else None
        if not isinstance(path, str) or not path.endswith("interact_messages.json"):
            continue
        try:
            messages = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        assistant_steps = [str(message.get("content", "")) for message in messages
                           if message.get("role") == "assistant" and message.get("content")]
        if assistant_steps:
            evidence.append({
                "ref": {"kind": "gui_trajectory", "result_index": index},
                "content": "\n".join(assistant_steps),
            })
    if not evidence:
        raise ValueError(f"No usable chat messages in {path}")
    return evidence
