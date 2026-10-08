#!/bin/bash
# Code memory (v6): node and a project with @vue/compiler-sfc for the compile checks.
export WEBGEN_NODE=${WEBGEN_NODE:-/data/qma258/opt/node/bin/node}
export WEBGEN_VUE_COMPILER_PROJECT=${WEBGEN_VUE_COMPILER_PROJECT:-/data/qma258/opt/vue-compiler}
# Helpers for worker queue items (source it at the top of an item). Items run from $WG/webgen with the
# worker's environment ($py, $memory_config, $WEBGEN_BOLT_URL and the shifted model URLs).

# run_longmem_tasks OUTPUT TASK_ID...: Long Memory (continual, post-task reflection, case_only) on the
# given tasks in order, each followed by the health check; a failed task is logged and the next one runs.
run_longmem_tasks() {
  local out="$1"; shift
  local id start
  for id in "$@"; do
    start=$(date +%s)
    echo "=== Long Memory $id -> $out"
    "$py" scripts/run_continual_memory.py --modes continual --post-task-reflection \
      --memory-representation case_only --memory-config "$memory_config" \
      --url "$WEBGEN_BOLT_URL" --generator-model WebGen-LM-7B \
      --output "$out" --database "$out/memory.db" --task-ids "$id" 2>&1 | tee -a "$out/runner-$id.log"
    echo "Long Memory $id exit ${PIPESTATUS[0]} after $(( $(date +%s) - start ))s"
    "$py" scripts/cluster/check_task_health.py "$out" "$id" continual
  done
}

# manifest_ids [FROM [COUNT]]: task ids in manifest order (0-based position).
manifest_ids() {
  "$py" -c "
import json
m = json.load(open('data/experiment_splits/continual_domain_blocks/manifest.json'))
ids = [t for b in m['batches'] for t in b['task_ids']]
start, count = int('${1:-0}'), int('${2:-0}') or len(ids)
print(' '.join(ids[start:start + count]))"
}

# key_file VAR: write the API key held in VAR to a private temporary file and print its path.
key_file() {
  local f; f=$(mktemp "$WG/tmp/key.XXXXXX"); chmod 600 "$f"; printf '%s' "${!1}" > "$f"; echo "$f"
}

# run_nomem_tasks OUTPUT TASK_ID...: No Memory (disabled) on the given tasks, each with the health check.
run_nomem_tasks() {
  local out="$1"; shift
  local id start
  for id in "$@"; do
    start=$(date +%s)
    echo "=== No Memory $id -> $out"
    "$py" scripts/run_continual_memory.py --modes disabled --memory-config "$memory_config" \
      --url "$WEBGEN_BOLT_URL" --generator-model WebGen-LM-7B \
      --output "$out" --database "$out/memory.db" --task-ids "$id"
    local status=$?
    echo "No Memory $id exit $status after $(( $(date +%s) - start ))s"
    "$py" scripts/cluster/check_task_health.py "$out" "$id" disabled
    return $status
  done
}

# filler_next: the next unfinished "ARM OUTPUT TASK_ID CONFIG" from $WG/queue/filler.conf (lines
# "L|N OUTPUT [MEMORY_CONFIG]", CONFIG "-" = the worker default;
# done in order), skipping tasks whose runner already failed three times; nothing (exit 1) when all are done.
filler_next() {
  "$py" - "$WG/queue/filler.conf" "$WG/queue/filler-failures.txt" <<'PY'
import json, sys
from pathlib import Path
conf, failures = Path(sys.argv[1]), Path(sys.argv[2])
m = json.load(open("data/experiment_splits/continual_domain_blocks/manifest.json"))
ids = [t for b in m["batches"] for t in b["task_ids"]]
failed = failures.read_text().split("\n") if failures.is_file() else []
for line in conf.read_text().splitlines() if conf.is_file() else []:
    if not line.strip() or line.startswith("#"):
        continue
    arm, out = line.split()[:2]
    cfg = line.split()[2] if len(line.split()) > 2 else "-"
    mode = "continual" if arm == "L" else "disabled"
    progress = Path(out) / "progress.jsonl"
    done = {json.loads(r)["task_id"] for r in progress.read_text().splitlines() if r.strip()
            and json.loads(r).get("mode") == mode} if progress.is_file() else set()
    for task in ids:
        if task not in done and failed.count(f"{out} {task}") < 3:
            print(arm, out, task, cfg); sys.exit(0)
sys.exit(1)
PY
}
