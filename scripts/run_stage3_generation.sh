#!/usr/bin/env bash
set -euo pipefail

# Stage 3: generate + evaluate one task using the reviewed guidance in <stage_dir>/stage2.json.
# Usage: scripts/run_stage3_generation.sh <task_id> <stage_dir>
# Runs on a COPY of <stage_dir>/memory_snapshot.db so the snapshot stays reusable for stages 1-2.
task_id="${1:?task id, e.g. 000018}"
stage_dir="${2:?stage dir, e.g. outputs/experiment/stages_000018_r1}"
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
output="${WEBGEN_RUN_OUTPUT:-${stage_dir}_gen}"
[ -e "$output" ] && { echo "Output $output already exists; set WEBGEN_RUN_OUTPUT to a new path" >&2; exit 1; }
mkdir -p "$output"
memory_snapshot="${WEBGEN_MEMORY_SNAPSHOT:-$stage_dir/memory_snapshot.db}"
[ -f "$memory_snapshot" ] || { echo "Memory snapshot not found: $memory_snapshot" >&2; exit 1; }
cp "$memory_snapshot" "$output/memory.db"

WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-2}" \
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --output "$output" \
  --database "$output/memory.db" \
  --task-ids "$task_id" \
  --modes continual \
  --memory-representation case_only \
  --post-task-reflection \
  --guidance-file "$stage_dir/stage2.json" \
  ${WEBGEN_GUIDANCE_SELFCHECK:+--guidance-selfcheck} \
  --url "${WEBGEN_BOLT_URL:-http://localhost:5186/}" \
  --generator-model "${WEBGEN_GENERATOR_API_MODEL:-webgen-generator-gpt41-mini}"
