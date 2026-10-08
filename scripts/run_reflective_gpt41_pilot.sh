#!/bin/zsh
# First clean pilot: one complete domain (8 tasks), paired one-shot No-Memory
# versus one-shot continual Long Memory built through post-task reflection.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
output="$project_root/outputs/experiment/reflective_multimodal_gpt41_pilot"
mkdir -p "$output"

cd "$project_root"
# The Bolt launcher loads .env for its own child process, but the evaluator
# variables below are exported by this wrapper itself. Load the same existing
# project credentials before resolving those variables.
set -a
source "$project_root/.env"
set +a
export WEBGEN_EVALUATOR_API_KEY="${AZURE_OPENAI_API_KEY:?AZURE_OPENAI_API_KEY is required}"
export WEBGEN_EVALUATOR_BASE_URL="${WEBVOYAGER_BASE_URL:?WEBVOYAGER_BASE_URL is required}"
export WEBGEN_EVALUATOR_MODEL="${WEBVOYAGER_API_MODEL:-webgen-evaluator-gpt54-mini}"
print "Running model preflight check (generator, reflection, embedding, evaluator)..." | tee -a "$output/runner.log"
env/webvoyager/bin/python3.10 "$script_dir/preflight_reflective_models.py" 2>&1 | \
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"

bolt_pid=""
if lsof -nP -iTCP:5183 -sTCP:LISTEN >/dev/null 2>&1; then
  print "Reusing an existing Bolt listener on 5183." >>"$output/bolt.log"
else
  "$script_dir/start_bolt_provider.sh" --provider azure --port 5183 >>"$output/bolt.log" 2>&1 &
  bolt_pid=$!
fi
cleanup() { [[ -n "$bolt_pid" ]] && kill -TERM "$bolt_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  lsof -nP -iTCP:5183 -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 1
done
lsof -nP -iTCP:5183 -sTCP:LISTEN >/dev/null 2>&1 || { tail -80 "$output/bolt.log"; exit 1; }

PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 --modes disabled continual --post-task-reflection \
  --url http://localhost:5183/ --generator-model webgen-generator-gpt41-mini \
  --output "$output" --database "$output/memory.db" "$@" \
  2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"
