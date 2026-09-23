#!/bin/zsh
# Paired No-Memory vs Continual-LTM batch-1 run with Qwen generation.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
output="$project_root/outputs/experiment/continual_domain_blocks_qwen_v2"
mkdir -p "$output"

bolt_pid=""
if lsof -nP -iTCP:5182 -sTCP:LISTEN >/dev/null 2>&1; then
  print "Reusing an existing Bolt listener on 5182." >>"$output/bolt.log"
else
  "$script_dir/start_bolt_provider.sh" --provider dashscope --port 5182 >>"$output/bolt.log" 2>&1 &
  bolt_pid=$!
fi
cleanup() { [[ -n "$bolt_pid" ]] && kill -TERM "$bolt_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  lsof -nP -iTCP:5182 -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 1
done
lsof -nP -iTCP:5182 -sTCP:LISTEN >/dev/null 2>&1 || {
  tail -80 "$output/bolt.log"; exit 1
}

cd "$project_root"
export WEBGEN_EVALUATOR_API_KEY="${DASHSCOPE_API_KEY:?DASHSCOPE_API_KEY is required}"
export WEBGEN_EVALUATOR_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export WEBGEN_EVALUATOR_MODEL="qwen3-vl-32b-instruct"
PYTHONUNBUFFERED=1 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 --modes disabled continual --url http://localhost:5182/ \
  --generator-model qwen3-coder-next \
  --output "$output" --database "$output/memory.db" "$@" \
  2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do
    printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$line"
  done | tee -a "$output/runner.log"
