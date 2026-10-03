#!/bin/zsh
# Mac Q8_0 paper protocol -- catch-up phase.
# Brings No Memory and Long Memory to the same 11-task coverage
# (000014-000021 + 000026-000028) before the alternating phase-2 run
# (scripts/paper_protocol_phase2.sh) continues from 000029.
#
# No Memory is missing 000026/000027/000028 (never touched domain block 2).
# Long Memory is missing 000016/000017/000018 (block 1 was run out of order:
# 000019,020,021,014,015 then block 2's 026,027,028). This is safe under the
# project's leave-one-task-out retrieval policy: running 016-018 now, after
# 019-021/026-028 are already in the DB, does not invalidate anything.
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
log="outputs/experiment/paper_protocol_catchup.log"

mkdir -p outputs/experiment
: > "$log"

print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Preflight: verifying all five model roles (generator/memory/functional-eval/appearance-eval/embedding)." | tee -a "$log"
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
    --memory-representation case_only \
    --url "$bolt_url" \
    --generator-model "${WEBGEN_GENERATOR_API_MODEL:-WebGen-LM-7B}" \
    --output "$longmem_output" \
    --database "$longmem_db" \
    --task-ids "$task_id" 2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
      printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
    done | tee -a "$log"
}

for t in 000026 000027 000028; do
  run_nomem_task "$t"
done

for t in 000016 000017 000018; do
  run_longmem_task "$t"
done

print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Catch-up complete. Generating shared-task scorecard." | tee -a "$log"
env/webvoyager/bin/python3.10 scripts/generate_scorecard.py \
  --nomem-progress "$nomem_output/progress.jsonl" \
  --longmem-progress "$longmem_output/progress.jsonl" \
  --task-ids 000014,000015,000016,000017,000018,000019,000020,000021,000026,000027,000028 \
  --out outputs/experiment/scorecard_catchup_11tasks.md | tee -a "$log"

print "[$(date '+%Y-%m-%dT%H:%M:%S%z')] Wrote outputs/experiment/scorecard_catchup_11tasks.md" | tee -a "$log"
