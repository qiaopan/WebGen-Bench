"""Static code facts for Table 5.3: per run, tasks with an undeclared import or a Vue compile error, tasks with a
missing Vue import, and .vue components with a missing Vue import (numerator / denominator).
Usage (on the cluster, inside a Slurm allocation): python scripts/cluster/static_facts_table.py RUN_DIR [RUN_DIR ...]"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import code_memory as cm
# The compiler can throw an error without loc.start; the cached checker crashed on it and recorded the site as unknown.
cm._COMPILE_JS = cm._COMPILE_JS.replace("e.loc ? e.loc.start.line", "e.loc && e.loc.start ? e.loc.start.line")

def order(run: Path) -> list[str]:
    seen = []
    for line in open(run / "progress.jsonl"):
        t = json.loads(line)["task_id"]
        if t not in seen:
            seen.append(t)
    return seen

def file_missing(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    code = "\n".join(cm._SCRIPT.findall(text))
    if not code or re.search(r"import\s+\*\s+as\s+\w+\s+from\s+['\"]vue['\"]", code):
        return False
    imported = {n.strip().split(" as ")[-1].strip() for m in cm._VUE_IMPORT.findall(code) for n in m.split(",")}
    return any(api not in imported and re.search(rf"(?<![\w.]){api}\s*[(<]", code)
               and not re.search(rf"(function|const|let|var)\s+{api}\b", code) for api in cm._VUE_APIS)

for arg in sys.argv[1:]:
    run = Path(arg)
    ids = order(run)
    segs = [ids[:30], ids[30:60], ids[60:]]
    brk, miss, unknown = [0, 0, 0], [0, 0, 0], []
    comps = bad = 0
    for k, seg in enumerate(segs):
        for t in seg:
            site = run / "tasks" / t / "continual" / "extracted" / "000001"
            if not (site / "package.json").is_file():
                unknown.append(t); continue
            f = cm.site_facts(site)
            if f["compile_errors"] is None:
                unknown.append(t)
            if f["undeclared"] or f["compile_errors"]:
                brk[k] += 1
            if f["missing_vue_api"]:
                miss[k] += 1
            for p in (site / "src").rglob("*.vue") if (site / "src").is_dir() else []:
                comps += 1; bad += file_missing(p)
    print(json.dumps({"run": run.name, "n": len(ids), "break": brk, "break_total": sum(brk),
                      "missing_import": miss, "missing_total": sum(miss), "components": comps,
                      "components_missing_import": bad, "pct": round(100 * bad / max(comps, 1), 2),
                      "unknown": unknown}))
