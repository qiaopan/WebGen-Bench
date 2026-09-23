#!/usr/bin/env python3
"""Fail fast before a reflective-memory run spends generation tokens.

This checks the exact deployments used by the pilot: Bolt's generator,
memory/reflection LLM, embedding service, and the evaluator.  Calls are kept
tiny and no credentials or response bodies are written to stdout.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def chat_ping(label: str, client: OpenAI, model: str) -> None:
    client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_completion_tokens=4,
        temperature=0,
    )
    print(f"PASS  {label}: {model}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = required("AZURE_OPENAI_API_KEY")
    generator_base = required("WEBGEN_GENERATOR_BASE_URL")
    evaluator_base = required("WEBVOYAGER_BASE_URL")
    generator_model = os.getenv("WEBGEN_GENERATOR_API_MODEL", "webgen-generator-gpt41-mini")
    memory_model = "webgen-memory-gpt41-mini"
    embedding_model = "webgen-memory-embedding"
    evaluator_model = os.getenv("WEBVOYAGER_API_MODEL", "webgen-evaluator-gpt54-mini")

    generator = OpenAI(api_key=key, base_url=generator_base, timeout=30, max_retries=0)
    evaluator = OpenAI(api_key=key, base_url=evaluator_base, timeout=30, max_retries=0)
    failures: list[str] = []
    for label, client, model in (
        ("generator", generator, generator_model),
        ("memory/reflection", generator, memory_model),
        ("evaluator", evaluator, evaluator_model),
    ):
        try:
            chat_ping(label, client, model)
        except Exception as error:  # report deployment identity, never a key
            failures.append(f"FAIL  {label}: {model} ({type(error).__name__}: {error})")

    try:
        response = generator.embeddings.create(model=embedding_model, input=["health check"])
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
