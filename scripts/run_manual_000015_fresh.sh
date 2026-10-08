#!/usr/bin/env zsh
set -euo pipefail

cd "${0:A:h:h}"
out="${WEBGEN_RUN_OUTPUT:-outputs/experiment/manual_000015_fresh}"

# Manual retrieval ablation for 000015.
# The selected cases are in config/golden_source_000015.txt.
# No automatic vector retrieval and no disabled/No-Memory arm are run here.
WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-2}" \
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --batches 1 \
  --task-ids 000015 \
  --modes continual \
  --memory-representation case_only \
  --post-task-reflection \
  --manual-memory-file config/golden_source_000015.txt \
  --url "${WEBGEN_BOLT_URL:-http://localhost:5186/}" \
  --generator-model "${WEBGEN_GENERATOR_API_MODEL:-webgen-generator-gpt41-mini}" \
  --output "$out" \
  --database "$out/memory.db"
