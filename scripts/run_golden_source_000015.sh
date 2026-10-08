#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
out="${WEBGEN_RUN_OUTPUT:-outputs/experiment/golden_source_000015_r1}"
manual_memory_file="${WEBGEN_MANUAL_MEMORY_FILE:-config/golden_source_000015.txt}"
WEBGEN_MAX_REPAIR_ATTEMPTS=2 env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 --task-ids 000015 --modes continual \
  --memory-representation case_only --post-task-reflection \
  --manual-memory-file "$manual_memory_file" \
  --url http://localhost:5186/ --generator-model webgen-generator-gpt41-mini \
  --output "$out" --database "$out/memory.db"
