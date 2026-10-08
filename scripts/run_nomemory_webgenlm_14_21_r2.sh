#!/usr/bin/env bash
set -euo pipefail

# Clean rerun of the eight-task No Memory baseline after the generator-side
# output-token limit was corrected.  This script deliberately uses a new
# output directory and refuses to overwrite it.
#
# Required services (started separately):
#   SSH tunnel for WebGen-LM-7B on localhost:8000
#   SSH tunnel for qwen2.5-vl-32b-awq on localhost:8001
#   bash scripts/start_bolt_provider.sh --provider local --port 5186

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

output="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2}"
database="${WEBGEN_RUN_DATABASE:-$output/memory.db}"

if [ -e "$output" ]; then
  echo "Refusing to overwrite existing output: $output" >&2
  echo "Set WEBGEN_RUN_OUTPUT to a new directory to start a distinct run." >&2
  exit 1
fi

curl --fail --silent --show-error --max-time 10 \
  "${WEBGEN_BOLT_URL:-http://127.0.0.1:5186/}api/health" >/dev/null

# Read-only five-role connectivity check; it does not request generation.
env/webvoyager/bin/python3.10 scripts/preflight_reflective_models.py

# `disabled` guarantees no retrieval, Long Memory guidance, reflection, or
# task-experience writes. The empty SQLite database is runner schema setup.
WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-1}" \
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
    --output "$output" \
    --database "$database" \
    --task-ids 000014,000015,000016,000017,000018,000019,000020,000021 \
    --modes disabled \
    --url "${WEBGEN_BOLT_URL:-http://127.0.0.1:5186/}" \
    --generator-model "${WEBGEN_GENERATOR_API_MODEL:-WebGen-LM-7B}"
