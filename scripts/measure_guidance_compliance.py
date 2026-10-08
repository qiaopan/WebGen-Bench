#!/usr/bin/env python3
"""Compliance: does the generated website's code do what each guidance line asks? (measurement only)

Reads stage2.json (guidance + common pool) and the generated project's own source. One Memory-LLM call
per line; the model must cite a verbatim code line, checked against the files. Nothing is written back and
nothing is regenerated.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from long_memory_integrations import generated_code_evidence  # noqa: E402
from memory_stage1_retrieval import make_memory_clients  # noqa: E402

INSTRUCTIONS = """You check ONE requirement against a website's source code. Decide from the code alone
whether the code implements what the requirement asks for: "yes" (clearly implemented), "partial" (some of
it, or only in some places) or "no" (absent or contradicted). Do not judge quality or style. Quote ONE
verbatim code line that supports your verdict (for "no", the closest relevant line, or null when nothing is
relevant). Return JSON only: {"verdict":"yes|partial|no","file":str|null,"snippet":str|null,"reason":str}."""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--generation-dir", type=Path, required=True, help="dir with 000001.json and extracted/000001")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config/long_memory.json")
    args = parser.parse_args()
    stage2 = json.loads(args.stage2.read_text(encoding="utf-8"))
    _, llm, _ = make_memory_clients(args.memory_config.resolve())
    code = generated_code_evidence({"trace_path": str((args.generation_dir / "000001.json").resolve())})
    files = {e["ref"]["path"]: e["content"] for e in code
             if isinstance(e.get("ref"), dict) and e["ref"].get("kind") == "code_file"}
    norm = lambda text: re.sub(r"\s+", " ", text or "").strip()
    lines = [("guidance", g["implementation_pattern"]) for g in stage2["guidance"]] + \
            [("common", text) for text in stage2.get("common", [])]
    results = []
    for kind, text in lines:
        answer = llm.generate("guidance_compliance", {"instructions": INSTRUCTIONS, "requirement": text, "code_files": code})
        answer = answer if isinstance(answer, dict) else {}
        snippet, file = norm(answer.get("snippet")), str(answer.get("file") or "")
        content = files.get(file) or next((c for p, c in files.items() if file and (p.endswith(file) or file.endswith(p))), None)
        grounded = bool(snippet and content is not None and snippet in norm(content))
        verdict = answer.get("verdict") if answer.get("verdict") in ("yes", "partial", "no") else "unknown"
        if verdict in ("yes", "partial") and not grounded:
            verdict = "unverified"
        results.append({"kind": kind, "requirement": text, "verdict": verdict, "file": file,
                        "snippet": snippet[:200], "grounded": grounded, "reason": str(answer.get("reason", ""))[:300]})
    counts = {v: sum(r["verdict"] == v for r in results) for v in ("yes", "partial", "no", "unverified", "unknown")}
    print("compliance:", counts, f"-> implemented {counts['yes']}/{len(results)}")
    for r in results:
        print(f"  [{r['kind']:<8}] {r['verdict']:<10} {r['requirement'][:100]}\n      -> {r['file']}: {r['snippet'][:90]} | {r['reason'][:140]}")
    if args.out:
        args.out.write_text(json.dumps({"counts": counts, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
