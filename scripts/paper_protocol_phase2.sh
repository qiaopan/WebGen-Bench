#!/bin/zsh
# Mac Q8_0 paper protocol -- phase 2: remaining 90 tasks (000029 onward, in
# the manifest's domain-block order, not numeric task-ID order), with No
# Memory and Long Memory run back-to-back per task. Which arm goes first
# ALTERNATES every task (000029: No Memory then Long Memory; 000030: Long
# Memory then No Memory; 000031: back to No Memory first; ...) so a fixed
# ordering never systematically advantages one arm (e.g. via warm shared
# Bolt/Chrome state or GPU warm-up).
#
# Must only be run after scripts/paper_protocol_catchup.sh has completed,
# so both arms already share the same 11-task coverage (000014-000021 +
# 000026-000028). Safe to re-run: run_continual_memory.py skips task IDs
# already marked complete in progress.jsonl, so nothing is duplicated.
#
# See docs/agent-memory/DECISIONS.md, "2026-09-30: Mac Q8_0 profile 正式升级为论文协议".
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
cd "$project_root"

nomem_output="outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2"
nomem_db="$nomem_output/memory.db"
longmem_output="outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1"
longmem_db="$longmem_output/memory.db"
bolt_port="${WEBGEN_BOLT_PORT:-5186}"
bolt_url="${WEBGEN_BOLT_URL:-http://127.0.0.1:${bolt_port}/}"
log="outputs/experiment/paper_protocol_phase2.log"

mkdir -p outputs/experiment
touch "$log"

print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Preflight: verifying all five model roles." | tee -a "$log"
env/webvoyager/bin/python3.10 scripts/preflight_reflective_models.py |& tee -a "$log"

bolt_pid=""
if lsof -nP -iTCP:"$bolt_port" -sTCP:LISTEN >/dev/null 2>&1; then
  print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Reusing existing Bolt listener on $bolt_port." | tee -a "$log"
else
  "$script_dir/start_bolt_provider.sh" --provider local --port "$bolt_port" >>"$log" 2>&1 &
  bolt_pid=$!
fi
cleanup() { [[ -n "$bolt_pid" ]] && kill -TERM "$bolt_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  curl --fail --silent --show-error --max-time 5 "${bolt_url}api/health" >/dev/null && break
  sleep 1
done
curl --fail --silent --show-error --max-time 5 "${bolt_url}api/health" >/dev/null || {
  print "Bolt health check failed." >&2
  tail -80 "$log" >&2
  exit 1
}

export WEBGEN_GENERATION_TIMEOUT_SECONDS="${WEBGEN_GENERATION_TIMEOUT_SECONDS:-2700}"
export WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-1}"

run_nomem_task() {
  local task_id="$1"
  print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] No Memory: starting $task_id" | tee -a "$log"
  PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
    --modes disabled \
    --url "$bolt_url" \
    --generator-model "${WEBGEN_GENERATOR_API_MODEL:-WebGen-LM-7B}" \
    --output "$nomem_output" \
    --database "$nomem_db" \
    --task-ids "$task_id" 2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
      printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
    done | tee -a "$log"
}

run_longmem_task() {
  local task_id="$1"
  print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Long Memory: starting $task_id" | tee -a "$log"
  PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
    --modes continual \
    --post-task-reflection \
    --memory-representation case_only --memory-config config/long_memory_condensed.json \
    --url "$bolt_url" \
    --generator-model "${WEBGEN_GENERATOR_API_MODEL:-WebGen-LM-7B}" \
    --output "$longmem_output" \
    --database "$longmem_db" \
    --task-ids "$task_id" 2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
      printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
    done | tee -a "$log"
}

# Manifest order (domain-block insertion order, not numeric task-ID order),
# restricted to task 000029 onward.
remaining_task_ids="$(env/webvoyager/bin/python3.10 -c '
import json
from pathlib import Path
manifest = json.loads(Path("data/experiment_splits/continual_domain_blocks/manifest.json").read_text())
ids = [t for block in manifest["batches"] for t in block["task_ids"]]
start = ids.index("000029")
print(",".join(ids[start:]))
')"

batch_size="${WEBGEN_PHASE2_BATCH_SIZE:-10}"
batch_task_ids=()

first_is_nomem=1
i=0
for task_id in ${(s:,:)remaining_task_ids}; do
  i=$((i + 1))
  if (( first_is_nomem )); then
    print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Task $i/90: $task_id -- No Memory first, then Long Memory" | tee -a "$log"
    run_nomem_task "$task_id"
    run_longmem_task "$task_id"
  else
    print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Task $i/90: $task_id -- Long Memory first, then No Memory" | tee -a "$log"
    run_longmem_task "$task_id"
    run_nomem_task "$task_id"
  fi
  first_is_nomem=$((1 - first_is_nomem))
  batch_task_ids+=("$task_id")

  # Emit a checkpoint scorecard every batch_size tasks (default 10, i.e. 9
  # checkpoints across the 90 remaining tasks) so progress can be inspected
  # incrementally instead of only after all 90 finish.
  if (( i % batch_size == 0 )); then
    batch_number=$(( i / batch_size ))
    joined_ids="${(j:,:)batch_task_ids}"
    print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] BATCH $batch_number CHECKPOINT: tasks $joined_ids" | tee -a "$log"
    env/webvoyager/bin/python3.10 scripts/generate_scorecard.py \
      --nomem-progress "$nomem_output/progress.jsonl" \
      --longmem-progress "$longmem_output/progress.jsonl" \
      --task-ids "$joined_ids" \
      --out "outputs/experiment/scorecard_phase2_batch${batch_number}.md" | tee -a "$log"
    batch_task_ids=()
  fi
done

print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Phase 2 complete: all 101 manifest tasks covered by both arms." | tee -a "$log"
