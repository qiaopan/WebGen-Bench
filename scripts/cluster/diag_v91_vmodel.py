"""Diagnostic (not a formal run): v9.1 (compile-error entries universal) on the v9 seed-11 tasks that failed on
v-model. Takes the v9 run's own prompt, swaps only its code section for what v9.1 would inject from the v9 run's
memory database (leave-one-task-out as in the runner), generates once, and checks the code. No evaluation.

    python scripts/cluster/diag_v91_vmodel.py --out DIR TASK...
"""
import argparse, json, os, sqlite3, sys, types, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "src" / "automatic_bolt_diy"))
from long_memory_settings import load_long_memory_settings  # noqa: E402
from reflection_case_memory import ReflectionCaseMemory, CasePacket  # noqa: E402
import code_memory as cm  # noqa: E402
from automatic_web_gen import automatic_web_gen  # noqa: E402

V9 = ROOT / "outputs/experiment/cluster_order_blocks11_longmem_v9"
HEAD, FOOT = "\n\nCODE FROM EARLIER WEBSITES THAT WORKED:\n", "\n\nBuild every checklist item"
ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("tasks", nargs="+")
a = ap.parse_args(); out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
settings = load_long_memory_settings(ROOT / "config/long_memory_cluster_v9_1.json")
con = sqlite3.connect(f"file:{V9 / 'memory.db'}?mode=ro", uri=True); con.row_factory = sqlite3.Row
agent = con.execute("SELECT agent_id FROM code_memories LIMIT 1").fetchone()[0]
class NoModel:  # import entries are decided by code when the checklist has >= 3 items
    def generate(self, kind, payload): return {"decisions": []}
for t in a.tasks:
    prompt = next(V9.glob(f"tasks/{t}/*/000001.prompt.txt")).read_text()
    n_items = sum(1 for l in prompt.splitlines() if l[:1].isdigit() and ". " in l[:5])
    me = types.SimpleNamespace(connection=con, agent_id=agent, llm=NoModel(), config=settings.memory,
                               record_code_uses=False, _has_table=lambda name: True, statistics_task_id=t)
    packet, info = ReflectionCaseMemory.add_code_pool(me, "", CasePacket(checklist=(("x", ()),) * n_items))
    base = prompt.split(HEAD)[0] if HEAD in prompt else prompt.split(FOOT)[0]
    tail = FOOT + prompt.split(FOOT, 1)[1] if FOOT in prompt else ""
    new = base + HEAD + packet._code_text() + tail
    d = out / t; d.mkdir(exist_ok=True); (d / "prompt.v91.txt").write_text(new)
    try:
        automatic_web_gen(1, new, download_dir=str(d), url=os.environ["WEBGEN_BOLT_URL"],
                          desired_model=os.environ.get("WEBGEN_GENERATOR_API_MODEL", "WebGen-LM-7B"),
                          provider="OpenAILike", headless=True, max_repair_attempts=0)
    except Exception as error:  # noqa: BLE001
        print(t, "generation error", str(error)[:200])
    r = {"task": t, "injected": [x.split(". ")[0] for x, _ in packet.code_examples]}
    if (d / "000001.zip").is_file():
        with zipfile.ZipFile(d / "000001.zip") as f:
            f.extractall(d / "site")
        root = next((p.parent for p in (d / "site").rglob("package.json") if "node_modules" not in p.parts), d / "site")
        vues = {p.name for p in root.rglob("*.vue") if "node_modules" not in p.parts}
        r.update(scaffold=bool(vues) and vues <= {"App.vue", "HelloWorld.vue"}, n_vue=len(vues),
                 problems=sorted(cm.problem_keys(root, cm.site_facts(root))))
    print("RESULT", json.dumps(r), flush=True)
