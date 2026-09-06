"""Small concrete integrations used by the Bolt long-memory experiment."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from long_memory_runtime import MemoryPacket


class AzureMemoryLLM:
    """Structured MemoryLLM over an OpenAI-compatible Azure deployment."""

    def __init__(self, client: Any, model_id: str, *, max_tokens: int = 4096):
        if not model_id.strip():
            raise ValueError("Memory LLM deployment name is required")
        self.client = client
        self.model_id = model_id
        self.max_tokens = max_tokens

    def generate(self, operation: str, payload: Mapping[str, Any]) -> dict:
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": str(payload["instructions"]) +
                 " Return one valid JSON object and no surrounding prose."},
                {"role": "user", "content": json.dumps(
                    {"operation": operation, **{key: value for key, value in payload.items()
                     if key != "instructions"}}, ensure_ascii=False, default=str)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_completion_tokens=self.max_tokens,
        )
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
    if not memory.experiences and not memory.skills:
        return task
    return (
        task
        + "\n\nUse the following retrieved long-term memory only where it applies. "
          "It contains historical guidance, not new task requirements.\n\n"
        + memory.render()
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
    last_memory: MemoryPacket | None = field(default=None, init=False)

    def run(self, task: str, memory: MemoryPacket) -> Any:
        self.last_memory = memory
        return self.generate(
            idx=self.index,
            instruction=bolt_memory_prompt(task, memory),
            download_dir=str(self.output_dir),
            url=self.url,
            desired_model=self.model,
            provider=self.provider,
            headless=self.headless,
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
    if not evidence:
        raise ValueError(f"No usable chat messages in {path}")
    return evidence
