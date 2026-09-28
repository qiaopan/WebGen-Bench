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


def chat_ping(label: str, client: OpenAI, model: str, *, azure_style: bool = False) -> None:
    client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        **({"max_completion_tokens": 4} if azure_style else {"max_tokens": 4}),
        temperature=0,
    )
    print(f"PASS  {label}: {model}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    azure_key = required("AZURE_OPENAI_API_KEY")
    azure_base = required("AZURE_OPENAI_ENDPOINT").rstrip("/") + "/openai/v1"
    generator_base = required("WEBGEN_GENERATOR_BASE_URL")
    generator_key = (os.getenv("WEBGEN_GENERATOR_API_KEY") or azure_key).strip()
    functional_base = (os.getenv("WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL")
                       or os.getenv("WEBGEN_EVALUATOR_BASE_URL")
                       or required("WEBVOYAGER_BASE_URL")).strip()
    functional_key = (os.getenv("WEBGEN_FUNCTIONAL_EVALUATOR_API_KEY")
                      or os.getenv("WEBGEN_EVALUATOR_API_KEY") or azure_key).strip()
    appearance_base = (os.getenv("WEBGEN_APPEARANCE_EVALUATOR_BASE_URL")
                       or os.getenv("WEBGEN_EVALUATOR_BASE_URL")
                       or required("WEBVOYAGER_BASE_URL")).strip()
    appearance_key = (os.getenv("WEBGEN_APPEARANCE_EVALUATOR_API_KEY")
                      or os.getenv("WEBGEN_EVALUATOR_API_KEY") or azure_key).strip()
    generator_model = os.getenv("WEBGEN_GENERATOR_API_MODEL", "webgen-generator-gpt41-mini")
    memory_model = "webgen-memory-gpt4o"
    embedding_model = "webgen-memory-embedding"
    functional_model = os.getenv("WEBGEN_FUNCTIONAL_EVALUATOR_MODEL", os.getenv("WEBVOYAGER_API_MODEL", ""))
    appearance_model = os.getenv("WEBGEN_APPEARANCE_EVALUATOR_MODEL", os.getenv("WEBVOYAGER_API_MODEL", ""))

    generator = OpenAI(api_key=generator_key, base_url=generator_base, timeout=30, max_retries=0)
    memory = OpenAI(api_key=azure_key, base_url=azure_base, timeout=30, max_retries=0)
    functional = OpenAI(api_key=functional_key, base_url=functional_base, timeout=90, max_retries=0)
    appearance = OpenAI(api_key=appearance_key, base_url=appearance_base, timeout=30, max_retries=0)
    failures: list[str] = []
    for label, client, model, azure_style in (
        ("generator", generator, generator_model, False),
        ("memory/reflection", memory, memory_model, True),
        ("functional evaluator", functional, functional_model, "azure.com/openai/v1" in functional_base),
        ("appearance evaluator", appearance, appearance_model, "azure.com/openai/v1" in appearance_base),
    ):
        try:
            chat_ping(label, client, model, azure_style=azure_style)
        except Exception as error:  # report deployment identity, never a key
            failures.append(f"FAIL  {label}: {model} ({type(error).__name__}: {error})")

    try:
        response = memory.embeddings.create(model=embedding_model, input=["health check"])
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
