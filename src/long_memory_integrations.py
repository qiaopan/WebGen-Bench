"""Small concrete integrations used by the Bolt long-memory experiment."""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from long_memory_runtime import MemoryPacket

# (share of the site's code kept, share of each GUI trajectory kept), step by step, when a request exceeds
# the model's context window (the cluster's 72B memory model has 32K tokens; Phase 1's GPT-4o had 128K).
# The code goes first; only then the middle of long tester trajectories (their start and end stay).
_CONTEXT_TRIM_STEPS = ((0.5, 1.0), (0.25, 1.0), (0.1, 1.0), (0.1, 0.5), (0.1, 0.25))


def _is_context_overflow(error: Exception) -> bool:
    return getattr(error, "status_code", None) == 400 and "maximum context length" in str(error)


def _trim_code(value: Any, keep: float, gui_keep: float = 1.0) -> Any:
    """Copy of a payload with the site's code cut to ``keep`` of its length (code files and the generator's
    own chat replies) and, when ``gui_keep`` < 1, the middle of each GUI trajectory cut so that share of it
    remains (its first and last steps stay). Evaluator results and the requirement stay whole."""
    if isinstance(value, list):
        return [_trim_code(item, keep, gui_keep) for item in value]
    if not isinstance(value, dict):
        return value
    ref, content = value.get("ref"), value.get("content")
    if isinstance(ref, dict) and isinstance(content, str):
        if ref.get("kind") == "code_file" or (ref.get("kind") == "chat_message" and ref.get("role") == "assistant"):
            limit = max(1500, int(len(content) * keep))
            if len(content) > limit:
                return {**value, "content": content[:limit] + "\n...[cut: did not fit in the reflection model's context]"}
            return value
        if ref.get("kind") == "gui_trajectory" and gui_keep < 1:
            half = max(1000, int(len(content) * gui_keep / 2))
            if len(content) > 2 * half:
                return {**value, "content": content[:half] + "\n...[middle steps cut: did not fit in the "
                        "reflection model's context]...\n" + content[-half:]}
            return value
    return {key: _trim_code(item, keep, gui_keep) for key, item in value.items()}


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
        self.transient_retries: list[dict] = []
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
        self.context_trims: list[dict] = []  # requests that only fit after cutting the site's code

    # Transient failures (invalid or empty JSON, dropped connection, timeout, server error) are retried before the
    # task is given up: an unretried bad reply crashed whole Long Memory tasks before generation (v4, 2026-10-07).
    transient_attempts = 3

    def generate(self, operation: str, payload: Mapping[str, Any]) -> dict:
        for attempt in range(1, self.transient_attempts + 1):
            try:
                return self._generate(operation, payload)
            except Exception as error:
                if _is_context_overflow(error):
                    overflow = error
                    break
                # Rate limiting (429) has its own policy in _generate; not retried again here.
                if attempt == self.transient_attempts or getattr(error, "status_code", None) == 429:
                    raise
                self.transient_retries.append({"operation": operation, "attempt": attempt,
                                               "error": f"{type(error).__name__}: {str(error)[:200]}"})
                print(f"[memory-llm] {operation}: attempt {attempt} failed ({type(error).__name__}); retrying",
                      file=sys.stderr, flush=True)
                time.sleep(10 * attempt)
        for keep, gui_keep in _CONTEXT_TRIM_STEPS:
            self.context_trims.append({"operation": operation, "code_kept": keep, "gui_kept": gui_keep})
            print(f"[memory-llm] {operation}: request exceeds the model's context; retrying with the "
                  f"site's code cut to {keep:.0%} and tester steps to {gui_keep:.0%}", file=sys.stderr, flush=True)
            try:
                return self._generate(operation, _trim_code(payload, keep, gui_keep))
            except Exception as error:
                if not _is_context_overflow(error):
                    raise
                overflow = error
        raise overflow

    def _generate(self, operation: str, payload: Mapping[str, Any]) -> dict:
        # ``_images``: optional PNG paths sent as image parts after the JSON text (multimodal models only).
        text = json.dumps({"operation": operation, **{key: value for key, value in payload.items()
                           if key not in ("instructions", "_images")}}, ensure_ascii=False, default=str)
        images = [path for path in payload.get("_images", []) if Path(path).is_file()]
        user_content: Any = text if not images else [{"type": "text", "text": text}] + [
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()}}
            for path in images]
        arguments = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": str(payload["instructions"]) +
                 " Return one valid JSON object and no surrounding prose."},
                {"role": "user", "content": user_content},
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


def memory_llm_from_settings(client: Any, cfg: Mapping[str, Any]) -> AzureMemoryLLM:
    return AzureMemoryLLM(
        client, cfg["deployment"], max_tokens=cfg["max_completion_tokens"],
        rate_limit_retries=cfg["rate_limit_retries"],
        rate_limit_base_seconds=cfg["rate_limit_base_seconds"],
        rate_limit_max_wait_seconds=cfg["rate_limit_max_wait_seconds"],
        rate_limit_long_retry_seconds=cfg["rate_limit_long_retry_seconds"],
        rate_limit_long_retries=cfg["rate_limit_long_retries"])


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


def bolt_memory_prompt(task: str, memory: MemoryPacket, *, base_constraints: bool = False) -> str:
    """Format only. Stored memory content is copied without summarisation."""
    prompt = task
    rendered_memory = memory.render()
    if rendered_memory:
        header = getattr(memory, "injection_header", None)
        prompt += (header + rendered_memory if header else (
        "\n\nHISTORICAL LONG-TERM CASES (REFERENCE ONLY):\n"
        "The current task requirement above is binding and has the highest priority. "
        "The following cases are historical evidence, not new requirements. Do not copy "
        "their old business content, text, colours, or layout; use them only when they "
        "happen to apply to the current task.\n\n"
        + rendered_memory))
    # Optional fixed reliability paragraph; off by default (config: base_constraints_in_prompt).
    if not base_constraints:
        return prompt
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
    repair_hint: Callable[..., str] | None = None
    compliance_check: Callable[[str], str] | None = None
    base_constraints: bool = False
    last_memory: MemoryPacket | None = field(default=None, init=False)

    def run(self, task: str, memory: MemoryPacket) -> Any:
        self.last_memory = memory
        prompt = bolt_memory_prompt(task, memory, base_constraints=self.base_constraints)
        if self.generation_guard:
            prompt += "\n\nFINAL IMPLEMENTATION CONSTRAINTS:\n" + self.generation_guard
        extra = {"repair_hint": self.repair_hint} if self.repair_hint else {}
        if self.compliance_check:
            extra["compliance_check"] = self.compliance_check
        return self.generate(
            idx=self.index,
            instruction=prompt,
            download_dir=str(self.output_dir),
            url=self.url,
            desired_model=self.model,
            provider=self.provider,
            headless=self.headless,
            max_repair_attempts=self.max_repair_attempts,
            **extra,
        )


_CODE_SKIP_DIRS = {"node_modules", "dist", ".git", "shots", "results", "downloads", "public", ".astro"}
_CODE_SUFFIXES = (".jsx", ".tsx", ".js", ".ts", ".astro", ".vue", ".svelte", ".html", ".css", ".mjs")


_GLOBAL_STYLE_FILES = ("src/style.css", "src/index.css", "src/App.css", "src/assets/main.css",
                       "src/styles.css", "src/global.css", "src/app.css")
def global_style_findings(project: Path) -> list[str]:
    """Measured facts, no judgement: for each global stylesheet, which entry files import it and every
    declaration it makes on :root, html, body or #app (the rules every page inherits)."""
    src = project / "src"
    entries = [p for p in src.glob("*") if p.is_file() and p.stem in ("main", "App", "index")
               and p.suffix in (".ts", ".tsx", ".js", ".jsx", ".vue")] if src.is_dir() else []
    entry_text = {p.relative_to(project).as_posix(): p.read_text(encoding="utf-8", errors="ignore") for p in entries}
    findings = []
    for rel in _GLOBAL_STYLE_FILES:
        path = project / rel
        if not path.is_file():
            continue
        importers = [name for name, text in entry_text.items() if Path(rel).name in text]
        selector, media, depth, rules = None, None, 0, []
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            head = re.match(r"\s*([^{}]+?)\s*\{", line)
            if head and head.group(1).strip().startswith("@media"):
                media, depth = head.group(1).strip(), 0
            elif head:
                selector = head.group(1).strip()
                depth += 1
            elif selector and re.fullmatch(r"(:root|html|body|#app)(\s*,\s*(:root|html|body|#app))*", selector) \
                    and ":" in line and line.strip().endswith(";"):
                rules.append(f"line {number} " + (f"{media} " if media else "") + f"{selector} {{ {line.strip()} }}")
            if "}" in line:
                if selector:
                    selector, depth = None, depth - 1
                elif media:
                    media = None
        if rules:
            findings.append(f"{rel} (imported by: {', '.join(importers) or 'no entry file'}): " + "; ".join(rules))
    return findings


_IMPORT_PATTERNS = (re.compile(r"""\bfrom\s+['"]([^'"]+)['"]"""), re.compile(r"""\bimport\s+['"]([^'"]+)['"]"""),
                    re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]\s*\)"""), re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)"""))
_NODE_BUILTINS = {"assert", "buffer", "child_process", "crypto", "dns", "events", "fs", "http", "https", "module",
                  "net", "os", "path", "perf_hooks", "process", "querystring", "readline", "stream", "tls", "url",
                  "util", "worker_threads", "zlib"}


def undeclared_imports(project: Path, files: list[str], declared: set[str]) -> list[dict]:
    """Packages the source imports by bare name that package.json does not declare (measured fact)."""
    found: dict[str, list[str]] = {}
    for rel in files:
        if rel.endswith((".css", ".html")):
            continue
        try:
            text = (project / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in _IMPORT_PATTERNS:
            for spec in pattern.findall(text):
                if spec.startswith((".", "/", "@/", "~", "#")) or ":" in spec:
                    continue
                parts = spec.split("/")
                name = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
                if name and name not in declared and name not in _NODE_BUILTINS:
                    found.setdefault(name, [])
                    if rel not in found[name]:
                        found[name].append(rel)
    return [{"package": name, "imported_in": paths[:3]} for name, paths in sorted(found.items())]


def generator_written_files(trajectory: dict) -> list[str] | None:
    """Files written by the generator's own reply in the exported chat; a template import that Bolt
    performs before the request is answered is not counted. None when the chat cannot be read."""
    try:
        data = json.loads(Path(trajectory["trace_path"]).read_text(encoding="utf-8"))
    except (KeyError, TypeError, OSError, ValueError):
        return None
    messages = data.get("messages", []) if isinstance(data, dict) else data
    start = 0
    for index, message in enumerate(messages):
        if message.get("role") == "user" and "Template is imported" in str(message.get("content", "")):
            start = index + 1
    written: list[str] = []
    for message in messages[start:]:
        if message.get("role") == "assistant" and isinstance(message.get("content"), str):
            for path in re.findall(r'<boltAction type="file" filePath="([^"]+)"', message["content"]):
                if path not in written:
                    written.append(path)
    return written


def generated_code_evidence(trajectory: dict, *, per_file: int = 16000, budget: int = 60000,
                            project: Path | None = None) -> list[dict]:
    """Compact view of the generated website's own source, for root-cause analysis.

    Only our generated project is read (never evaluator prompts). Returns [] when the
    project directory cannot be located, so callers that lack code still work.
    """
    if project is None:
        try:
            project = Path(trajectory["trace_path"]).parent / "extracted" / "000001"
        except (KeyError, TypeError):
            return []
    if not project.is_dir():
        return []
    manifest: dict[str, Any] = {}
    package = project / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            manifest = {"dependencies": data.get("dependencies", {}),
                        "devDependencies": data.get("devDependencies", {}),
                        "scripts": data.get("scripts", {})}
        except (OSError, ValueError):
            pass
    files = []
    for path in sorted(project.rglob("*")):
        rel = path.relative_to(project)
        if (not path.is_file() or any(part in _CODE_SKIP_DIRS for part in rel.parts)
                or path.suffix not in _CODE_SUFFIXES or path.name.endswith(".d.ts")):
            continue
        files.append(rel.as_posix())
    declared = set(manifest.get("dependencies", {})) | set(manifest.get("devDependencies", {}))
    facts: dict[str, Any] = {"imports_not_in_package_json": undeclared_imports(project, files, declared)}
    written = generator_written_files(trajectory)
    if written is not None:
        facts["generator_written_files"] = written
    evidence = [{"ref": {"kind": "code_manifest"},
                 "content": {**manifest, "files": files, "global_style_rules": global_style_findings(project),
                             **facts}}]
    used = 0
    for rel in sorted(files, key=lambda f: (0 if "/pages/" in f or "/components/" in f else 1, f)):
        try:
            text = (project / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = text[:per_file]
        if used + len(text) > budget:
            break
        used += len(text)
        evidence.append({"ref": {"kind": "code_file", "path": rel}, "content": text})
    return evidence


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


def setup_label(manifest: Mapping[str, Any]) -> str:
    names = set(manifest.get("dependencies", {})) | set(manifest.get("devDependencies", {}))
    if "astro" in names:
        return "Astro (static-site framework)"
    if "next" in names:
        return "Next.js"
    if "vue" in names:
        return "Vite + Vue"
    if "react" in names:
        return "Vite + React"
    return "Vite (plain JavaScript)"


def setup_history(trajectories: list[dict]) -> dict:
    """Automatic statistics: how each build setup fared on functional checks in earlier runs."""
    history: dict[str, dict[str, int]] = {}
    for trajectory in trajectories:
        code = generated_code_evidence(trajectory)
        if not code:
            continue
        label = setup_label(code[0]["content"])
        try:
            checks = [c for c in json.loads(trajectory["evaluation_results"] or "[]")
                      if isinstance(c, dict) and c.get("check") != "appearance"]
        except (TypeError, ValueError):
            continue
        entry = history.setdefault(label, {"runs": 0, "checks": 0, "passed": 0, "partial": 0, "failed": 0})
        entry["runs"] += 1
        entry["checks"] += len(checks)
        for check in checks:
            outcome = check.get("outcome")
            if outcome in ("passed", "partial", "failed"):
                entry[outcome] += 1
    return history


def earlier_trajectories(connection: Any, trajectory: dict) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM trajectories WHERE agent_id=? AND started_at < ? ORDER BY started_at",
        (trajectory["agent_id"], trajectory["started_at"]))
    return [dict(row) for row in rows]


def guidance_received_evidence(trajectory: dict) -> list[dict]:
    """The memory lines this website's generator was actually given (only when delivery was verified).
    It is our own prompt, never evaluator material."""
    try:
        config = json.loads(trajectory.get("run_config") or "{}")
    except (TypeError, ValueError):
        return []
    if config.get("prompt_delivered") is not True:
        return []
    prompt = str(config.get("generation_prompt", ""))
    lines: dict[str, list[str]] = {"guidance": [], "common": []}
    section = None
    for line in prompt.splitlines():
        if line.startswith("IMPLEMENTATION GUIDANCE FROM PAST TASKS"):
            section = "guidance"
        elif line.startswith("COMMON IMPLEMENTATION PITFALLS"):
            section = "common"
        elif line.startswith("RECORDED OUTCOMES") or line.startswith("BASE IMPLEMENTATION"):
            section = None
        elif section and line.startswith("- "):
            lines[section].append(line[2:].strip())
    if not (lines["guidance"] or lines["common"]):
        return []
    return [{"ref": {"kind": "guidance_received"}, "content": lines}]


def evaluator_log_evidence(trajectory: dict, *, limit: int = 1500) -> list[dict]:
    """Error lines from each evaluator run's own log (agent.log next to interact_messages.json).

    Only ERROR lines are kept (for example a browser dialog opened by the page that stopped the
    tester); the log's prompts and thoughts are never copied. Deduplicated and capped.
    """
    evidence = []
    try:
        results = json.loads(trajectory.get("evaluation_results") or "[]")
    except (TypeError, ValueError):
        return []
    for index, result in enumerate(results):
        path = result.get("evidence") if isinstance(result, dict) else None
        if not isinstance(path, str) or not path.endswith("interact_messages.json"):
            continue
        try:
            lines = (Path(path).parent / "agent.log").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        errors: list[str] = []
        for position, line in enumerate(lines):
            if " - ERROR - " not in line:
                continue
            text = line.split(" - ERROR - ", 1)[1].strip()
            if position + 1 < len(lines) and " - " not in lines[position + 1][:30]:
                text += " " + lines[position + 1].strip()
            if text not in errors:
                errors.append(text)
        if errors:
            evidence.append({"ref": {"kind": "evaluator_log", "result_index": index},
                             "content": "\n".join(errors)[:limit]})
    return evidence


def case_reflection_evidence(trajectory: dict) -> list[dict]:
    """Evidence for case-only post-task reflection: the shared evidence plus the site's code.

    Kept separate from exported_chat_evidence so that the abstract Long Memory path and the
    older runners see exactly the evidence they saw before.
    """
    return (exported_chat_evidence(trajectory) + generated_code_evidence(trajectory)
            + evaluator_log_evidence(trajectory) + guidance_received_evidence(trajectory))
