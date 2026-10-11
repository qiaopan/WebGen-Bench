"""Diagnostic: replay the code-pool updates of a finished chain on a fresh database (no generation), to check how
code memories are created and versioned under a given config. Uses the real memory model.

    python scripts/cluster/replay_code_pool.py RUN_DIR CONFIG --key-file K --out DB
"""
import argparse, json, os, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from openai import OpenAI  # noqa: E402
from long_memory import initialize_database, ensure_optional_tables  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from long_memory_integrations import memory_llm_from_settings  # noqa: E402
import code_memory as cm  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("config")
ap.add_argument("--key-file", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
settings = load_long_memory_settings(ROOT / a.config)
cm.CODE_POOL_REFRESH = settings.memory.code_pool_refresh
cm.REFRESH_MONOTONIC = settings.memory.code_pool_refresh_monotonic
llm = memory_llm_from_settings(OpenAI(base_url=os.environ["WEBGEN_MEMORY_BASE_URL"],
                                      api_key=Path(a.key_file).read_text().strip()), settings.memory_llm)
run = ROOT / a.run
order = json.load(open(run / "task-order.json"))["task_ids"]
score = {}
for l in open(run / "progress.jsonl"):
    x = json.loads(l)
    ev = [e for e in x.get("evaluation") or [] if e["check"] != "appearance" and e["outcome"] != "scored"]
    if ev:
        score[x["task_id"]] = (sum(e["outcome"] == "passed" for e in ev) + 0.5 * sum(e["outcome"] == "partial" for e in ev)) / len(ev)
Path(a.out).unlink(missing_ok=True); initialize_database(Path(a.out))
con = sqlite3.connect(a.out); ensure_optional_tables(con)
chain = []
for t in order:
    if t not in score:
        continue
    chain.append({"task_id": t, "trace_path": str(run / f"tasks/{t}/continual/000001.json"), "score": score[t]})
    info = cm.update_code_pool(con, "replay", llm, chain, ROOT, current_task=t,
                               min_tasks_site_break=settings.memory.code_memory_min_tasks_site_break)
    for x in info.get("added", []):
        print(f"{len(chain):3d} {t} ADD {x['key']}")
    for f in info.get("refresh", []):
        if "new_code_id" in f:
            print(f"{len(chain):3d} {t} VERSION need={f['need']} new_first_line={f['new_code'].splitlines()[0]!r}")
for r in con.execute("SELECT problem_key, status, superseded_at_task, substr(replace(code, char(10), ' | '), 1, 120) "
                     "FROM code_memories ORDER BY created_at"):
    print("ROW", r)
