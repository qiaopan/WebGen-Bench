#!/usr/bin/env python3
"""Fail fast before a reflective-memory run spends generation tokens.

This checks the exact deployments used by the pilot: Bolt's generator,
memory/reflection LLM, embedding service, and the evaluator.  Calls are kept
tiny and no credentials or response bodies are written to stdout.

Memory/reflection and embedding names come from --memory-config; their endpoints from
WEBGEN_MEMORY_* / WEBGEN_EMBEDDING_* (Azure otherwise).  WEBGEN_FORBID_AZURE=1 fails the check
before any call if a role would reach Azure (cluster profile: self-hosted models only).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from long_memory_settings import load_long_memory_settings  # noqa: E402


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def first(*names: str) -> str:
    return next((os.getenv(name, "").strip() for name in names if os.getenv(name, "").strip()), "")


def chat_ping(label: str, client: OpenAI, model: str, *, azure_style: bool = False) -> None:
    client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        **({"max_completion_tokens": 4} if azure_style else {"max_tokens": 4}),
        temperature=0,
    )
    print(f"PASS  {label}: {model}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config" / "long_memory.json")
    parser.add_argument("--skip-memory", action="store_true",
                        help="No Memory-only runs: do not check the memory/reflection LLM or the embedding service")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    settings = load_long_memory_settings(args.memory_config.resolve())

    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    azure_base = (os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/") + "/openai/v1"
                  if os.getenv("AZURE_OPENAI_ENDPOINT", "").strip() else "")
    generator_base = required("WEBGEN_GENERATOR_BASE_URL")
    generator_key = first("WEBGEN_GENERATOR_API_KEY") or azure_key
    functional_base = first("WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL", "WEBGEN_EVALUATOR_BASE_URL",
                            "WEBVOYAGER_BASE_URL")
    functional_key = first("WEBGEN_FUNCTIONAL_EVALUATOR_API_KEY", "WEBGEN_EVALUATOR_API_KEY") or azure_key
    appearance_base = first("WEBGEN_APPEARANCE_EVALUATOR_BASE_URL", "WEBGEN_EVALUATOR_BASE_URL",
                            "WEBVOYAGER_BASE_URL")
    appearance_key = first("WEBGEN_APPEARANCE_EVALUATOR_API_KEY", "WEBGEN_EVALUATOR_API_KEY") or azure_key
    memory_base = first("WEBGEN_MEMORY_BASE_URL") or azure_base
    memory_key = first("WEBGEN_MEMORY_API_KEY") or azure_key
    embedding_base = first("WEBGEN_EMBEDDING_BASE_URL") or memory_base
    embedding_key = first("WEBGEN_EMBEDDING_API_KEY") or memory_key
    generator_model = os.getenv("WEBGEN_GENERATOR_API_MODEL", "webgen-generator-gpt41-mini")
    memory_model = settings.memory_llm["deployment"]
    embedding_model = settings.embedding["deployment"]
    functional_model = os.getenv("WEBGEN_FUNCTIONAL_EVALUATOR_MODEL", os.getenv("WEBVOYAGER_API_MODEL", ""))
    appearance_model = os.getenv("WEBGEN_APPEARANCE_EVALUATOR_MODEL", os.getenv("WEBVOYAGER_API_MODEL", ""))

    roles = {"generator": generator_base, "functional evaluator": functional_base,
             "appearance evaluator": appearance_base}
    if not args.skip_memory:
        roles.update({"memory/reflection": memory_base, "embedding": embedding_base})
    missing = [label for label, base in roles.items() if not base]
    if missing:
        raise SystemExit(f"FAIL  no endpoint configured for: {', '.join(missing)}")
    if os.getenv("WEBGEN_FORBID_AZURE") == "1":
        azure_roles = [label for label, base in roles.items() if "azure.com" in base]
        if azure_roles:
            raise SystemExit(f"FAIL  WEBGEN_FORBID_AZURE=1 but these roles point at Azure: {', '.join(azure_roles)}")

    generator = OpenAI(api_key=generator_key, base_url=generator_base, timeout=30, max_retries=0)
    memory = OpenAI(api_key=memory_key, base_url=memory_base, timeout=90, max_retries=0)
    embedding = OpenAI(api_key=embedding_key, base_url=embedding_base, timeout=30, max_retries=0)
    functional = OpenAI(api_key=functional_key, base_url=functional_base, timeout=90, max_retries=0)
    appearance = OpenAI(api_key=appearance_key, base_url=appearance_base, timeout=90, max_retries=0)
    failures: list[str] = []
    checks = [("generator", generator, generator_model, False),
              ("functional evaluator", functional, functional_model, "azure.com" in functional_base),
              ("appearance evaluator", appearance, appearance_model, "azure.com" in appearance_base)]
    if not args.skip_memory:
        checks.insert(1, ("memory", memory, memory_model, "azure.com" in memory_base))
    for label, client, model, azure_style in checks:
        try:
            chat_ping(label, client, model, azure_style=azure_style)
        except Exception as error:  # report deployment identity, never a key
            failures.append(f"FAIL  {label}: {model} ({type(error).__name__}: {error})")

    try:
        if not args.skip_memory:
            response = embedding.embeddings.create(model=embedding_model, input=["health check"])
            if not response.data or not response.data[0].embedding:
                raise RuntimeError("empty embedding response")
            print(f"PASS  embedding: {embedding_model}")
    except Exception as error:
        failures.append(f"FAIL  embedding: {embedding_model} ({type(error).__name__}: {error})")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
    print("All required pilot models are reachable. Starting the experiment is safe.")


if __name__ == "__main__":
    main()
