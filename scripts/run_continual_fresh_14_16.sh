#!/usr/bin/env bash
set -euo pipefail

# Fresh continual Long Memory pilot: 000014 -> 000015 -> 000016.
# No disabled arm and no manual Golden Case injection.
project_root="$(cd "$(dirname "$0")/.." && pwd)"
output="$project_root/outputs/experiment/continual_14_to_16_fresh"
database="$output/memory.db"

cd "$project_root"
WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-2}" \
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --output "$output" \
  --database "$database" \
  --task-ids 000014,000015,000016 \
  --modes continual \
  --memory-representation case_only \
  --post-task-reflection \
  --url "${WEBGEN_BOLT_URL:-http://localhost:5186/}" \
  --generator-model "${WEBGEN_GENERATOR_API_MODEL:-webgen-generator-gpt41-mini}"
