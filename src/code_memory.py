"""Code memory (v5): code taken from the generator's own earlier websites, not written by hand.

Recurring breakage is detected by code on the sites earlier tasks of this chain generated:
  * a package imported but not declared in package.json (the site does not start: blank page);
  * a Vue template that does not compile (the site shows an error overlay).
When the same breakage has occurred in at least ``min_tasks`` earlier tasks (recurrence before codifying, as in
Metis, Dai et al. 2026), the matching code of an earlier site that worked (score >= ``min_score``, nothing undeclared,
compiles) is offered as an example: its App.vue for view switching, or the element written correctly for a compile
error. Only earlier tasks are read (the current task is excluded); results are cached per site in
``code_facts.json`` next to the site.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Iterable

_IMPORT = re.compile(r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|import\(\s*|require\(\s*)['"]([^'"]+)['"]""")
_NODE_BUILTINS = {"fs", "path", "url", "os", "crypto", "util", "events", "stream", "http", "https", "child_process"}
_FACTS_VERSION = 5

# Compiles every .vue file of a site with the site's own @vue/compiler-sfc; prints JSON errors.
_COMPILE_JS = r"""
const path = require('path'), fs = require('fs');
const root = process.argv[1];
const sfc = require(require.resolve('@vue/compiler-sfc', {paths: [process.argv[2] || root]}));
const out = [];
function walk(d) { for (const e of fs.readdirSync(d, {withFileTypes: true})) {
  const p = path.join(d, e.name);
  if (e.isDirectory()) { if (e.name !== 'node_modules') walk(p); } else if (p.endsWith('.vue')) check(p); } }
function check(f) {
  const src = fs.readFileSync(f, 'utf8');
  const {descriptor: d, errors} = sfc.parse(src, {filename: f});
  const push = (offset) => (e) => out.push({file: path.relative(root, f), message: String(e.message || e),
                                line: e.loc ? e.loc.start.line + offset : null});
  errors.forEach(push(0));  // parse errors: lines are already file-relative
  if (d.scriptSetup) {
    // Compile script and template together, as Vite does: only then are props known (v-model on a prop, ...).
    try { sfc.compileScript(d, {id: 'x', inlineTemplate: true}); }
    catch (e) { push(e.loc && e.loc.source !== undefined ? 0 : 0)(e); }
  } else if (d.template) sfc.compileTemplate({source: d.template.content, filename: f, id: 'x'})
    .errors.forEach(push(d.template.loc.start.line - 1));
}
walk(path.join(root, 'src'));
console.log(JSON.stringify(out));
"""


def site_root(trace_path: str, repo_root: Path) -> Path | None:
    """The generated project of a trajectory (``<task dir>/extracted/000001``). Cluster paths are mapped onto the
    local checkout when the run is analysed elsewhere."""
    candidates = [Path(trace_path)]
    marker = "/outputs/experiment/"
    if marker in trace_path:
        candidates.append(repo_root / ("outputs/experiment/" + trace_path.split(marker, 1)[1]))
    for trace in candidates:
        site = trace.parent / "extracted" / "000001"
        if (site / "package.json").is_file():
            return site
    return None


def _declared(site: Path) -> set[str]:
    try:
        data = json.loads((site / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {name for key in ("dependencies", "devDependencies") for name in (data.get(key) or {})}


def _sources(site: Path) -> Iterable[Path]:
    src = site / "src"
    if src.is_dir():
        yield from (p for p in src.rglob("*") if p.is_file() and p.suffix in (".vue", ".ts", ".js", ".tsx", ".jsx"))


def _undeclared(site: Path) -> list[str]:
    declared, found = _declared(site), set()
    for path in _sources(site):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for spec in _IMPORT.findall(text):
            if spec.startswith((".", "/", "@/", "~", "#")) or ":" in spec:
                continue
            parts = spec.split("/")
            name = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
            if name and name not in declared and name not in _NODE_BUILTINS:
                found.add(name)
    return sorted(found)


def _compile_errors(site: Path) -> list[dict] | None:
    node = os.environ.get("WEBGEN_NODE") or shutil.which("node")
    resolve_from = site
    if not (site / "node_modules" / "@vue" / "compiler-sfc").is_dir():
        # Sites copied without node_modules (analysis off the cluster): another project's compiler.
        fallback = os.environ.get("WEBGEN_VUE_COMPILER_PROJECT")
        resolve_from = Path(fallback).resolve() if fallback and (Path(fallback) / "node_modules" / "@vue" / "compiler-sfc").is_dir() else None
    if node is None or resolve_from is None:
        return None  # cannot check: treated as unknown, never as clean
    try:
        result = subprocess.run([node, "-e", _COMPILE_JS, str(site.resolve()), str(resolve_from.resolve())], capture_output=True,
                                text=True, timeout=120)
        return json.loads(result.stdout or "[]") if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _stamp(site: Path) -> str:
    """Changes whenever the site's sources change (a rerun written into the same directory)."""
    files = [site / "package.json", *_sources(site)]
    return f"{len(files)}:" + str(max((f.stat().st_mtime_ns for f in files if f.is_file()), default=0))


def site_facts(site: Path) -> dict:
    cache = site.parent / "code_facts.json"
    stamp = _stamp(site)
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("version") == _FACTS_VERSION and cached.get("stamp") == stamp:
            return cached
    except (OSError, ValueError):
        pass
    errors = _compile_errors(site)
    for error in errors or []:
        error["source_line"] = _line(site / error["file"], error.get("line"))
    facts = {"version": _FACTS_VERSION, "stamp": stamp, "undeclared": _undeclared(site), "compile_errors": errors,
             "missing_vue_api": missing_vue_imports(site)}
    if errors is None:
        return facts  # unknown (no node, or a timeout on a busy node): not cached, checked again next time
    try:
        cache.write_text(json.dumps(facts), encoding="utf-8")
    except OSError:
        pass
    return facts


def _line(path: Path, number: int | None) -> str:
    if not number:
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    return lines[number - 1].strip() if 0 < number <= len(lines) else ""


def _element_key(source_line: str) -> str | None:
    """``input[type=file]`` for ``<input type="file" v-model="x">``: the element a compile error is about."""
    tag = re.search(r"<([a-zA-Z][\w-]*)", source_line)
    if not tag:
        return None
    kind = re.search(r"""\btype=["']([\w-]+)["']""", source_line)
    return tag.group(1).lower() + (f"[type={kind.group(1).lower()}]" if kind else "")


def _strip_style(text: str) -> str:
    return re.sub(r"<style[\s\S]*?</style>", "", text).strip()


def build_code_examples(earlier: list[dict], repo_root: Path, *, min_tasks: int = 2, min_score: float = 0.5,
                        max_lines: int = 40, max_examples: int = 2,
                        scan_seconds: float = 600) -> tuple[list[dict], dict]:
    """``earlier``: [{task_id, trace_path, score}] for earlier tasks only. Returns examples
    [{kind, problem, text, code, source_task}] and an info dict for the run log."""
    sites, started, skipped = [], time.monotonic(), 0
    for item in earlier:
        if time.monotonic() - started > scan_seconds:  # never hold a task up for long; the rest are cached later
            skipped += 1
            continue
        site = site_root(str(item["trace_path"]), repo_root)
        if site is not None:
            sites.append({**item, "site": site, "facts": site_facts(site)})
    import_tasks: dict[str, set[str]] = {}
    compile_tasks: dict[str, set[str]] = {}
    compile_message: dict[str, str] = {}
    for s in sites:
        for package in s["facts"]["undeclared"]:
            import_tasks.setdefault(package, set()).add(s["task_id"])
        for error in s["facts"]["compile_errors"] or []:
            key = _element_key(error.get("source_line", ""))
            if key:
                compile_tasks.setdefault(key, set()).add(s["task_id"])
                compile_message.setdefault(key, error["message"].split("\n")[0][:160])
    good = sorted((s for s in sites if s["score"] >= min_score and not s["facts"]["undeclared"]
                   and s["facts"]["compile_errors"] == []), key=lambda s: -s["score"])
    examples: list[dict] = []
    info = {"sites": len(sites), "good_sites": len(good), "scan_skipped": skipped,
            "node": os.environ.get("WEBGEN_NODE") or shutil.which("node"),
            "compile_unknown": sum(s["facts"]["compile_errors"] is None for s in sites),
            "recurring_imports": {k: sorted(v) for k, v in import_tasks.items() if len(v) >= min_tasks},
            "recurring_compile": {k: sorted(v) for k, v in compile_tasks.items() if len(v) >= min_tasks}}
    for package, tasks in sorted(import_tasks.items(), key=lambda kv: -len(kv[1])):
        if len(tasks) < min_tasks or len(examples) >= max_examples:
            continue
        for s in good:
            app = s["site"] / "src" / "App.vue"
            try:
                text = _strip_style(app.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
            if package in text or not re.search(r"\bv-(if|show)\b", text) or len(lines) > max_lines:
                continue
            examples.append({"kind": "import", "problem": package, "source_task": s["task_id"], "code": text,
                             # The package is not named: naming it (even as a warning) made the generator use it.
                             "text": f"Earlier websites that imported a package missing from package.json showed a "
                                     f"blank page ({len(tasks)} tasks). This App.vue from an earlier website that "
                                     f"worked switches its pages with vue alone:"})
            break
    for key, tasks in sorted(compile_tasks.items(), key=lambda kv: -len(kv[1])):
        if len(tasks) < min_tasks or len(examples) >= max_examples:
            continue
        for s in good:
            snippet = _find_element(s["site"], key)
            if snippet:
                examples.append({"kind": "compile", "problem": key, "source_task": s["task_id"], "code": snippet,
                                 "text": f"Earlier websites failed to compile ({len(tasks)} tasks): "
                                         f"\"{compile_message[key]}\". An earlier website that worked wrote "
                                         f"{key} like this:"})
                break
    info["examples"] = [{k: e[k] for k in ("kind", "problem", "source_task")} for e in examples]
    return examples, info


def _find_element(site: Path, key: str) -> str | None:
    tag, _, kind = key.partition("[type=")
    kind = kind.rstrip("]")
    pattern = re.compile(rf"<{re.escape(tag)}\b[^>]*" + (rf"""type=["']{re.escape(kind)}["']""" if kind else ""), re.I)
    for path in _sources(site):
        if path.suffix != ".vue":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if pattern.search(line):
                handler = re.search(r"@(\w+)=\"(\w+)\"", line)
                block = [line.strip()]
                if handler:  # include the handler's definition so the example is complete
                    for j, other in enumerate(lines):
                        if re.search(rf"\b(const|function)\s+{handler.group(2)}\b", other):
                            block += [x.rstrip() for x in lines[j:j + 6]]
                            break
                return "\n".join(block)
    return None


# ----------------------------------------------------------------------------------------------------------------
# v6: a code pool kept in the memory database (tables code_memories / code_memory_uses), written after each task.
# ----------------------------------------------------------------------------------------------------------------

_VUE_APIS = ("ref", "reactive", "computed", "watch", "watchEffect", "onMounted", "onUnmounted", "onBeforeMount",
             "onBeforeUnmount", "nextTick", "toRef", "toRefs", "provide", "inject", "readonly", "shallowRef")
_SCRIPT = re.compile(r"<script[^>]*>([\s\S]*?)</script>")
_VUE_IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]vue['\"]")


def missing_vue_imports(site: Path) -> list[str]:
    """Vue APIs a file calls without importing them from 'vue' (a runtime ReferenceError: blank page)."""
    found = set()
    for path in _sources(site):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        code = "\n".join(_SCRIPT.findall(text)) if path.suffix == ".vue" else text
        if not code or re.search(r"import\s+\*\s+as\s+\w+\s+from\s+['\"]vue['\"]", code):
            continue
        imported = {n.strip().split(" as ")[-1].strip() for m in _VUE_IMPORT.findall(code) for n in m.split(",")}
        for api in _VUE_APIS:
            if api not in imported and re.search(rf"(?<![\w.]){api}\s*[(<]", code) \
                    and not re.search(rf"(function|const|let|var)\s+{api}\b", code):
                found.add(api)
    return sorted(found)


def normalise_compile_message(message: str) -> str:
    first = message.split("\n")[0]
    first = re.sub(r"(/[^\s:]+)+", "", first)          # paths
    first = re.sub(r"[\"'`][^\"'`]{1,60}[\"'`]", "X", first)  # quoted names
    return re.sub(r"\s+", " ", first).strip()[:160]


def problem_keys(site: Path, facts: dict) -> dict[str, dict]:
    """Breakage of one site, by key: import:<package>, vue-api:<name>, compile:<normalised message>."""
    keys: dict[str, dict] = {}
    for package in facts.get("undeclared") or []:
        keys[f"import:{package}"] = {"what": f"imports {package}, which package.json does not declare"}
    apis = facts.get("missing_vue_api") or []
    if apis:  # one key for every missing Vue import: one example (a whole small component) answers them all
        keys["vue-api:any"] = {"what": "a component calls " + ", ".join(f"{a}()" for a in apis)
                               + " without importing it from 'vue' (that page fails when opened)", "apis": apis}
    for error in facts.get("compile_errors") or []:
        keys.setdefault(f"compile:{normalise_compile_message(error['message'])}",
                        {"what": "Vue compile error: " + error["message"].split("\n")[0][:200],
                         "file": error.get("file"), "line": error.get("line"),
                         "source_line": error.get("source_line", "")})
    return keys


def compile_file_text(text: str, name: str, compiler_project: Path | None) -> list[dict] | None:
    """Compile one .vue text on its own (script and template together); None when no compiler is available."""
    import tempfile
    node = os.environ.get("WEBGEN_NODE") or shutil.which("node")
    fallback = os.environ.get("WEBGEN_VUE_COMPILER_PROJECT")
    for project in (compiler_project, Path(fallback) if fallback else None):
        if project is not None and (project / "node_modules" / "@vue" / "compiler-sfc").is_dir():
            break
    else:
        return None
    if node is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "src").mkdir()
        (Path(tmp) / "src" / name).write_text(text, encoding="utf-8")
        try:
            result = subprocess.run([node, "-e", _COMPILE_JS, tmp, str(project.resolve())], capture_output=True,
                                    text=True, timeout=120)
            return json.loads(result.stdout or "[]") if result.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None


VUE_API_KEY_LINES = os.environ.get("WEBGEN_VUE_API_KEY_LINES") == "1"  # diagnostic switch: short vs whole script
# v8: rebuild the vue-api example when the APIs the chain keeps missing change. v7 built it once (task 6, ref only)
# and never again, while half of its 22 support tasks later missed computed, which the example never showed.
CODE_POOL_REFRESH = os.environ.get("WEBGEN_CODE_POOL_REFRESH") == "1"
REFRESH_MONOTONIC = False  # v9: see _refresh_vue_api
VUE_API_COVER_MAX = 3


def _needed_apis(want: dict[str, int], min_tasks: int = 2) -> list[str]:
    """The Vue APIs the example must show: missed in >= min_tasks failing tasks, most-missed first (at least one)."""
    ranked = sorted(want, key=lambda a: (-want[a], a))
    return [a for a in ranked if want[a] >= min_tasks][:VUE_API_COVER_MAX] or ranked[:1]


def _imported_in(code: str) -> set[str]:
    return {a for line in _VUE_IMPORT.findall(code) for a in re.findall(r"\w+", line)}


def _key_lines(script: str) -> str:
    """The vue import line plus the first statement using each imported API, copied verbatim (no business
    code around them): what the generator lacked, without a whole component it might copy."""
    lines = script.splitlines()
    imp = next((l for l in lines if _VUE_IMPORT.search(l)), "")
    names = re.findall(r"\w+", (_VUE_IMPORT.search(imp) or [None, ""])[1]) if imp else []
    out = ["<script setup lang=\"ts\">", imp.strip(), ""]
    for a in names:
        i = next((i for i, l in enumerate(lines) if re.search(rf"(?<![\w.]){a}\s*[(<]", l) and "import" not in l), None)
        if i is None:
            continue
        block = [lines[i].rstrip()]
        depth = lines[i].count("(") + lines[i].count("{") - lines[i].count(")") - lines[i].count("}")
        j = i + 1
        while depth > 0 and j < len(lines) and len(block) < 4:
            block.append(lines[j].rstrip()); depth += lines[j].count("(") + lines[j].count("{") - lines[j].count(")") - lines[j].count("}"); j += 1
        out += block
    return "\n".join(out + ["</script>"])


def _fix_from_good_site(key: str, good: list[dict], max_lines: int,
                        want: dict[str, int] | None = None, prefer: set[str] | None = None) -> tuple[str, str] | None:
    """``want``: how many failing tasks missed each Vue API (vue-api:any); the example should import the ones
    missed most, otherwise it shows nothing the generator lacked."""
    kind, _, detail = key.partition(":")
    if kind == "vue-api" and detail == "any":
        best = None
        for s in good:
            for path in _sources(s["site"]):
                if path.suffix != ".vue" or path.name in ("App.vue", "HelloWorld.vue"):  # HelloWorld = scaffold
                    continue
                try:
                    full = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                m = re.search(r"<script[^>]*>.*?</script>", full, re.S)  # the import lesson lives in the script
                if not m:
                    continue
                text = m.group(0)
                imported = {a for line in _VUE_IMPORT.findall(text) for a in re.findall(r"\w+", line)}
                used = {a for a in _VUE_APIS if re.search(rf"(?<![\w.]){a}\s*[(<]", text)} & imported
                n = len(text.splitlines())
                need = set(_needed_apis(want)) if (CODE_POOL_REFRESH and want) else set()
                rank = (len(need & used), len((prefer or set()) & used), sum((want or {}).get(a, 0) for a in used), len(used), -n)
                if used and n <= 40 and (best is None or rank > best[0]):
                    best = (rank, text, s["task_id"])
        if not best:
            return None
        return (_key_lines(best[1]) if VUE_API_KEY_LINES else best[1]), best[2]
    for s in good:
        site = s["site"]
        if kind == "import":
            try:
                text = _strip_style((site / "src" / "App.vue").read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if detail not in text and re.search(r"\bv-(if|show)\b", text) and len(text.splitlines()) <= max_lines:
                return text, s["task_id"]
        elif kind == "vue-api" and detail == "any":
            best = None
            for path in _sources(site):
                if path.suffix != ".vue" or path.name in ("App.vue", "HelloWorld.vue"):  # HelloWorld = template scaffold
                    continue
                try:
                    text = _strip_style(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    continue
                imports = _VUE_IMPORT.findall(text)
                used = {a for a in _VUE_APIS if re.search(rf"(?<![\w.]){a}\s*[(<]", text)}
                n = len(text.splitlines())
                if imports and used and n <= 40 and (best is None or (len(used), -n) > best[0]):
                    best = ((len(used), -n), text)
            if best:
                return best[1], s["task_id"]
        elif kind == "vue-api":
            for path in _sources(site):
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                lines = text.splitlines()
                imp = next((l for l in lines if _VUE_IMPORT.search(l) and re.search(rf"\b{detail}\b", l)), None)
                use = next((i for i, l in enumerate(lines) if re.search(rf"(?<![\w.]){detail}\s*[(<]", l)
                            and "import" not in l), None)
                if imp and use is not None:
                    return "\n".join([imp.strip(), "", *[l.rstrip() for l in lines[use:use + 4]]]), s["task_id"]
    return None


REPAIR_INSTRUCTIONS = (
    "A Vue single-file component from an earlier generated website does not compile. Fix only what the compiler "
    "error is about; keep everything else as it is. Return JSON {\"file\": <the whole corrected file>, "
    "\"snippet\": <the corrected lines only, at most 12 lines, copied exactly from your corrected file>}.")
DESCRIBE_INSTRUCTIONS = (
    "You maintain a library of code that earlier websites needed. Given the breakage it prevents and the code, "
    "write a short name (start with the symptom, e.g. \"Blank page: ...\") and the condition under which a NEW "
    "website needs this code, stated in terms of what the website requirement asks for (e.g. \"the requirement "
    "has several pages or sections to switch between\"), not in terms of the bug. Return JSON "
    "{\"name\": str, \"applies_when\": str}. Never name the missing package or library in either field "
    "(naming it makes the code model use it).")
APPLICABILITY_INSTRUCTIONS = (
    "For each code entry, decide from the website requirement alone whether the new website meets the entry's "
    "condition (applies_when). Return JSON {\"decisions\": [{\"code_id\": str, \"applies\": true|false, "
    "\"reason\": str}]} with one decision per entry.")


KEY_LINES_INSTRUCTIONS = (
    "Earlier websites broke as described. Below is a working component from another earlier website. Copy out "
    "only the lines that show how to avoid this breakage (the lines a code model must imitate), as few as "
    "needed. Copy each line exactly as it appears; do not change, add or summarise anything. Return JSON "
    "{\"lines\": [str, ...]}.")
KEY_LINES_MAX = 15


def _pick_fragment(llm, code: str, breakage: str, attempts: int = 2) -> dict:
    """Same idea as _pick_key_lines for a whole good file (e.g. App.vue for a missing package): the model
    copies only the lines that show how the earlier websites avoided the breakage; code checks they are
    verbatim, at most KEY_LINES_MAX, and not a whole file (no <script>/<template> wrapper lines). A whole
    App.vue from another website read as a finished file and the generator left the scaffold untouched
    (v7 000001/000011). Returns {"code": None} when no valid pick is made (the caller keeps no fragment)."""
    source = {l.strip() for l in code.splitlines() if l.strip()}
    log, feedback = [], ""
    for _ in range(attempts):
        try:
            out = llm.generate("code_memory_key_lines", {"instructions": KEY_LINES_INSTRUCTIONS + feedback,
                                                         "breakage": breakage, "code": code})
        except Exception as error:  # noqa: BLE001
            log.append({"error": str(error)[:200]}); break
        raw = out.get("lines") if isinstance(out, dict) else None
        raw = [raw] if isinstance(raw, str) else (raw or [])
        lines = [part.rstrip() for l in raw for part in str(l).splitlines()]  # one string holding many lines
        lines = [l for l in lines if l.strip()]
        problems = [f"not in the source: {l.strip()[:60]}" for l in lines if l.strip() not in source]
        if any(re.match(r"\s*</?(script|template|style)\b", l) for l in lines):
            problems.append("leave out the <script>/<template> tag lines; give only the lines inside them")
        if not lines or len(lines) > KEY_LINES_MAX:
            problems.append(f"give 1-{KEY_LINES_MAX} lines")
        m = re.search(r"<template>(.*)</template>", code, re.S)
        markup = {l.strip() for l in m.group(1).splitlines() if l.strip()} if m else set()
        if markup and not any(l.strip() in markup for l in lines):
            problems.append("include the template lines that show how it works, not only the script lines")
        log.append({"lines": len(lines), "problems": problems})
        if not problems:
            return {"code": "\n".join(lines), "log": log}
        feedback = " Previous answer rejected: " + "; ".join(problems[:5]) + "."
    # Rule fallback: the file's own lines minus the wrapper tags, imports of the site's own files and bare
    # closing tags, verbatim. Still not a whole file, still the mechanism (state + markup that uses it).
    keep = [l.rstrip() for l in code.splitlines() if l.strip()
            and not re.match(r"\s*</?(script|template|style)\b", l)
            and not re.match(r"\s*import\s+\w+\s+from\s+['\"]\./", l)
            and not re.match(r"\s*</\w+>\s*$", l)]
    if 0 < len(keep) <= 2 * KEY_LINES_MAX:
        log.append({"fallback": "rule", "lines": len(keep)})
        return {"code": "\n".join(keep), "log": log}
    log.append({"fallback": "none", "lines": len(keep)})
    return {"code": None, "log": log}


def _pick_key_lines(llm, script: str, breakage: str, want: dict[str, int], attempts: int = 2) -> dict:
    """The memory model picks the key lines once, when the code memory is written; code checks them
    (verbatim in the source, keep the vue import with the most-missed API, at most KEY_LINES_MAX lines).
    Falls back to the rule extraction (_key_lines) when the model's pick fails the checks."""
    source = {l.strip() for l in script.splitlines() if l.strip()}
    top = max(want, key=want.get) if want else None
    need = [a for a in _needed_apis(want) if re.search(rf"(?<![\w.]){a}\s*[(<]", script)] if (CODE_POOL_REFRESH and want) else []
    log, feedback = [], ""
    for _ in range(attempts):
        try:
            out = llm.generate("code_memory_key_lines", {"instructions": KEY_LINES_INSTRUCTIONS + feedback,
                                                         "breakage": breakage, "code": script})
        except Exception as error:  # noqa: BLE001 - fall back to the rule extraction
            log.append({"error": str(error)[:200]}); break
        lines = [str(l).rstrip() for l in (out.get("lines") or [])] if isinstance(out, dict) else []
        lines = [l for l in lines if l.strip()]
        problems = [f"not in the source: {l.strip()[:60]}" for l in lines if l.strip() not in source]
        imp = next((l for l in lines if _VUE_IMPORT.search(l)), None)
        if imp is None or (top and not re.search(rf"\b{top}\b", imp)):
            problems.append(f"must include the import line from 'vue' with {top}")
        # An import line alone reads as a finished, empty component: the generator copied it and left the
        # scaffold untouched (v6 000020/000026). Show the imported function in use as well.
        if top and not any(re.search(rf"(?<![\w.]){top}\s*[(<]", l) and l is not imp for l in lines):
            problems.append(f"must also include a line that calls {top}(...)")
        for api in need:  # v8: every API the chain keeps missing, imported and used
            if api != top and not (imp and re.search(rf"\b{api}\b", imp)):
                problems.append(f"the import line from 'vue' must also include {api}")
            if api != top and not any(re.search(rf"(?<![\w.]){api}\s*[(<]", l) and l is not imp for l in lines):
                problems.append(f"must also include a line that calls {api}(...)")
        if not lines or len(lines) > KEY_LINES_MAX:
            problems.append(f"give 1-{KEY_LINES_MAX} lines")
        log.append({"lines": len(lines), "problems": problems})
        if not problems:
            # Lines only, no <script> wrapper: a whole tiny file reads as the finished component.
            return {"code": "\n".join(lines), "log": log}
        feedback = " Previous answer rejected: " + "; ".join(problems[:5]) + "."
    log.append({"fallback": "rule"})
    if not CODE_POOL_REFRESH:  # v7 behaviour, unchanged
        return {"code": _key_lines(script), "log": log}
    # v8: lines only here as well: a <script> wrapper made the example read as a finished component (v6).
    return {"code": "\n".join(l for l in _key_lines(script).splitlines() if not re.match(r"\s*</?script\b", l)),
            "log": log}


def _repair_with_model(llm, failing: dict, problem: dict, compiler_project: Path | None,
                       attempts: int = 2) -> tuple[str, str] | None:
    """The memory model rewrites the broken file; accepted only when the compiler reports no error (a loop with a
    code-checked criterion, at most ``attempts`` rounds)."""
    path = failing["site"] / str(problem.get("file") or "")
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    request = {"instructions": REPAIR_INSTRUCTIONS, "compiler_error": problem["what"], "file_name": path.name,
               "file": original}
    for _ in range(attempts):
        result = llm.generate("code_memory_repair", request)
        fixed = str(result.get("file", "")) if isinstance(result, dict) else ""
        snippet = str(result.get("snippet", "")).strip() if isinstance(result, dict) else ""
        errors = compile_file_text(fixed, path.name, failing["site"]) if fixed else None
        if errors == [] and snippet and all(line.strip() in fixed for line in snippet.splitlines() if line.strip()):
            return snippet, failing["task_id"]
        request = {**request, "retry_notice": "Your file still does not compile or the snippet is not in it: "
                   + json.dumps(errors)[:600]}
    return None


def _api_snippet(good: list[dict], api: str, max_lines: int = 6) -> tuple[str, str] | None:
    """Verbatim lines from the shortest good-site component that imports ``api`` from 'vue' and calls it: its
    vue import line plus the first statement calling it (up to max_lines - 1 lines)."""
    best = None
    for s in good:
        for path in _sources(s["site"]):
            if path.suffix != ".vue" or path.name in ("App.vue", "HelloWorld.vue"):
                continue
            try:
                m = re.search(r"<script[^>]*>(.*?)</script>", path.read_text(encoding="utf-8"), re.S)
            except (OSError, UnicodeDecodeError):
                continue
            if not m or api not in _imported_in(m.group(1)):
                continue
            lines = m.group(1).splitlines()
            imp = next((l.strip() for l in lines if _VUE_IMPORT.search(l) and re.search(rf"\b{api}\b", l)), None)
            i = next((i for i, l in enumerate(lines) if re.search(rf"(?<![\w.]){api}\s*[(<]", l) and "import" not in l), None)
            if imp is None or i is None:
                continue
            block, depth, j = [lines[i].rstrip()], 0, i
            depth = lines[i].count("(") + lines[i].count("{") - lines[i].count(")") - lines[i].count("}")
            while depth > 0 and j + 1 < len(lines) and len(block) < max_lines - 1:
                j += 1; block.append(lines[j].rstrip())
                depth += lines[j].count("(") + lines[j].count("{") - lines[j].count(")") - lines[j].count("}")
            if depth > 0:
                continue  # the statement does not close within the limit: not a usable snippet
            if best is None or len(block) < len(best[0]) - 1:
                best = ([imp, *block], s["task_id"])
    return ("\n".join(best[0]), best[1]) if best else None


def _vue_api_explanation(what: str, n_tasks: int) -> str:
    return f"Earlier websites broke here ({what}, {n_tasks} tasks). Code that works:"


def _refresh_vue_api(connection, llm, code_id: str, where: list[dict], good: list[dict], max_lines: int,
                     want: dict[str, int], tasks: list[str], info: dict, current_task: str | None = None) -> None:
    """v8: when the stored example no longer imports every API the chain keeps missing, pick a new one from the
    current good sites (same checks as at creation). The count in the explanation follows the support (updated in
    place). A new example is a new version: a new row (new code_id, so its uses and utility start fresh) and the
    old row is marked 'superseded' with superseded_by / superseded_at_task; retrieval reads only active rows."""
    row = connection.execute("SELECT code, explanation FROM code_memories WHERE code_id=?", (code_id,)).fetchone()
    need = _needed_apis(want)
    what = "a component calls " + ", ".join(f"{a}()" for a in need) + " without importing it from 'vue' (that page fails when opened)"
    explanation = _vue_api_explanation(what, len(tasks))
    if set(need) <= _imported_in(row[0]):
        if row[1] != explanation:
            connection.execute("UPDATE code_memories SET explanation=? WHERE code_id=?", (explanation, code_id))
        return
    # Prefer a component that uses the needed APIs the stored example lacks (a ref-only one ties otherwise).
    fix = _fix_from_good_site("vue-api:any", good, max_lines, want, prefer=set(need) - _imported_in(row[0]))
    if fix is None:
        info.setdefault("refresh", []).append({"key": "vue-api:any", "need": need, "result": "no good site"})
        return
    picked = _pick_key_lines(llm, fix[0], what, want)
    code, source_task = picked["code"], fix[1]
    if not set(need) <= _imported_in(code):
        # No single small working component uses all of them: one verbatim snippet per API, each from its own
        # site (two import lines from 'vue' are valid and each stays exactly as written there).
        parts = [_api_snippet(good, api) for api in need]
        if all(parts) and sum(len(p[0].splitlines()) for p in parts) <= KEY_LINES_MAX:
            code = "\n\n".join(p[0] for p in parts)
            source_task = ",".join(dict.fromkeys(p[1] for p in parts))
            picked["log"].append({"composed": [p[1] for p in parts]})
    covered = set(need) & _imported_in(code)
    old_covered = set(need) & _imported_in(row[0])
    # v8 replaced the example whenever the new one covered any function the old one lacked, so a ref-only and a
    # computed-only example kept replacing each other (seed 11, tasks 26-33). v9 replaces only on a strict gain.
    if (not covered > old_covered) if REFRESH_MONOTONIC else (not covered - _imported_in(row[0])):
        info.setdefault("refresh", []).append({"key": "vue-api:any", "need": need, "result": "no better example",
                                               "log": picked["log"]})
        return
    new_id = uuid.uuid4().hex
    connection.execute(
        "INSERT INTO code_memories (code_id,agent_id,problem_key,name,applies_when,explanation,code,source,"
        "source_task_id,support_tasks,status) SELECT ?,agent_id,problem_key,name,applies_when,?,?,source,?,"
        "support_tasks,status FROM code_memories WHERE code_id=?", (new_id, explanation, code, source_task, code_id))
    connection.execute("UPDATE code_memories SET status='superseded', superseded_by=?, superseded_at_task=? "
                       "WHERE code_id=?", (new_id, current_task, code_id))
    info.setdefault("refresh", []).append({"key": "vue-api:any", "need": need, "old_code_id": code_id,
                                           "new_code_id": new_id, "old_code": row[0], "new_code": code,
                                           "source_task": source_task, "log": picked["log"]})


def update_code_pool(connection, agent_id: str, llm, chain: list[dict], repo_root: Path, *, min_tasks: int = 2,
                     min_score: float = 0.5, max_lines: int = 40, current_task: str | None = None,
                     scan_seconds: float = 600, min_tasks_site_break: int = 0) -> dict:
    """After a task: refresh site facts, add a code memory for every breakage seen in >= min_tasks tasks of this
    chain that has none yet, extend support of existing ones, and mark whether the current task's injected code
    memories' breakage came back. ``chain``: [{task_id, trace_path, score}] for every task run so far."""
    sites, started = [], time.monotonic()
    for item in chain:
        if time.monotonic() - started > scan_seconds and item.get("task_id") != current_task:
            continue  # never hold a task up for long; the rest are cached on later tasks
        site = site_root(str(item["trace_path"]), repo_root)
        if site is not None:
            facts = site_facts(site)
            sites.append({**item, "site": site, "facts": facts, "keys": problem_keys(site, facts)})
    seen: dict[str, list[dict]] = {}
    for s in sites:
        for key in s["keys"]:
            seen.setdefault(key, []).append(s)
    good = sorted((s for s in sites if s["score"] >= min_score and not s["keys"]
                   and s["facts"]["compile_errors"] == []), key=lambda s: -s["score"])
    info: dict = {"sites": len(sites), "good_sites": len(good), "added": [], "supported": [], "no_fix": []}
    existing = {row[0]: row[1] for row in connection.execute(
        "SELECT problem_key, code_id FROM code_memories WHERE agent_id=? AND status!='superseded'", (agent_id,))}
    for key, where in seen.items():
        tasks = sorted({s["task_id"] for s in where})
        want: dict[str, int] = {}
        for s in where:
            for a in s["facts"].get("missing_vue_api") or []:
                want[a] = want.get(a, 0) + 1
        if key in existing:
            connection.execute("UPDATE code_memories SET support_tasks=? WHERE code_id=?",
                               (json.dumps(tasks), existing[key]))
            info["supported"].append(key)
            if CODE_POOL_REFRESH and key == "vue-api:any":
                _refresh_vue_api(connection, llm, existing[key], where, good, max_lines, want, tasks, info,
                                 current_task)
            continue
        if len(tasks) < ((min_tasks_site_break or min_tasks) if severity(key) == 2 else min_tasks):
            continue
        fix = _fix_from_good_site(key, good, max_lines, want)
        source = "good_site"
        if fix is not None and key.startswith("import:") and CODE_POOL_REFRESH:  # v8 only; v7 kept the whole file
            picked = _pick_fragment(llm, fix[0], "earlier websites imported a package that package.json does not "
                                    "declare, so the whole site showed a blank page; the working file below does the "
                                    "same job using only what is installed")
            info.setdefault("key_lines", {})[key] = picked["log"]
            fix = (picked["code"], fix[1]) if picked["code"] else None
        if fix is not None and key == "vue-api:any" and not VUE_API_KEY_LINES:
            picked = _pick_key_lines(llm, fix[0], where[-1]["keys"][key]["what"], want)
            info.setdefault("key_lines", {})[key] = picked["log"]
            if picked["code"]:
                fix = (picked["code"], fix[1])
        if fix is None and key.startswith("compile:"):
            fix, source = _repair_with_model(llm, where[-1], where[-1]["keys"][key], where[-1]["site"]), "model_repair"
            if fix is not None and min_tasks_site_break:
                # v9: a repair that is only a file wrapper (e.g. "<script setup> / import / </script>" for a missing
                # end tag) teaches nothing and reads as a finished empty component (the v6 scaffold failure).
                body = [l for l in fix[0].splitlines() if l.strip() and not re.match(r"\s*</?(script|template|style)\b", l)
                        and not re.match(r"\s*import\s", l)]
                if len(body) < 2:
                    info.setdefault("rejected", []).append({"key": key, "reason": "repair is only a wrapper"})
                    fix = None
        if fix is None:
            info["no_fix"].append(key)
            continue
        code, source_task = fix
        what = where[-1]["keys"][key]["what"]
        package = key.partition(":")[2] if key.startswith("import:") else None
        breakage = "imports a package that package.json does not declare" if package else what
        name = applies = ""
        for _ in range(2):  # code check: the package is never named (one rewrite)
            described = llm.generate("code_memory_describe", {"instructions": DESCRIBE_INSTRUCTIONS,
                                                              "breakage": breakage, "code": code})
            name = str(described.get("name", "")).strip() if isinstance(described, dict) else ""
            applies = str(described.get("applies_when", "")).strip() if isinstance(described, dict) else ""
            stem = package.split("/")[-1].split("-")[-1].lower() if package else None
            if not (package and (package.lower() in (name + applies).lower()
                                 or (stem and len(stem) > 3 and stem in (name + applies).lower()))):
                break
            name = applies = ""
        if not name or not applies:
            info["no_fix"].append(key)
            continue
        # The explanation names the symptom, not the package (naming it made the generator use it).
        explanation = ("Earlier websites broke here (" + ("a package missing from package.json" if
                       key.startswith("import:") else what) + f", {len(tasks)} tasks). Code that works:")
        code_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO code_memories (code_id,agent_id,problem_key,name,applies_when,explanation,code,source,"
            "source_task_id,support_tasks) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (code_id, agent_id, key, name, applies, explanation, code, source, source_task, json.dumps(tasks)))
        info["added"].append({"code_id": code_id, "key": key, "source": source, "source_task": source_task})
    if current_task:
        # The site of a failed generation may not exist: its injected code did not prevent the failure.
        current = next((s for s in sites if s["task_id"] == current_task), None)
        for code_id, key in connection.execute(
                "SELECT u.code_id, m.problem_key FROM code_memory_uses u JOIN code_memories m "
                "ON m.code_id=u.code_id WHERE u.agent_id=? AND u.task_id=?", (agent_id, current_task)).fetchall():
            recurred = 1 if current is None else int(key in current["keys"])
            connection.execute("UPDATE code_memory_uses SET recurred=? WHERE agent_id=? AND task_id=? AND code_id=?",
                               (recurred, agent_id, current_task, code_id))
    connection.commit()
    return info


def severity(problem_key: str) -> int:
    """2 = the whole site does not start (missing package, compile error); 1 = one page fails (missing import)."""
    return 2 if problem_key.startswith(("import:", "compile:")) else 1


def code_utility(connection, agent_id: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for code_id, recurred in connection.execute(
            "SELECT code_id, recurred FROM code_memory_uses WHERE agent_id=? AND recurred IS NOT NULL", (agent_id,)):
        entry = stats.setdefault(code_id, {"uses": 0, "recurred": 0})
        entry["uses"] += 1
        entry["recurred"] += recurred
    for entry in stats.values():
        entry["utility"] = (entry["uses"] - entry["recurred"] + 1) / (entry["uses"] + 2)
    return stats
