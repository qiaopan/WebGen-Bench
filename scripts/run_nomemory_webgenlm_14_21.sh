#!/usr/bin/env bash
set -euo pipefail

# Eight-task No Memory baseline for the local WebGen-LM-7B setup.
#
# Required services (run in separate terminals before invoking this script):
#   ssh -N -L 8000:127.0.0.1:8000 qma258@130.216.118.84
#   ssh -N -L 8001:127.0.0.1:8001 qma258@130.216.119.129
#   bash scripts/start_bolt_provider.sh --provider local --port 5186
#
# Roles are read from .env:
#   generator             WebGen-LM-7B on http://127.0.0.1:8000/v1
#   functional evaluator  Qwen2.5-VL-32B on http://127.0.0.1:8001/v1
#   appearance evaluator  Azure GPT-4o
#   memory/reflection     not used by this No Memory run

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

output="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o}"
database="${WEBGEN_RUN_DATABASE:-$output/memory.db}"

if [ -e "$output" ]; then
  echo "Refusing to overwrite existing output: $output" >&2
  echo "Set WEBGEN_RUN_OUTPUT to a new directory to start a distinct run." >&2
  exit 1
fi

curl --fail --silent --show-error --max-time 10 \
  "${WEBGEN_BOLT_URL:-http://127.0.0.1:5186/}api/health" >/dev/null

# Performs tiny health calls only; no generation is requested here.
env/webvoyager/bin/python3.10 scripts/preflight_reflective_models.py

# `disabled` means no retrieval, no guidance injection, no reflection, and no
# writes of task experience.  The database exists only because the common
# runner initialises its schema before entering the disabled arm.
WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-1}" \
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
    --output "$output" \
    --database "$database" \
    --task-ids 000014,000015,000016,000017,000018,000019,000020,000021 \
    --modes disabled \
    --url "${WEBGEN_BOLT_URL:-http://127.0.0.1:5186/}" \
    --generator-model "${WEBGEN_GENERATOR_API_MODEL:-WebGen-LM-7B}"
