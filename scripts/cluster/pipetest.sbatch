#!/bin/bash
# One-task end-to-end check of the cluster profile (No Memory only): generation -> build ->
# functional evaluation (local Qwen-VL) -> appearance (Azure GPT-4o). Not an experiment result.
#SBATCH --job-name=qma-webgen-pipetest
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gres=gpu:h200:1
#SBATCH --output=/data/qma258/jobs/pipetest-%j.out
set -uo pipefail
source /data/qma258/env.sh
cd "$WG/webgen"

cleanup() { pm2 kill >/dev/null 2>&1; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

source scripts/cluster/start_services.sh || { echo PIPETEST_SERVICES_FAILED; exit 1; }

env/webvoyager/bin/python3.10 scripts/preflight_reflective_models.py || { echo PIPETEST_PREFLIGHT_FAILED; exit 1; }

out="outputs/experiment/cluster_pipetest_${SLURM_JOB_ID}"
export WEBGEN_GENERATION_TIMEOUT_SECONDS=2700 WEBGEN_MAX_REPAIR_ATTEMPTS=5 PYTHONUNBUFFERED=1
start=$(date +%s)
env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --modes disabled --url "$WEBGEN_BOLT_URL" --generator-model WebGen-LM-7B \
  --output "$out" --database "$out/memory.db" --task-ids "${PIPETEST_TASK:-000018}"
echo "PIPETEST_RUNNER_EXIT $? after $(( $(date +%s) - start ))s output=$out"
