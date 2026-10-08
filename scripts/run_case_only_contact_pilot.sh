#!/bin/zsh
# Three-generation diagnostic: Case-only Long Memory only.
# 000014 creates a lead-form case; 000015 and 000016 test transfer to contact
# submission/confirmation flows. The store starts empty and never writes
# Experience or Skill rows in this protocol.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
output="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/case_only_contact_pilot_r1}"
port="${WEBGEN_BOLT_PORT:-5186}"
task_ids="${WEBGEN_TASK_IDS:-000014,000015,000016}"

cd "$project_root"
set -a
source "$project_root/.env"
set +a
mkdir -p "$output"

export WEBGEN_EVALUATOR_API_KEY="${AZURE_OPENAI_API_KEY:?AZURE_OPENAI_API_KEY is required}"
export WEBGEN_EVALUATOR_BASE_URL="${WEBVOYAGER_BASE_URL:?WEBVOYAGER_BASE_URL is required}"
export WEBGEN_EVALUATOR_MODEL="${WEBVOYAGER_API_MODEL:-webgen-evaluator-gpt54-mini}"

print "Running model preflight check (generator, reflection, embedding, evaluator)..." | tee -a "$output/runner.log"
env/webvoyager/bin/python3.10 "$script_dir/preflight_reflective_models.py" 2>&1 | \
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"

bolt_pid=""
if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
  print "Reusing an existing Bolt listener on $port." >>"$output/bolt.log"
else
  "$script_dir/start_bolt_provider.sh" --provider azure --port "$port" >>"$output/bolt.log" 2>&1 &
  bolt_pid=$!
fi
cleanup() { [[ -n "$bolt_pid" ]] && kill -TERM "$bolt_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in {1..60}; do
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 1
done
lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || { tail -80 "$output/bolt.log"; exit 1; }

PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 --task-ids "$task_ids" --modes continual \
  --memory-representation case_only --post-task-reflection \
  --url "http://localhost:$port/" --generator-model webgen-generator-gpt41-mini \
  --output "$output" --database "$output/memory.db" "$@" \
  2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"
