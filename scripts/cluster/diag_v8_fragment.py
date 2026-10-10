"""Diagnostic (not a formal run): does the v8 fragment stop the scaffold outputs of v7 on seed 11?

For each task, take the v7 seed-11 prompt and replace only the whole-file example in the "Missing package"
code-pool entry with a fragment picked by code_memory._pick_fragment (the v8 path). Everything else in the
prompt stays as v7 sent it. Generate once with the worker's Bolt and 7B (official protocol, no repair), then
check the code only: scaffold or not, .vue files, undeclared imports. No evaluation, no memory writes.

    python scripts/cluster/diag_v8_fragment.py --key-file K --out DIR TASK...
"""
import argparse, json, os, re, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "src" / "automatic_bolt_diy"))
from openai import OpenAI  # noqa: E402
from long_memory_settings import load_long_memory_settings  # noqa: E402
from long_memory_integrations import memory_llm_from_settings  # noqa: E402
from code_memory import _pick_fragment  # noqa: E402
from automatic_web_gen import automatic_web_gen  # noqa: E402

V7 = ROOT / "outputs/experiment/cluster_order_blocks11_longmem_v7/tasks"
BLOCK = re.compile(r"(Missing package:.*?Code that works:\n```vue\n)(.*?)(```)", re.S)

ap = argparse.ArgumentParser()
ap.add_argument("--key-file", required=True); ap.add_argument("--out", required=True); ap.add_argument("tasks", nargs="+")
a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
settings = load_long_memory_settings(ROOT / "config/long_memory_cluster_v8.json")
client = OpenAI(base_url=os.environ["WEBGEN_MEMORY_BASE_URL"], api_key=Path(a.key_file).read_text().strip())
llm = memory_llm_from_settings(client, settings.memory_llm)

fragment = {}
for i, task in enumerate(a.tasks, 1):
    prompt = next(V7.glob(f"{task}/*/000001.prompt.txt")).read_text()
    m = BLOCK.search(prompt)
    if not m:
        print(task, "no whole-file block; skipped"); continue
    whole = m.group(2)
    if whole not in fragment:  # same source file on every task; pick once, as v8 stores it once
        picked = _pick_fragment(llm, whole, "earlier websites imported a package that package.json does not "
                                "declare, so the whole site showed a blank page; the working file below does the "
                                "same job using only what is installed")
        fragment[whole] = picked["code"]
        (out / "fragment.json").write_text(json.dumps(picked, indent=1))
        print("FRAGMENT\n" + str(picked["code"]))
    if not fragment[whole]:
        print(task, "no fragment picked; skipped"); continue
    new = prompt[:m.start(2)] + fragment[whole].rstrip() + "\n" + prompt[m.end(2):]
    d = out / task; d.mkdir(exist_ok=True)
    (d / "prompt.v8.txt").write_text(new)
    try:
        automatic_web_gen(1, new, download_dir=str(d), url=os.environ["WEBGEN_BOLT_URL"],
                          desired_model=os.environ.get("WEBGEN_GENERATOR_API_MODEL", "WebGen-LM-7B"),
                          provider="OpenAILike", headless=True, max_repair_attempts=0)
    except Exception as error:  # noqa: BLE001
        print(task, "generation error", str(error)[:200])
    z = d / "000001.zip"
    if not z.is_file():
        print(f"RESULT {task} no zip"); continue
    with zipfile.ZipFile(z) as f:
        names = f.namelist()
        vues = [n for n in names if n.endswith(".vue")]
        pkg = next((n for n in names if n.endswith("package.json") and "node_modules" not in n), None)
        deps = set()
        if pkg:
            j = json.loads(f.read(pkg)); deps = set(j.get("dependencies", {})) | set(j.get("devDependencies", {}))
        imports = set()
        for n in names:
            if n.endswith((".vue", ".ts", ".js")) and "node_modules" not in n:
                for p in re.findall(r"""from\s+['"]([^'"./][^'"]*)['"]""", f.read(n).decode(errors="ignore")):
                    imports.add(p if p.startswith("@") and "/" in p and p.count("/") == 1 else p.split("/")[0] if not p.startswith("@") else "/".join(p.split("/")[:2]))
    base = {Path(v).name for v in vues}
    scaffold = base <= {"App.vue", "HelloWorld.vue"}
    print(f"RESULT {task} scaffold={scaffold} vue={len(vues)} undeclared={sorted(imports - deps)} "
          f"files={sorted(base)[:8]}")
