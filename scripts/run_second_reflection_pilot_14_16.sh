#!/bin/zsh
# Three-task diagnostic for raw reflections plus cross-task consolidation review.
# Candidates are logged only; they are deliberately not injected into generation.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
output="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/second_reflection_pilot_14_16_r1}"
port="${WEBGEN_BOLT_PORT:-5186}"

cd "$project_root"
set -a
source "$project_root/.env"
set +a
mkdir -p "$output"

export WEBGEN_EVALUATOR_API_KEY="${AZURE_OPENAI_API_KEY:?AZURE_OPENAI_API_KEY is required}"
export WEBGEN_EVALUATOR_BASE_URL="${WEBVOYAGER_BASE_URL:?WEBVOYAGER_BASE_URL is required}"
export WEBGEN_EVALUATOR_MODEL="${WEBVOYAGER_API_MODEL:-webgen-evaluator-gpt54-mini}"

bolt_pid=""
if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
  "$script_dir/start_bolt_provider.sh" --provider azure --port "$port" >>"$output/bolt.log" 2>&1 &
  bolt_pid=$!
fi
cleanup() { [[ -n "$bolt_pid" ]] && kill -TERM "$bolt_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in {1..60}; do
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 1
done

PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 --task-ids 000014,000015,000016 --modes continual \
  --memory-representation case_only --post-task-reflection \
  --url "http://localhost:$port/" --generator-model webgen-generator-gpt41-mini \
  --output "$output" --database "$output/memory.db" \
  2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"
