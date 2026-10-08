"""Copy the analysis-relevant files of finished cluster runs into archive/phase2-webgen-2026-10/<run>/ for git.

Kept per run: progress.jsonl, continual-report.json, run-metadata.json, task-order.json, memory.db, the gzipped
memory-events.jsonl and post-task-reflections.jsonl, and every task's submitted prompt (prompts/<task>.txt).
Generated sites, screenshots and evaluator transcripts stay out of git (they are in outputs/experiment/, local).

    python3 scripts/archive_phase2_runs.py cluster_longmem_v7_webgenlm7b_r1 [more runs...]
"""
import gzip
import shutil
import sys
from pathlib import Path

SRC = Path("outputs/experiment")
DST = Path("archive/phase2-webgen-2026-10")
PLAIN = ("progress.jsonl", "continual-report.json", "run-metadata.json", "task-order.json", "memory.db")
GZIP = ("memory-events.jsonl", "post-task-reflections.jsonl")


def archive(run: str) -> None:
    src, dst = SRC / run, DST / run
    if not (src / "progress.jsonl").is_file():
        raise SystemExit(f"{src}: no progress.jsonl")
    dst.mkdir(parents=True, exist_ok=True)
    for name in PLAIN:
        if (src / name).is_file():
            shutil.copy2(src / name, dst / name)
    for name in GZIP:
        if (src / name).is_file():
            with open(src / name, "rb") as f, open(dst / f"{name}.gz", "wb") as raw, \
                    gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as g:  # mtime 0: same bytes on a rerun
                shutil.copyfileobj(f, g)
    prompts = dst / "prompts"
    for p in sorted(src.glob("tasks/*/*/000001.prompt.txt")):
        prompts.mkdir(exist_ok=True)
        shutil.copy2(p, prompts / f"{p.parts[-3]}.txt")
    size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
    print(f"{run}: {size / 1e6:.1f} MB, {len(list(prompts.glob('*.txt'))) if prompts.exists() else 0} prompts")


if __name__ == "__main__":
    for run in sys.argv[1:]:
        archive(run)
