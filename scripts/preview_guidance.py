#!/usr/bin/env python3
"""Stage 1-2 preview: the guidance a Long Memory task would receive now, without generating a website.

Runs the same retrieval, adaptation, common pool and condense steps as the runner (leave-one-task-out),
reading the chain's memory.db without changing it. Its log goes to a separate preview file so the
chain's memory-events.jsonl is not touched. Prints the final prompt and the condense numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import run_continual_memory as rcm  # noqa: E402
from long_memory_integrations import AzureEmbedder, memory_llm_from_settings  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Long Memory chain directory")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--memory-config", type=Path, default=ROOT / "config" / "long_memory_condensed.json")
    parser.add_argument("--prompt-out", type=Path, help="also write the final prompt to this file")
    parser.add_argument("--log", type=Path, required=True, help="where the preview's own events go")
    parser.add_argument("--memory-url", help="self-hosted memory model endpoint (skips .env and Azure)")
    parser.add_argument("--memory-key-file", type=Path)
    parser.add_argument("--embedding-url", help="self-hosted embedding endpoint (with --memory-url)")
    parser.add_argument("--embedding-key-file", type=Path)
    args = parser.parse_args()
    candidates = sorted(args.output.glob(f"tasks/{args.task_id}*/task.jsonl"))
    if not candidates:
        raise SystemExit(f"no task.jsonl for {args.task_id} under {args.output}/tasks")
    task = json.loads(candidates[0].read_text().splitlines()[0])
    settings = load_long_memory_settings(args.memory_config.resolve())
    if args.memory_url:
        # Cluster profile: our own job's services through an SSH tunnel; never Azure.
        if "azure" in (args.memory_url + str(args.embedding_url)).lower() or not args.embedding_url:
            raise SystemExit("--memory-url needs --embedding-url, and neither may be Azure")
        client = rcm.OpenAI(api_key=args.memory_key_file.read_text().strip(), base_url=args.memory_url,
                            timeout=600, max_retries=2)
        embedding_client = rcm.OpenAI(api_key=args.embedding_key_file.read_text().strip(),
                                      base_url=args.embedding_url, timeout=120, max_retries=2)
    else:
        rcm.load_dotenv(ROOT / ".env")
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        client = rcm.OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                            base_url=os.environ.get("WEBGEN_MEMORY_BASE_URL") or f"{endpoint}/openai/v1",
                            timeout=120, max_retries=2)
        embedding_client = client
    llm = memory_llm_from_settings(client, settings.memory_llm)
    embedder = AzureEmbedder(embedding_client, settings.embedding["deployment"],
                             dimensions=settings.embedding["dimensions"])
    with ReflectionCaseMemory(str(args.output / "memory.db"), "bolt", llm=llm, embedder=embedder,
                              config=settings.memory, log=rcm.JsonlRunLog(args.log)) as memory:
        memory.statistics_task_id = args.task_id
        packet = memory.retrieve(task["instruction"])
    from long_memory_integrations import bolt_memory_prompt
    prompt = bolt_memory_prompt(task["instruction"], packet)  # exactly what the runner sends to Bolt
    if args.prompt_out:
        args.prompt_out.parent.mkdir(parents=True, exist_ok=True)
        args.prompt_out.write_text(prompt, encoding="utf-8")
    print(prompt)
    events = [json.loads(line) for line in args.log.read_text().splitlines() if '"case_retrieval"' in line]
    if events:
        print("\nCONDENSE:", json.dumps(events[-1].get("guidance_condense"), ensure_ascii=False))
        print("COMMON POOL:", [p["implementation_pattern"] for p in events[-1].get("common_pool", {}).get("patterns", [])])


if __name__ == "__main__":
    main()
