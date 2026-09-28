"""Long Memory arm, diagnostic option: after a website builds, check it against the guidance it was given.

Each requirement line is checked against the generated source by one Memory-LLM call (the model must quote a
real code line, verified here). Requirements that are missing are returned as one message for a single extra
repair round. No evaluation result is used; the only inputs are the task's own prompt lines and the code.
"""
from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Sequence

from long_memory_integrations import generated_code_evidence

CHECK_INSTRUCTIONS = """You check ONE requirement against a website's source code. Decide from the code alone
whether the code implements what the requirement asks for: "yes" (clearly implemented), "partial" (some of
it, or only in some places) or "no" (absent or contradicted). Do not judge quality or style. Quote ONE
verbatim code line that supports your verdict (for "no", the closest relevant line, or null when nothing is
relevant). Return JSON only: {"verdict":"yes|partial|no","file":str|null,"snippet":str|null,"reason":str}."""


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def check_requirement(llm: Any, requirement: str, code: list[dict]) -> dict:
    files = {e["ref"]["path"]: e["content"] for e in code
             if isinstance(e.get("ref"), dict) and e["ref"].get("kind") == "code_file"}
    answer = llm.generate("guidance_compliance", {"instructions": CHECK_INSTRUCTIONS, "requirement": requirement,
                                                  "code_files": code})
    answer = answer if isinstance(answer, dict) else {}
    snippet, file = _norm(answer.get("snippet")), str(answer.get("file") or "")
    content = files.get(file) or next((c for p, c in files.items() if file and (p.endswith(file) or file.endswith(p))), None)
    grounded = bool(snippet and content is not None and snippet in _norm(content))
    verdict = answer.get("verdict") if answer.get("verdict") in ("yes", "partial", "no") else "unknown"
    if verdict in ("yes", "partial") and not grounded:
        verdict = "unverified"
    return {"verdict": verdict, "file": file, "snippet": snippet[:200], "grounded": grounded,
            "reason": str(answer.get("reason", ""))[:300]}


def project_code(archive: str | Path) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="webgen-selfcheck-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root)
        package = next((p for p in [root / "package.json", *root.glob("*/package.json")] if p.is_file()), None)
        return generated_code_evidence({}, project=package.parent if package else root)


def make_compliance_check(llm: Any, requirements: Sequence[str], log: Callable[[dict], None] | None = None
                          ) -> Callable[[str], str]:
    """Returns check(archive_path) -> repair message ('' when every requirement is found)."""
    lines = [r for r in requirements if str(r).strip()]

    def check(archive: str) -> str:
        code = project_code(archive)
        results = [{"requirement": text, **check_requirement(llm, text, code)} for text in lines]
        if log:
            log({"operation": "guidance_selfcheck", "archive": str(archive), "results": results})
        missing = [r for r in results if r["verdict"] in ("no", "partial")]
        if not missing:
            return ""
        return ("\n\nBefore finishing, these requirements from this task's implementation guidance were not found "
                "in your code. Implement each of them now, keep everything else unchanged, and return the complete "
                "corrected project:\n" + "\n".join(f"- {r['requirement']} (found in code: {r['reason']})" for r in missing) + "\n")

    return check
