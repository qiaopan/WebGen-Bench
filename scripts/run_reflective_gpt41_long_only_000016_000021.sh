#!/bin/zsh
# Continuation pilot: preserve the reflective Long Memory learned from tasks
# 000014–000015, then run only Long Memory for 000016–000021.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
parent_output="$project_root/outputs/experiment/reflective_multimodal_gpt41_pilot"
parent_database="$parent_output/memory.db"
output="$project_root/outputs/experiment/reflective_multimodal_gpt41_long_only_000016_000021"
database="$output/memory.db"
mkdir -p "$output"

[[ -f "$parent_database" ]] || {
  print -u2 "Missing parent Long Memory database: $parent_database"
  exit 1
}

# Never mutate the completed pilot.  SQLite's backup command produces a safe,
# independent continuation database and lets a later rerun resume this batch.
if [[ ! -f "$database" ]]; then
  sqlite3 "$parent_database" ".backup '$database'"
  printf '{"parent_output":"%s","parent_database":"%s","continued_after_tasks":["000014","000015"]}\n' \
    "$parent_output" "$parent_database" > "$output/continuation-parent.json"
fi

cd "$project_root"
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
if lsof -nP -iTCP:5184 -sTCP:LISTEN >/dev/null 2>&1; then
  print "Reusing an existing Bolt listener on 5184." >>"$output/bolt.log"
else
  "$script_dir/start_bolt_provider.sh" --provider azure --port 5184 >>"$output/bolt.log" 2>&1 &
  bolt_pid=$!
fi
cleanup() { [[ -n "$bolt_pid" ]] && kill -TERM "$bolt_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in {1..60}; do
  lsof -nP -iTCP:5184 -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 1
done
lsof -nP -iTCP:5184 -sTCP:LISTEN >/dev/null 2>&1 || { tail -80 "$output/bolt.log"; exit 1; }

PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 --task-ids 000016,000017,000018,000019,000020,000021 \
  --modes continual --post-task-reflection \
  --url http://localhost:5184/ --generator-model webgen-generator-gpt41-mini \
  --output "$output" --database "$database" "$@" \
  2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"
