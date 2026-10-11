"""Diagnostic (not a formal run): v9 code pool on the seed-11 tasks that went wrong under v7, plus v7 high scorers.

The v9 code pool is rebuilt task by task on a fresh database from the v7 seed-11 sites (as replay_code_pool.py does).
At each target task, the entries v9 would inject at that position are chosen with the v9 retrieval rules, and they
replace only the code section of the v7 prompt; everything else stays as v7 sent it. One generation with the worker's
Bolt and 7B (official protocol, no repair), then a code check only: scaffold, undeclared packages, compile errors,
missing Vue imports. No evaluation; nothing written to any run's memory.

    python scripts/cluster/diag_v9_codepool.py --key-file K --out DIR TASK...
"""
import argparse, json, os, sqlite3, sys, types, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "src" / "automatic_bolt_diy"))
from openai import OpenAI  # noqa: E402
from long_memory import initialize_database, ensure_optional_tables  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from long_memory_integrations import memory_llm_from_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory, CasePacket  # noqa: E402
import code_memory as cm  # noqa: E402
from automatic_web_gen import automatic_web_gen  # noqa: E402

V7 = ROOT / "outputs/experiment/cluster_order_blocks11_longmem_v7"
HEAD, FOOT = "\n\nCODE FROM EARLIER WEBSITES THAT WORKED:\n", "\n\nBuild every checklist item"
ap = argparse.ArgumentParser(); ap.add_argument("--key-file", required=True); ap.add_argument("--out", required=True)
ap.add_argument("tasks", nargs="+"); a = ap.parse_args()
targets = set(a.tasks); out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
settings = load_long_memory_settings(ROOT / "config/long_memory_cluster_v9.json")
cm.CODE_POOL_REFRESH = settings.memory.code_pool_refresh; cm.REFRESH_MONOTONIC = settings.memory.code_pool_refresh_monotonic
llm = memory_llm_from_settings(OpenAI(base_url=os.environ["WEBGEN_MEMORY_BASE_URL"],
                                      api_key=Path(a.key_file).read_text().strip()), settings.memory_llm)
order = json.load(open(V7 / "task-order.json"))["task_ids"]
score = {}
for l in open(V7 / "progress.jsonl"):
    x = json.loads(l); ev = [e for e in x.get("evaluation") or [] if e["check"] != "appearance" and e["outcome"] != "scored"]
    if ev:
        score[x["task_id"]] = (sum(e["outcome"] == "passed" for e in ev) + .5 * sum(e["outcome"] == "partial" for e in ev)) / len(ev)
db = out / "v9_pool.db"; db.unlink(missing_ok=True); initialize_database(db)
con = sqlite3.connect(db); con.row_factory = sqlite3.Row; ensure_optional_tables(con)
me = types.SimpleNamespace(connection=con, agent_id="replay", llm=llm, config=settings.memory,
                           record_code_uses=False, _has_table=lambda name: True)
chain, results = [], []
for pos, t in enumerate(order, 1):
    if t in targets:
        prompt = next(V7.glob(f"tasks/{t}/*/000001.prompt.txt")).read_text()
        n_items = sum(1 for l in prompt.splitlines() if l[:1].isdigit() and ". " in l[:5])
        me.statistics_task_id = t
        packet, info = ReflectionCaseMemory.add_code_pool(me, prompt.split("\n\n")[0], CasePacket(checklist=(("x", ()),) * n_items))
        code = packet._code_text()
        base = prompt.split(HEAD)[0] if HEAD in prompt else prompt.split(FOOT)[0]
        tail = FOOT + prompt.split(FOOT, 1)[1] if FOOT in prompt else ""
        new = base + (HEAD + code if code else "") + tail
        d = out / t; d.mkdir(exist_ok=True); (d / "prompt.v9.txt").write_text(new)
        (d / "code_pool.json").write_text(json.dumps(info, indent=1, default=str))
        try:
            automatic_web_gen(1, new, download_dir=str(d), url=os.environ["WEBGEN_BOLT_URL"],
                              desired_model=os.environ.get("WEBGEN_GENERATOR_API_MODEL", "WebGen-LM-7B"),
                              provider="OpenAILike", headless=True, max_repair_attempts=0)
        except Exception as error:  # noqa: BLE001
            print(t, "generation error", str(error)[:200])
        r = {"pos": pos, "task": t, "v7": round(score.get(t, -1), 2),
             "injected": [k for k in (x.split(". ")[0] for x, _ in packet.code_examples)]}
        z = d / "000001.zip"
        if z.is_file():
            site = d / "site"
            with zipfile.ZipFile(z) as f:
                f.extractall(site)
            root = next((p.parent for p in site.rglob("package.json") if "node_modules" not in p.parts), site)
            vues = {p.name for p in root.rglob("*.vue") if "node_modules" not in p.parts}
            r.update(scaffold=bool(vues) and vues <= {"App.vue", "HelloWorld.vue"}, n_vue=len(vues),
                     problems=sorted(cm.problem_keys(root, cm.site_facts(root))))
        else:
            r["no_zip"] = True
        results.append(r); print("RESULT", json.dumps(r), flush=True)
    if t in score:
        chain.append({"task_id": t, "trace_path": str(V7 / f"tasks/{t}/continual/000001.json"), "score": score[t]})
        cm.update_code_pool(con, "replay", llm, chain, ROOT, current_task=t,
                            min_tasks_site_break=settings.memory.code_memory_min_tasks_site_break)
(out / "results.json").write_text(json.dumps(results, indent=1))
