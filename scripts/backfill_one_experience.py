#!/usr/bin/env python3
"""Backfill and explicitly activate the selected 000020 reflection candidate."""
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "src" / "automatic_bolt_diy")]
from long_memory import connect_database
from long_memory_integrations import AzureEmbedder, AzureMemoryLLM
from long_memory_settings import load_long_memory_settings
from reflection_case_memory import ReflectionCaseMemory

load_dotenv(ROOT / ".env")
out = ROOT / "outputs/experiment/second_reflection_pilot_14_16_r1"
db = out / "memory.db"
event_file = out / "memory-events.jsonl"
review = None
for line in event_file.read_text(encoding="utf-8").splitlines():
    item = json.loads(line)
    if item.get("operation") == "case_consolidation_review" and item.get("review", {}).get("decision") == "experience":
        review = item["review"]
if review is None:
    raise SystemExit("No experience review candidate found")
settings = load_long_memory_settings(ROOT / "config/long_memory.json")
client = OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"], base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1", timeout=120)
llm = AzureMemoryLLM(client, settings.memory_llm["deployment"], max_tokens=settings.memory_llm["max_completion_tokens"])
embedder = AzureEmbedder(client, settings.embedding["deployment"], dimensions=settings.embedding["dimensions"])
with ReflectionCaseMemory(str(db), "bolt", llm=llm, embedder=embedder, config=settings.memory) as memory:
    record_id = memory.persist_experience_candidate(review)
    if not record_id:
        raise SystemExit("Candidate persistence returned no record")
    memory.activate_experience(record_id)
with connect_database(str(db), read_only=True) as conn:
    row = conn.execute("SELECT record_id,status,embedding_dim FROM experiences WHERE record_id=?", (record_id,)).fetchone()
    source_count = conn.execute("SELECT count(*) FROM memory_sources WHERE experience_record_id=?", (record_id,)).fetchone()[0]
print(json.dumps({"record_id": row["record_id"], "status": row["status"], "embedding_dim": row["embedding_dim"], "source_count": source_count}, ensure_ascii=False))
